"""Log Broadcaster service for managing real-time debug log distribution.

Responsible for:
- Collecting JSON lines from Agent Worker stderr streams
- Broadcasting log entries to subscribed WebSocket clients in real-time
- Buffering logs for batch persistence after session ends
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import aiosqlite
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class LogBroadcaster:
    """Singleton service that manages debug log broadcasting and persistence.

    Internal state:
    - _subscribers: session_id → set of connected WebSocket clients
    - _log_buffers: session_id → list of buffered log entry dicts
    - _reader_tasks: session_id → asyncio Task reading stderr
    """

    _instance: "LogBroadcaster | None" = None

    def __new__(cls) -> "LogBroadcaster":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._subscribers: dict[str, set[WebSocket]] = {}
        self._log_buffers: dict[str, list[dict[str, Any]]] = {}
        self._reader_tasks: dict[str, asyncio.Task] = {}

    async def subscribe(self, session_id: str, websocket: WebSocket) -> None:
        """Add a WebSocket client to a session's subscriber set."""
        if session_id not in self._subscribers:
            self._subscribers[session_id] = set()
        self._subscribers[session_id].add(websocket)

    async def unsubscribe(self, session_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket client from a session's subscriber set."""
        if session_id in self._subscribers:
            self._subscribers[session_id].discard(websocket)
            if not self._subscribers[session_id]:
                del self._subscribers[session_id]

    async def broadcast(self, session_id: str, log_entry: dict[str, Any]) -> None:
        """Send a log entry to all subscribers of a session and buffer it.

        Args:
            session_id: The session to broadcast to.
            log_entry: Dict containing timestamp, direction, event_type, payload.
        """
        # Buffer for later persistence
        if session_id not in self._log_buffers:
            self._log_buffers[session_id] = []
        self._log_buffers[session_id].append(log_entry)

        # Broadcast to all connected WebSocket clients
        if session_id in self._subscribers:
            message = json.dumps(log_entry)
            disconnected: list[WebSocket] = []
            for ws in self._subscribers[session_id]:
                try:
                    await ws.send_text(message)
                except Exception:
                    # Client disconnected, mark for removal
                    disconnected.append(ws)
            # Clean up disconnected clients
            for ws in disconnected:
                self._subscribers[session_id].discard(ws)

    async def start_reading(self, session_id: str, stdout_reader: asyncio.StreamReader) -> None:
        """Start an asyncio task that reads JSON lines from stderr and broadcasts them.

        Args:
            session_id: The session this reader is associated with.
            stdout_reader: The StreamReader connected to Agent Worker's stderr.
        """
        task = asyncio.create_task(self._read_stdout(session_id, stdout_reader))
        self._reader_tasks[session_id] = task

    async def _read_stdout(self, session_id: str, reader: asyncio.StreamReader) -> None:
        """Internal coroutine that reads lines from stderr and broadcasts parsed entries."""
        try:
            while True:
                line = await reader.readline()
                if not line:
                    # EOF reached, Agent Worker process ended
                    break
                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue
                try:
                    data = json.loads(line_str)
                except json.JSONDecodeError:
                    logger.warning(
                        "Malformed JSON line from session %s: %s",
                        session_id,
                        line_str[:200],
                    )
                    continue

                # Skip if parsed JSON is not a dict (e.g., a bare string)
                if not isinstance(data, dict):
                    continue
                # Build a normalized log entry.
                # If the payload is already a JSON string (as emitted by the
                # agent worker), store it as-is to avoid double-encoding.
                raw_payload = data.get("payload", data)
                payload_str = (
                    raw_payload if isinstance(raw_payload, str) else json.dumps(raw_payload)
                )
                log_entry = {
                    "session_id": session_id,
                    "timestamp": data.get(
                        "timestamp",
                        datetime.now(UTC).isoformat(),
                    ),
                    "direction": data.get("direction", "internal"),
                    "event_type": data.get("event_type", data.get("type", "unknown")),
                    "payload": payload_str,
                }
                await self.broadcast(session_id, log_entry)
        except asyncio.CancelledError:
            logger.info("Reader task cancelled for session %s", session_id)
        except Exception as e:
            logger.error("Error reading stderr for session %s: %s", session_id, e)

    def stop_reading(self, session_id: str) -> None:
        """Cancel the reading task for a session."""
        task = self._reader_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    async def persist_logs(self, session_id: str, db: aiosqlite.Connection) -> None:
        """Bulk insert buffered log entries into session_logs table, then clear buffer.

        Args:
            session_id: The session whose logs should be persisted.
            db: An active aiosqlite database connection.
        """
        buffer = self._log_buffers.pop(session_id, [])
        if not buffer:
            return

        await db.executemany(
            """
            INSERT INTO session_logs (session_id, timestamp, direction, event_type, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    session_id,
                    entry.get("timestamp", ""),
                    entry.get("direction", "internal"),
                    entry.get("event_type", "unknown"),
                    entry.get("payload", "{}"),
                )
                for entry in buffer
                if isinstance(entry, dict)
            ],
        )
        await db.commit()
        logger.info("Persisted %d log entries for session %s", len(buffer), session_id)

    async def persist_messages(self, session_id: str, db: aiosqlite.Connection) -> None:
        """Extract message.added events from buffer and save to session_messages table."""
        buffer = self._log_buffers.get(session_id, [])
        messages = []
        for entry in buffer:
            if not isinstance(entry, dict):
                continue
            if entry.get("event_type") == "message.added":
                try:
                    payload = json.loads(entry.get("payload", "{}"))
                    # A double-encoded payload decodes to a str (not a dict);
                    # skip such entries rather than raising AttributeError.
                    if not isinstance(payload, dict):
                        continue
                    role = payload.get("role")
                    text = payload.get("text")
                    if role and text:
                        messages.append(
                            (
                                session_id,
                                role,
                                text,
                                entry.get("timestamp", ""),
                            )
                        )
                except (json.JSONDecodeError, TypeError, AttributeError):
                    pass

        if messages:
            await db.executemany(
                """
                INSERT INTO session_messages (session_id, role, content, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                messages,
            )
            await db.commit()
            logger.info("Persisted %d messages for session %s", len(messages), session_id)

    def get_buffer(self, session_id: str) -> list[dict[str, Any]]:
        """Get the current log buffer for a session (for testing/inspection)."""
        return self._log_buffers.get(session_id, [])

    def has_active_reader(self, session_id: str) -> bool:
        """Check if there is an active reader task for the given session."""
        task = self._reader_tasks.get(session_id)
        return task is not None and not task.done()


# Module-level singleton accessor
def get_log_broadcaster() -> LogBroadcaster:
    """Get the singleton LogBroadcaster instance."""
    return LogBroadcaster()
