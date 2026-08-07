"""REST API routes for Voice Session management."""

import aiosqlite
from fastapi import APIRouter, Depends, Response
from starlette.status import HTTP_201_CREATED, HTTP_204_NO_CONTENT

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
async def create_session(data: SessionCreate, db: aiosqlite.Connection = Depends(get_db)):
    """Create a new voice session.

    Validates that the instance exists, generates a unique room name and
    LiveKit token, creates the session record, and returns connection info.

    Returns 404 if the instance does not exist.
    """
    return await _session_service.create_session(db, data.instance_id, data.voice)


@router.get("", response_model=PaginatedSessions)
async def list_sessions(
    page: int = 1,
    page_size: int = 20,
    instance_id: str | None = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    """List sessions with pagination and optional instance filter.

    Supports query parameters:
    - page: page number (default 1)
    - page_size: items per page (default 20)
    - instance_id: optional filter by instance
    """
    return await _session_service.list_sessions(db, page, page_size, instance_id)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Get session detail by ID.

    Returns 404 if not found.
    """
    return await _session_service.get_session(db, session_id)


@router.get("/{session_id}/logs")
async def get_session_logs(session_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Get saved debug logs for a completed session.

    Returns an array of log entries from the session_logs table.
    Returns 404 if session doesn't exist.
    """
    from fastapi import HTTPException

    # Verify session exists
    cursor = await db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
    if not await cursor.fetchone():
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
            "id": row[0],
            "session_id": row[1],
            "timestamp": row[2],
            "direction": row[3],
            "event_type": row[4],
            "payload": row[5],
        }
        for row in rows
    ]


@router.post("/{session_id}/stop")
async def stop_session(session_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Stop an active session.

    Updates status to 'cancelled' and sets end_time.
    Returns 404 if the session does not exist.
    """
    return await _session_service.stop_session(db, session_id)


@router.delete("/{session_id}", status_code=HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a session record and its associated logs.

    Returns 404 if the session does not exist.
    """
    await _session_service.delete_session(db, session_id)
    return Response(status_code=HTTP_204_NO_CONTENT)


# Internal endpoint for Agent Worker token usage reporting
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
