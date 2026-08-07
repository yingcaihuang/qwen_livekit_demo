"""Pydantic data models for the Azure Voice Testing Admin system."""

from app.models.chat import (
    ChatCompletionRequest,
    ChatMessage,
    ChatMessageRecord,
)
from app.models.dashboard import DashboardStats, InstanceUsage, TypeUsage
from app.models.history import HistoryItem, PaginatedHistory
from app.models.instance import (
    InstanceCreate,
    InstanceDetail,
    InstanceSummary,
    InstanceUpdate,
)
from app.models.log import LogEntry
from app.models.session import (
    PaginatedSessions,
    SessionCreate,
    SessionDetail,
    SessionResponse,
    TokenUsageReport,
)

__all__ = [
    # Instance models
    "InstanceCreate",
    "InstanceUpdate",
    "InstanceSummary",
    "InstanceDetail",
    # Chat models
    "ChatMessage",
    "ChatCompletionRequest",
    "ChatMessageRecord",
    # Session models
    "SessionCreate",
    "SessionResponse",
    "SessionDetail",
    "PaginatedSessions",
    "TokenUsageReport",
    # Log models
    "LogEntry",
    # Dashboard models
    "DashboardStats",
    "InstanceUsage",
    "TypeUsage",
    # History models
    "HistoryItem",
    "PaginatedHistory",
]
