"""Tests for the LogBroadcaster service."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from app.services.log_broadcaster import LogBroadcaster, get_log_broadcaster


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the LogBroadcaster singleton between tests."""
    LogBroadcaster._instance = None
    yield
    LogBroadcaster._instance = None


@pytest.fixture
def broadcaster():
    return LogBroadcaster()


class TestSingleton:
    def test_returns_same_instance(self):
        a = LogBroadcaster()
        b = LogBroadcaster()
        assert a is b

    def test_get_log_broadcaster_returns_singleton(self):
        instance = get_log_broadcaster()
        assert instance is LogBroadcaster()


class TestSubscribeUnsubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_adds_websocket(self, broadcaster):
        ws = MagicMock()
        await broadcaster.subscribe("session-1", ws)
        assert ws in broadcaster._subscribers["session-1"]

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_websocket(self, broadcaster):
        ws = MagicMock()
        await broadcaster.subscribe("session-1", ws)
        await broadcaster.unsubscribe("session-1", ws)
        assert "session-1" not in broadcaster._subscribers

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_session_no_error(self, broadcaster):
        ws = MagicMock()
        # Should not raise
        await broadcaster.unsubscribe("no-such-session", ws)

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, broadcaster):
        ws1 = MagicMock()
        ws2 = MagicMock()
        await broadcaster.subscribe("session-1", ws1)
        await broadcaster.subscribe("session-1", ws2)
        assert len(broadcaster._subscribers["session-1"]) == 2


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_sends_to_subscribers(self, broadcaster):
        ws = AsyncMock()
        await broadcaster.subscribe("session-1", ws)

        log_entry = {
            "session_id": "session-1",
            "timestamp": "2024-01-01T00:00:00",
            "direction": "inbound",
            "event_type": "session.update",
            "payload": "{}",
        }
        await broadcaster.broadcast("session-1", log_entry)

        ws.send_text.assert_called_once_with(json.dumps(log_entry))

    @pytest.mark.asyncio
    async def test_broadcast_buffers_entry(self, broadcaster):
        log_entry = {
            "session_id": "session-1",
            "timestamp": "2024-01-01T00:00:00",
            "direction": "outbound",
            "event_type": "response.audio.delta",
            "payload": '{"data": "test"}',
        }
        await broadcaster.broadcast("session-1", log_entry)

        buffer = broadcaster.get_buffer("session-1")
        assert len(buffer) == 1
        assert buffer[0] == log_entry

    @pytest.mark.asyncio
    async def test_broadcast_removes_disconnected_clients(self, broadcaster):
        ws_good = AsyncMock()
        ws_bad = AsyncMock()
        ws_bad.send_text.side_effect = RuntimeError("disconnected")

        await broadcaster.subscribe("session-1", ws_good)
        await broadcaster.subscribe("session-1", ws_bad)

        log_entry = {
            "session_id": "session-1",
            "timestamp": "2024-01-01T00:00:00",
            "direction": "internal",
            "event_type": "info",
            "payload": "{}",
        }
        await broadcaster.broadcast("session-1", log_entry)

        # Bad client should be removed
        assert ws_bad not in broadcaster._subscribers["session-1"]
        # Good client still present
        assert ws_good in broadcaster._subscribers["session-1"]

    @pytest.mark.asyncio
    async def test_broadcast_no_subscribers_still_buffers(self, broadcaster):
        log_entry = {
            "session_id": "session-2",
            "timestamp": "2024-01-01T00:00:00",
            "direction": "internal",
            "event_type": "info",
            "payload": "{}",
        }
        await broadcaster.broadcast("session-2", log_entry)
        assert len(broadcaster.get_buffer("session-2")) == 1


