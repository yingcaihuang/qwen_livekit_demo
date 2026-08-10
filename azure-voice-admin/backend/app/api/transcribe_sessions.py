"""API routes for Transcribe Sessions."""

import aiosqlite
from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, require_permission
from app.database import get_db
from app.models.session import SessionResponse, TranscribeSessionCreate
from app.services.session_service import SessionService

router = APIRouter(prefix="/api/transcribe-sessions", tags=["transcribe-sessions"])
_session_service = SessionService()


@router.post("", response_model=SessionResponse, status_code=201)
async def create_transcribe_session(
    body: TranscribeSessionCreate,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(require_permission("transcribe:use")),
) -> SessionResponse:
    """Create a new real-time transcription session."""
    return await _session_service.create_transcribe_session(
        db, body.instance_id, body.source_language, user=user
    )
