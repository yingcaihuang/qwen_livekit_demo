"""API routes for Translate Sessions."""

import aiosqlite
from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, require_permission
from app.database import get_db
from app.models.session import SessionResponse, TranslateSessionCreate
from app.services.session_service import SessionService

router = APIRouter(prefix="/api/translate-sessions", tags=["translate-sessions"])
_session_service = SessionService()


@router.post("", response_model=SessionResponse, status_code=201)
async def create_translate_session(
    body: TranslateSessionCreate,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(require_permission("translate:use")),
) -> SessionResponse:
    """Create a new real-time translation session."""
    return await _session_service.create_translate_session(
        db, body.instance_id, body.target_language, user=user
    )
