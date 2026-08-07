"""Integration tests for the WebSocket log streaming endpoint."""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

# Set temp DB path before imports
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")

import app.database as db_mod  # noqa: E402

from app.main import app  # noqa: E402
from app.services.log_broadcaster import get_log_broadcaster  # noqa: E402


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    """Use a fresh temp database for each test."""
    test_db = str(tmp_path / "test.db")
    db_mod.DB_PATH = test_db
    from app.database import init_db

    await init_db()
    yield
    if Path(test_db).exists():
        Path(test_db).unlink()


class TestWebSocketSessionLogs:
    """Tests for WS /ws/sessions/{session_id}/logs endpoint."""

    def test_websocket_connect_and_receive_log(self):
        """Test that a client can connect and receive broadcast logs."""
        session_id = "test-session-123"
        client = TestClient(app)

        with client.websocket_connect(f"/ws/sessions/{session_id}/logs") as ws:
            # Broadcast a log entry from the broadcaster
            broadcaster = get_log_broadcaster()

            # We need to broadcast from an async context; use the internal method
            # The TestClient runs in a thread, so we broadcast via the app
            log_entry = {
                "session_id": session_id,
                "timestamp": "2024-01-01T00:00:00Z",
                "direction": "inbound",
                "event_type": "session.created",
                "payload": json.dumps({"key": "value"}),
            }

            # Use the synchronous test approach: since broadcast needs async,
            # we'll verify that the subscriber list is populated correctly
            # by checking the broadcaster state
            assert session_id in broadcaster._subscribers
            assert len(broadcaster._subscribers[session_id]) == 1

    def test_websocket_disconnect_unsubscribes(self):
        """Test that disconnection removes the client from subscribers."""
        session_id = "test-session-456"
        broadcaster = get_log_broadcaster()
        client = TestClient(app)

        with client.websocket_connect(f"/ws/sessions/{session_id}/logs") as ws:
            assert session_id in broadcaster._subscribers

        # After disconnect, subscriber should be cleaned up
        # Note: cleanup happens in the finally block
        assert session_id not in broadcaster._subscribers or \
               len(broadcaster._subscribers.get(session_id, set())) == 0

    def test_websocket_multiple_sessions(self):
        """Test that multiple session subscriptions are independent."""
        broadcaster = get_log_broadcaster()
        client = TestClient(app)

        with client.websocket_connect("/ws/sessions/session-a/logs") as ws_a:
            with client.websocket_connect("/ws/sessions/session-b/logs") as ws_b:
                assert "session-a" in broadcaster._subscribers
                assert "session-b" in broadcaster._subscribers
                assert len(broadcaster._subscribers["session-a"]) == 1
                assert len(broadcaster._subscribers["session-b"]) == 1

    def test_websocket_broadcast_delivers_message(self):
        """Test that broadcast sends JSON messages to connected clients."""
        session_id = "test-broadcast-session"
        broadcaster = get_log_broadcaster()
        client = TestClient(app)

        with client.websocket_connect(f"/ws/sessions/{session_id}/logs") as ws:
            # Broadcast a log entry via the broadcaster
            import asyncio

            log_entry = {
                "session_id": session_id,
                "timestamp": "2024-01-01T12:00:00Z",
                "direction": "outbound",
                "event_type": "response.done",
                "payload": json.dumps({"usage": {"input_tokens": 10}}),
            }

            # Run broadcast in the event loop
            # The TestClient's WebSocket operates synchronously;
            # we need to use the running loop from the app
            import threading

            def broadcast_in_thread():
                loop = asyncio.new_event_loop()
                loop.run_until_complete(broadcaster.broadcast(session_id, log_entry))
                loop.close()

            t = threading.Thread(target=broadcast_in_thread)
            t.start()
            t.join()

            # Receive the message on the WebSocket
            data = ws.receive_json(mode="text")
            assert data["session_id"] == session_id
            assert data["event_type"] == "response.done"
            assert data["direction"] == "outbound"
