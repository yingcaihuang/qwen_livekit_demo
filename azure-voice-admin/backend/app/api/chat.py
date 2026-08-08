"""REST API routes for LLM Chat (Chat Completions) streaming.

Exposes a single thin streaming endpoint that proxies Azure OpenAI Chat
Completions through :class:`ChatService`. The service handles lazy session
creation, token forwarding, message + usage persistence, and the normalized
SSE event contract (``session`` / ``delta`` / ``done`` / ``error``).

Connection lifecycle note (why we open a dedicated connection here):
``ChatService.stream_chat`` uses the database connection across the *entire*
lifetime of the streamed generator — including the final persistence step that
runs only after Azure's stream completes. A connection provided via
``Depends(get_db)`` is closed in the dependency's ``finally`` block, which can
run before a ``StreamingResponse`` body finishes producing values. To guarantee
the connection stays open until persistence completes, we open a dedicated
``aiosqlite`` connection inside the streaming generator (mirroring the
``aiosqlite.connect(DB_PATH)`` usage in ``main.py``) and enable
``PRAGMA foreign_keys = ON`` on it.
"""

from collections.abc import AsyncGenerator

import aiosqlite
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

import app.database as db_mod
from app.api.deps import CurrentUser, require_permission
from app.models.chat import ChatCompletionRequest
from app.services.chat_service import ChatService

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Singleton service instance (mirrors the pattern used in sessions.py).
_chat_service = ChatService()


@router.post("/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    user: CurrentUser = Depends(require_permission("chat:use")),
) -> StreamingResponse:
    """Stream a chat completion as Server-Sent Events (``text/event-stream``).

    The response body is produced by :meth:`ChatService.stream_chat`, which:
      - lazily creates a ``chat`` session on the first turn (emitting a
        ``session`` event),
      - forwards each token as a ``delta`` event,
      - persists the user + assistant messages and cumulative token usage once
        the Azure stream completes,
      - emits a final ``done`` event with usage, or an ``error`` event on
        failure (without crashing the stream).

    A dedicated database connection is opened for the duration of the stream so
    that end-of-stream persistence still succeeds (see module docstring).
    Records ``created_by = user.id`` on newly created sessions.
    """

    # Capture user.id before entering the generator (the Depends() scope is
    # valid for the lifetime of the request, including the streaming body).
    user_id = user.id

    async def event_stream() -> AsyncGenerator[str, None]:
        # Resolve DB_PATH at call time (as a module attribute) so that runtime
        # reassignment — e.g. test fixtures pointing at a temp database — is
        # respected, consistent with how ``get_db`` reads it.
        db = await aiosqlite.connect(db_mod.DB_PATH)
        db.row_factory = aiosqlite.Row
        try:
            # Enable foreign key enforcement per connection (matches get_db so
            # ON DELETE CASCADE behaves consistently for session_messages).
            await db.execute("PRAGMA foreign_keys = ON")
            async for frame in _chat_service.stream_chat(db, request, created_by=user_id):
                yield frame
        finally:
            await db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            # Disable proxy/browser buffering so tokens flush as they arrive.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
