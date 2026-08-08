"""REST API routes for Voice Session management."""

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Response
from starlette.status import HTTP_201_CREATED, HTTP_204_NO_CONTENT

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.database import get_db
from app.models.session import (
    PaginatedSessions,
    SessionCreate,
    SessionDetail,
    SessionResponse,
    TokenUsageReport,
)
from app.services.session_service import SessionService

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
internal_router = APIRouter(prefix="/internal", tags=["internal"])

# Singleton service instance
_session_service = SessionService()


@router.post("", status_code=HTTP_201_CREATED, response_model=SessionResponse)
async def create_session(
    data: SessionCreate,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(require_permission("session:run")),
):
    """Create a new voice session.

    Validates that the instance exists, generates a unique room name and
    LiveKit token, creates the session record, and returns connection info.
    Records ``created_by = user.id`` for multi-tenant isolation.

    Returns 404 if the instance does not exist.
    """
    return await _session_service.create_session(db, data.instance_id, data.voice, user=user)


@router.get("", response_model=PaginatedSessions)
async def list_sessions(
    page: int = 1,
    page_size: int = 20,
    instance_id: str | None = None,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """List sessions with pagination and optional instance filter.

    Multi-tenant: only shows user's own sessions unless user has
    ``resource:read:all``.
    """
    return await _session_service.list_sessions(db, page, page_size, instance_id, user=user)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Get session detail by ID.

    Returns 404 if not found or not owned by user.
    """
    return await _session_service.get_session(db, session_id, user=user)


@router.get("/{session_id}/logs")
async def get_session_logs(
    session_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Get saved debug logs for a completed session.

    Returns an array of log entries from the session_logs table.
    Returns 404 if session doesn't exist or not owned.
    """
    # Verify session exists and ownership
    cursor = await db.execute("SELECT id, created_by FROM sessions WHERE id = ?", (session_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    if "resource:read:all" not in user.capabilities and row[1] != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    # Fetch logs
    cursor = await db.execute(
        """
        SELECT id, session_id, timestamp, direction, event_type, payload
        FROM session_logs
        WHERE session_id = ?
        ORDER BY id ASC
        """,
        (session_id,),
    )
    rows = await cursor.fetchall()

    return [
        {
            "id": r[0],
            "session_id": r[1],
            "timestamp": r[2],
            "direction": r[3],
            "event_type": r[4],
            "payload": r[5],
        }
        for r in rows
    ]


@router.get("/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Get conversation transcript for a session.

    Returns an array of messages (user and assistant) from the session_messages table.
    Returns 404 if session doesn't exist or not owned.
    """
    # Verify session exists and ownership
    cursor = await db.execute("SELECT id, created_by FROM sessions WHERE id = ?", (session_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    if "resource:read:all" not in user.capabilities and row[1] != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    cursor = await db.execute(
        """
        SELECT id, session_id, role, content, timestamp, model, endpoint
        FROM session_messages
        WHERE session_id = ?
        ORDER BY id ASC
        """,
        (session_id,),
    )
    rows = await cursor.fetchall()

    return [
        {
            "id": r[0],
            "session_id": r[1],
            "role": r[2],
            "content": r[3],
            "timestamp": r[4],
            "model": r[5],
            "endpoint": r[6],
        }
        for r in rows
    ]


@router.post("/{session_id}/stop")
async def stop_session(
    session_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Stop an active session.

    Updates status to 'cancelled' and sets end_time.
    Returns 404 if the session does not exist or not owned.
    """
    # Check ownership before stopping
    cursor = await db.execute("SELECT id, created_by FROM sessions WHERE id = ?", (session_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    if "resource:read:all" not in user.capabilities and row[1] != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    return await _session_service.stop_session(db, session_id)


@router.delete("/{session_id}", status_code=HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Delete a session record and its associated logs.

    Returns 404 if the session does not exist or not owned.
    """
    # Check ownership before deleting
    cursor = await db.execute("SELECT id, created_by FROM sessions WHERE id = ?", (session_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    if "resource:read:all" not in user.capabilities and row[1] != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    await _session_service.delete_session(db, session_id)
    return Response(status_code=HTTP_204_NO_CONTENT)


# Internal endpoint for Agent Worker token usage reporting
# (Not protected by auth — called by agent worker, not browser)
@internal_router.post("/sessions/{session_id}/usage")
async def report_token_usage(
    session_id: str,
    report: TokenUsageReport,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Internal endpoint for Agent Worker to report token usage.

    Cumulatively adds input_tokens and output_tokens to the session record.
    Returns 404 if the session does not exist.
    """
    return await _session_service.report_token_usage(
        db, session_id, report.input_tokens, report.output_tokens
    )
