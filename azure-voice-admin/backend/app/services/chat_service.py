"""Service layer for LLM Chat (Chat Completions) streaming proxy.

Responsibilities:
- Lazily create / reuse a ``chat`` session record (reusing the existing
  ``sessions`` + ``session_messages`` tables).
- Proxy Azure OpenAI Chat Completions with ``stream=true`` via aiohttp,
  normalizing Azure's SSE chunks into the platform's own SSE event contract.
- Constrain request parameters server-side (``temperature`` clamped to
  ``[0, 2]``; ``max_tokens`` coerced to a positive integer or passed through
  when ``None``).
- Accumulate token usage and persist both the user and assistant messages
  once the turn completes.

The API key is never written to logs or client responses in full; only the
last 4 characters are ever referenced (Requirements 9.3).
"""

import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import aiohttp
import aiosqlite
from fastapi import HTTPException

from app.models.chat import ChatCompletionRequest, ChatMessage
from app.services.azure_urls import resolve_azure_url

logger = logging.getLogger("chat_service")


class ChatService:
    """Business logic for streaming LLM chat completions."""

    # ------------------------------------------------------------------
    # Parameter constraints (pure functions — used by property tests)
    # ------------------------------------------------------------------
    @staticmethod
    def _clamp_temperature(value: float) -> float:
        """Clamp temperature into the closed range [0.0, 2.0] (Requirement 2.5).

        Inputs below 0 become 0, inputs above 2 become 2, in-range values are
        returned unchanged.
        """
        return max(0.0, min(2.0, float(value)))

    @staticmethod
    def _sanitize_max_tokens(value: int | None) -> int | None:
        """Coerce ``max_tokens`` to a positive integer (Requirement 2.6).

        A ``None`` value is passed through unchanged (meaning "no limit").
        Any provided value is truncated to an int; values <= 0 are coerced to
        the smallest positive integer (1) so the Azure request always receives
        a valid positive integer.
        """
        if value is None:
            return None
        coerced = int(value)
        if coerced < 1:
            return 1
        return coerced

    @staticmethod
    def _azure_chat_url(endpoint: str) -> str:
        """Resolve the Azure Chat Completions URL (v1 / OpenAI-compatible surface).

        Handles a plain base host, a v1 base, and full v1 operation URLs (see
        ``resolve_azure_url``). ``stream_chat`` always includes ``model`` in the
        body, which is what the v1 surface expects.
        """
        return resolve_azure_url(endpoint, "chat/completions")

    # ------------------------------------------------------------------
    # SSE helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _sse(payload: dict) -> str:
        """Serialize a payload dict into a single SSE ``data:`` event frame."""
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    @staticmethod
    def _now() -> str:
        """Current UTC timestamp formatted like the rest of the services."""
        return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------
    async def _load_instance(self, db: aiosqlite.Connection, instance_id: str) -> dict:
        """Load an instance's credentials by id.

        Raises HTTPException 404 if the instance does not exist.
        """
        cursor = await db.execute(
            "SELECT id, endpoint, api_key, deployment, type FROM instances WHERE id = ?",
            (instance_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Instance not found")
        return {
            "id": row[0],
            "endpoint": row[1],
            "api_key": row[2],
            "deployment": row[3],
            "type": row[4],
        }

    async def new_conversation(self, db: aiosqlite.Connection, instance_id: str) -> str:
        """Create a new ``chat`` session record and return its session_id.

        Verifies the instance exists and is of type ``chat``. The session is
        created with ``status='active'``; ``room_name`` (a voice-specific,
        NOT NULL column) is set to the empty string ``''`` (Requirement 2.7).

        Raises HTTPException 404 if the instance does not exist, 422 if the
        instance is not a chat instance.
        """
        instance = await self._load_instance(db, instance_id)
        if instance["type"] != "chat":
            raise HTTPException(
                status_code=422,
                detail="Instance is not a chat instance",
            )

        session_id = uuid.uuid4().hex
        now = self._now()
        await db.execute(
            """
            INSERT INTO sessions (id, instance_id, room_name, status, start_time)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, instance_id, "", "active", now),
        )
        await db.commit()
        return session_id

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    async def persist_turn(
        self,
        db: aiosqlite.Connection,
        session_id: str,
        user_content: str | None,
        assistant_content: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Persist a completed chat turn.

        Appends the user message (if any) and the assistant message to
        ``session_messages`` (role + content + timestamp) and cumulatively adds
        the turn's token usage onto the ``sessions`` row (Requirements 3.2,
        3.3, 3.6). Turns that returned no usage contribute zero.
        """
        now = self._now()
        rows: list[tuple[str, str, str, str]] = []
        if user_content is not None:
            rows.append((session_id, "user", user_content, now))
        rows.append((session_id, "assistant", assistant_content, now))

        await db.executemany(
            """
            INSERT INTO session_messages (session_id, role, content, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
        await db.execute(
            """
            UPDATE sessions
            SET input_tokens = input_tokens + ?,
                output_tokens = output_tokens + ?
            WHERE id = ?
            """,
            (input_tokens, output_tokens, session_id),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # Request body construction
    # ------------------------------------------------------------------
    @staticmethod
    def _build_messages(request: ChatCompletionRequest) -> list[dict]:
        """Build the Azure messages array.

        Prepends the system prompt (if provided and non-empty) as the first
        ``system`` message, then appends the accumulated conversation context
        from ``request.messages`` (Requirement 2.3).
        """
        messages: list[dict] = []
        if request.system_prompt and request.system_prompt.strip():
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)
        return messages

    @staticmethod
    def _last_user_content(messages: list[ChatMessage]) -> str | None:
        """Return the content of the most recent user message, if any."""
        for message in reversed(messages):
            if message.role == "user":
                return message.content
        return None

    # ------------------------------------------------------------------
    # Streaming proxy
    # ------------------------------------------------------------------
    async def stream_chat(
        self, db: aiosqlite.Connection, request: ChatCompletionRequest
    ) -> AsyncGenerator[str, None]:
        """Stream a chat completion, yielding normalized SSE event frames.

        Event contract (each yielded as a ``data: {...}\\n\\n`` frame):
          - ``{"type": "session", "session_id": "..."}``  (only when a new
            session was lazily created)
          - ``{"type": "delta", "content": "..."}``       (per streamed token)
          - ``{"type": "done", "usage": {"input_tokens": n, "output_tokens": n}}``
          - ``{"type": "error", "message": "..."}``        (on any failure)

        On completion the user + assistant messages are persisted and the
        session token totals are updated. On error an ``error`` event is
        emitted and the generator returns without raising (Requirement 9.2).
        The API key is never included in any yielded event (Requirement 9.3).
        """
        # 1) Resolve instance credentials.
        try:
            instance = await self._load_instance(db, request.instance_id)
        except HTTPException as exc:
            yield self._sse({"type": "error", "message": str(exc.detail)})
            return

        # 2) Resolve / lazily create the chat session.
        session_id = request.session_id
        if not session_id:
            try:
                session_id = await self.new_conversation(db, request.instance_id)
            except HTTPException as exc:
                yield self._sse({"type": "error", "message": str(exc.detail)})
                return
            # Announce the newly created session so the client can track it.
            yield self._sse({"type": "session", "session_id": session_id})

        # 3) Build the Azure request.
        url = self._azure_chat_url(instance["endpoint"])
        body: dict = {
            "model": instance["deployment"],
            "messages": self._build_messages(request),
            "temperature": self._clamp_temperature(request.temperature),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        sanitized_max = self._sanitize_max_tokens(request.max_tokens)
        if sanitized_max is not None:
            body["max_tokens"] = sanitized_max

        headers = {
            "api-key": instance["api_key"],
            "Content-Type": "application/json",
        }

        # Log the exact outgoing request URL so users can see the real path in
        # `docker compose logs backend` (never log the api-key or headers).
        logger.info("Azure chat request -> POST %s", url)

        assistant_content = ""
        input_tokens = 0
        output_tokens = 0

        # Timing: measure with perf_counter for durations and wall-clock for
        # start/end timestamps. ttfb marks the FIRST delta/token yielded; total
        # marks the end of the stream (just before the done event). Chat timing
        # is reported in the done event but NOT persisted.
        t0 = time.perf_counter()
        started_at = self._now()
        ttfb_ms: int | None = None

        # 4) Stream from Azure, forwarding deltas and capturing usage.
        try:
            async with aiohttp.ClientSession() as http:
                async with http.post(url, json=body, headers=headers) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(
                            "Azure chat completion failed (status=%s url=%s) for instance %s",
                            resp.status,
                            url,
                            request.instance_id,
                        )
                        yield self._sse(
                            {
                                "type": "error",
                                "message": (
                                    f"Azure returned status {resp.status}: {error_text[:500]}"
                                ),
                            }
                        )
                        return

                    async for raw_line in resp.content:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[len("data:") :].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            logger.warning("Malformed SSE chunk from Azure: %s", data_str[:200])
                            continue

                        # Accumulate assistant content from choices[].delta.content.
                        for choice in chunk.get("choices", []) or []:
                            delta = choice.get("delta") or {}
                            piece = delta.get("content")
                            if piece:
                                # Record TTFB at the first token/delta yielded.
                                if ttfb_ms is None:
                                    ttfb_ms = round((time.perf_counter() - t0) * 1000)
                                assistant_content += piece
                                yield self._sse({"type": "delta", "content": piece})

                        # Usage arrives in a final chunk when include_usage=True.
                        usage = chunk.get("usage")
                        if usage:
                            input_tokens = usage.get("prompt_tokens", 0) or 0
                            output_tokens = usage.get("completion_tokens", 0) or 0
        except aiohttp.ClientError as exc:
            logger.error(
                "Azure chat completion connection error for instance %s (url=%s): %s",
                request.instance_id,
                url,
                exc,
            )
            yield self._sse({"type": "error", "message": f"Failed to reach Azure: {exc}"})
            return
        except Exception as exc:  # noqa: BLE001 - defensive: never crash the stream
            logger.error(
                "Unexpected error streaming chat for instance %s: %s",
                request.instance_id,
                exc,
            )
            yield self._sse({"type": "error", "message": "Unexpected error during streaming"})
            return

        # 5) Persist the turn (messages + cumulative usage). If usage was not
        #    returned, input_tokens/output_tokens remain 0 (Requirement 3.6).
        try:
            await self.persist_turn(
                db,
                session_id,
                self._last_user_content(request.messages),
                assistant_content,
                input_tokens,
                output_tokens,
            )
        except Exception as exc:  # noqa: BLE001 - persistence failure shouldn't crash the response
            logger.error("Failed to persist chat turn for session %s: %s", session_id, exc)

        # 6) Final event with normalized usage and (non-persisted) timing.
        #    total_ms = start -> done; ttfb_ms = start -> first token (None if no
        #    tokens were streamed). started_at/ended_at are wall-clock stamps.
        total_ms = round((time.perf_counter() - t0) * 1000)
        ended_at = self._now()
        yield self._sse(
            {
                "type": "done",
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
                "timing": {
                    "ttfb_ms": ttfb_ms,
                    "total_ms": total_ms,
                    "started_at": started_at,
                    "ended_at": ended_at,
                },
            }
        )
