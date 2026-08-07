"""Pydantic models for debug log entries."""

from pydantic import BaseModel


class LogEntry(BaseModel):
    """Model for a single debug log entry from a Voice Session."""

    id: int
    session_id: str
    timestamp: str
    direction: str  # inbound | outbound | internal
    event_type: str
    payload: str  # JSON string
