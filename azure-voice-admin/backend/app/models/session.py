"""Pydantic models for Voice Session management."""

from pydantic import BaseModel


class SessionCreate(BaseModel):
    """Request model for creating a new Voice Session."""

    instance_id: str
    voice: str = "alloy"  # Default voice


class SessionResponse(BaseModel):
    """Response model returned after session creation with LiveKit join info."""

    session_id: str
    room_name: str
    livekit_token: str  # 用户加入房间的 token
    livekit_url: str


class SessionDetail(BaseModel):
    """Response model for session detail view."""

    id: str
    instance_id: str
    instance_name: str
    room_name: str
    status: str
    start_time: str
    end_time: str | None = None
    input_tokens: int
    output_tokens: int
    error_message: str | None = None


class PaginatedSessions(BaseModel):
    """Response model for paginated session list."""

    items: list[SessionDetail]
    total: int
    page: int
    page_size: int


class TokenUsageReport(BaseModel):
    """Request model for Agent Worker to report token usage."""

    input_tokens: int
    output_tokens: int


class TranslateSessionCreate(BaseModel):
    """Request model for creating a translate session."""

    instance_id: str
    target_language: str  # ISO 639-1 code (e.g., "en", "zh")


class TranscribeSessionCreate(BaseModel):
    """Request model for creating a transcribe session."""

    instance_id: str
    source_language: str = ""  # Empty string = auto-detect