class TestStartReading:
    @pytest.mark.asyncio
    async def test_reads_json_lines_and_broadcasts(self, broadcaster):
        """Test that start_reading parses JSON lines from stdout."""
        ws = AsyncMock()
        await broadcaster.subscribe("session-1", ws)

        # Simulate stdout with JSON lines
        lines = [
            json.dumps(
                {
                    "timestamp": "2024-01-01T00:00:00",
                    "direction": "inbound",
                    "event_type": "session.created",
                    "payload": {"id": "test"},
                }
            ).encode()
            + b"\n",
            json.dumps(
                {
                    "timestamp": "2024-01-01T00:00:01",
                    "direction": "outbound",
                    "event_type": "response.done",
                    "payload": {"usage": {"input_tokens": 10}},
                }
            ).encode()
            + b"\n",
        ]

        reader = asyncio.StreamReader()
        for line in lines:
            reader.feed_data(line)
        reader.feed_eof()

        await broadcaster.start_reading("session-1", reader)
        # Wait for the task to complete
        task = broadcaster._reader_tasks["session-1"]
        await task

        # Should have 2 log entries buffered
        buffer = broadcaster.get_buffer("session-1")
        assert len(buffer) == 2
        assert buffer[0]["event_type"] == "session.created"
        assert buffer[1]["event_type"] == "response.done"

    @pytest.mark.asyncio
    async def test_handles_malformed_json_gracefully(self, broadcaster):
        """Malformed JSON lines should be skipped, not crash the reader."""
        lines = [
            b"not valid json\n",
            json.dumps(
                {
                    "timestamp": "2024-01-01T00:00:00",
                    "direction": "internal",
                    "event_type": "info",
                    "payload": {},
                }
            ).encode()
            + b"\n",
            b"another broken line {{\n",
        ]

        reader = asyncio.StreamReader()
        for line in lines:
            reader.feed_data(line)
        reader.feed_eof()

        await broadcaster.start_reading("session-1", reader)
        task = broadcaster._reader_tasks["session-1"]
        await task

        # Only the valid line should be buffered
        buffer = broadcaster.get_buffer("session-1")
        assert len(buffer) == 1
        assert buffer[0]["event_type"] == "info"

    @pytest.mark.asyncio
    async def test_has_active_reader(self, broadcaster):
        """Test has_active_reader returns correct status."""
        assert not broadcaster.has_active_reader("session-1")

        reader = asyncio.StreamReader()
        # Don't feed EOF so the reader stays active
        reader.feed_data(b"")

        await broadcaster.start_reading("session-1", reader)
        assert broadcaster.has_active_reader("session-1")

        # Now feed EOF to let it finish
        reader.feed_eof()
        task = broadcaster._reader_tasks["session-1"]
        await task
        assert not broadcaster.has_active_reader("session-1")


class TestStopReading:
    @pytest.mark.asyncio
    async def test_stop_reading_cancels_task(self, broadcaster):
        """stop_reading should cancel the active reading task."""
        reader = asyncio.StreamReader()
        # Don't feed EOF — task will block on readline

        await broadcaster.start_reading("session-1", reader)
        assert broadcaster.has_active_reader("session-1")

        broadcaster.stop_reading("session-1")
        # Give the event loop a chance to process the cancellation
        await asyncio.sleep(0.05)
        assert not broadcaster.has_active_reader("session-1")

    def test_stop_reading_nonexistent_session_no_error(self, broadcaster):
        """Stopping a non-existent session should not raise."""
        broadcaster.stop_reading("no-such-session")


class TestPersistLogs:
    @pytest.mark.asyncio
    async def test_persist_logs_inserts_to_db(self, broadcaster, tmp_path):
        """persist_logs should bulk insert buffered entries into session_logs."""
        db_path = str(tmp_path / "test.db")
        async with aiosqlite.connect(db_path) as db:
            # Create the table
            await db.execute("""
                CREATE TABLE session_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}'
                )
            """)
            await db.commit()

            # Buffer some logs
            for i in range(3):
                await broadcaster.broadcast(
                    "session-1",
                    {
                        "session_id": "session-1",
                        "timestamp": f"2024-01-01T00:00:0{i}",
                        "direction": "inbound",
                        "event_type": f"event.{i}",
                        "payload": json.dumps({"index": i}),
                    },
                )

            # Persist
            await broadcaster.persist_logs("session-1", db)

            # Verify entries in DB
            cursor = await db.execute(
                "SELECT session_id, timestamp, direction, event_type, payload FROM session_logs ORDER BY timestamp"
            )
            rows = await cursor.fetchall()
            assert len(rows) == 3
            assert rows[0][3] == "event.0"
            assert rows[2][3] == "event.2"

            # Buffer should be cleared
            assert broadcaster.get_buffer("session-1") == []

    @pytest.mark.asyncio
    async def test_persist_empty_buffer_no_op(self, broadcaster, tmp_path):
        """Persisting when there's no buffer should not raise or insert."""
        db_path = str(tmp_path / "test.db")
        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                CREATE TABLE session_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}'
                )
            """)
            await db.commit()

            # Should not raise
            await broadcaster.persist_logs("session-1", db)

            cursor = await db.execute("SELECT COUNT(*) FROM session_logs")
            count = (await cursor.fetchone())[0]
            assert count == 0
