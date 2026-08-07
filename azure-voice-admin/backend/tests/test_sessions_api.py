"""Integration tests for the Session REST API endpoints."""

import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Set temp DB path before imports
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")
os.environ["LIVEKIT_API_KEY"] = "devkey"
os.environ["LIVEKIT_API_SECRET"] = "secret-that-is-at-least-32-chars-long!"
os.environ["LIVEKIT_URL"] = "ws://localhost:7880"

import app.database as db_mod  # noqa: E402
from app.main import app  # noqa: E402


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


@pytest.fixture
async def client():
    """Provide an async HTTP client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def instance_id(client):
    """Create an instance and return its ID for session tests."""
    resp = await client.post(
        "/api/instances",
        json={
            "name": "test-instance",
            "endpoint": "https://test.openai.azure.com",
            "api_key": "sk-test-key-12345",
            "deployment": "gpt-4o-realtime",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestCreateSession:
    """Tests for POST /api/sessions."""

    async def test_create_success(self, client, instance_id):
        """Successfully creates a session and returns connection info."""
        resp = await client.post(
            "/api/sessions",
            json={"instance_id": instance_id},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "session_id" in data
        assert "room_name" in data
        assert data["room_name"].startswith("room-")
        assert "livekit_token" in data
        assert len(data["livekit_token"]) > 0
        assert data["livekit_url"] == "ws://localhost:7880"

    async def test_create_instance_not_found(self, client):
        """Returns 404 when instance does not exist."""
        resp = await client.post(
            "/api/sessions",
            json={"instance_id": "nonexistent-id"},
        )
        assert resp.status_code == 404

    async def test_create_session_persists_record(self, client, instance_id):
        """Session is persisted in database with connecting status."""
        resp = await client.post(
            "/api/sessions",
            json={"instance_id": instance_id},
        )
        session_id = resp.json()["session_id"]

        # Verify by fetching the session
        detail_resp = await client.get(f"/api/sessions/{session_id}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["status"] == "connecting"
        assert detail["instance_id"] == instance_id
        assert detail["instance_name"] == "test-instance"


class TestListSessions:
    """Tests for GET /api/sessions."""

    async def test_list_empty(self, client):
        """Returns empty list when no sessions exist."""
        resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 20

    async def test_list_after_create(self, client, instance_id):
        """Returns created sessions in the list."""
        await client.post(
            "/api/sessions",
            json={"instance_id": instance_id},
        )
        resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["instance_name"] == "test-instance"

    async def test_list_pagination(self, client, instance_id):
        """Supports pagination with page and page_size."""
        # Create 3 sessions
        for _ in range(3):
            await client.post(
                "/api/sessions",
                json={"instance_id": instance_id},
            )

        # Get page 1 with size 2
        resp = await client.get("/api/sessions?page=1&page_size=2")
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

        # Get page 2
        resp = await client.get("/api/sessions?page=2&page_size=2")
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 1
        assert data["page"] == 2

    async def test_list_filter_by_instance(self, client, instance_id):
        """Supports filtering sessions by instance_id."""
        # Create a session for the known instance
        await client.post(
            "/api/sessions",
            json={"instance_id": instance_id},
        )

        # Create a second instance with its own session
        resp = await client.post(
            "/api/instances",
            json={
                "name": "other-instance",
                "endpoint": "https://other.openai.azure.com",
                "api_key": "sk-other-key",
                "deployment": "gpt-4o",
            },
        )
        other_id = resp.json()["id"]
        await client.post(
            "/api/sessions",
            json={"instance_id": other_id},
        )

        # Filter by original instance
        resp = await client.get(f"/api/sessions?instance_id={instance_id}")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["instance_id"] == instance_id

    async def test_list_ordered_by_start_time_desc(self, client, instance_id):
        """Sessions are ordered by start_time descending."""
        import asyncio

        # Create sessions with small delay to ensure different timestamps
        for _ in range(3):
            await client.post(
                "/api/sessions",
                json={"instance_id": instance_id},
            )
            await asyncio.sleep(0.01)

        resp = await client.get("/api/sessions")
        data = resp.json()
        items = data["items"]
        assert len(items) == 3
        # Verify descending order
        for i in range(len(items) - 1):
            assert items[i]["start_time"] >= items[i + 1]["start_time"]


class TestGetSession:
    """Tests for GET /api/sessions/{id}."""

    async def test_get_existing(self, client, instance_id):
        """Returns session detail for existing session."""
        create_resp = await client.post(
            "/api/sessions",
            json={"instance_id": instance_id},
        )
        session_id = create_resp.json()["session_id"]

        resp = await client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == session_id
        assert data["instance_id"] == instance_id
        assert data["instance_name"] == "test-instance"
        assert data["status"] == "connecting"
        assert data["input_tokens"] == 0
        assert data["output_tokens"] == 0

    async def test_get_nonexistent(self, client):
        """Returns 404 for non-existent session."""
        resp = await client.get("/api/sessions/nonexistent-id")
        assert resp.status_code == 404


class TestStopSession:
    """Tests for POST /api/sessions/{id}/stop."""

    async def test_stop_success(self, client, instance_id):
        """Successfully stops a session and updates status."""
        create_resp = await client.post(
            "/api/sessions",
            json={"instance_id": instance_id},
        )
        session_id = create_resp.json()["session_id"]

        resp = await client.post(f"/api/sessions/{session_id}/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == session_id
        assert data["status"] == "cancelled"
        assert "end_time" in data

        # Verify the status was persisted
        detail_resp = await client.get(f"/api/sessions/{session_id}")
        assert detail_resp.json()["status"] == "cancelled"
        assert detail_resp.json()["end_time"] is not None

    async def test_stop_nonexistent(self, client):
        """Returns 404 for non-existent session."""
        resp = await client.post("/api/sessions/nonexistent-id/stop")
        assert resp.status_code == 404


class TestDeleteSession:
    """Tests for DELETE /api/sessions/{id}."""

    async def test_delete_success(self, client, instance_id):
        """Successfully deletes session and returns 204."""
        create_resp = await client.post(
            "/api/sessions",
            json={"instance_id": instance_id},
        )
        session_id = create_resp.json()["session_id"]

        resp = await client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 204

        # Verify it's gone
        get_resp = await client.get(f"/api/sessions/{session_id}")
        assert get_resp.status_code == 404

    async def test_delete_nonexistent(self, client):
        """Returns 404 for non-existent session."""
        resp = await client.delete("/api/sessions/nonexistent-id")
        assert resp.status_code == 404

    async def test_delete_removes_logs(self, client, instance_id):
        """Deleting session also removes associated logs."""
        import aiosqlite

        create_resp = await client.post(
            "/api/sessions",
            json={"instance_id": instance_id},
        )
        session_id = create_resp.json()["session_id"]

        # Insert some logs directly
        async with aiosqlite.connect(db_mod.DB_PATH) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                """
                INSERT INTO session_logs (session_id, timestamp, direction, event_type, payload)
                VALUES (?, datetime('now'), 'inbound', 'session.created', '{}')
                """,
                (session_id,),
            )
            await db.commit()

        # Delete the session
        resp = await client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 204

        # Verify logs are gone
        async with aiosqlite.connect(db_mod.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM session_logs WHERE session_id = ?",
                (session_id,),
            )
            count = (await cursor.fetchone())[0]
            assert count == 0


class TestReportTokenUsage:
    """Tests for POST /internal/sessions/{id}/usage."""

    async def test_report_usage_success(self, client, instance_id):
        """Successfully reports token usage (cumulative)."""
        create_resp = await client.post(
            "/api/sessions",
            json={"instance_id": instance_id},
        )
        session_id = create_resp.json()["session_id"]

        # Report first usage
        resp = await client.post(
            f"/internal/sessions/{session_id}/usage",
            json={"input_tokens": 100, "output_tokens": 200},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Report second usage (cumulative)
        resp = await client.post(
            f"/internal/sessions/{session_id}/usage",
            json={"input_tokens": 50, "output_tokens": 80},
        )
        assert resp.status_code == 200

        # Verify cumulative totals
        detail_resp = await client.get(f"/api/sessions/{session_id}")
        detail = detail_resp.json()
        assert detail["input_tokens"] == 150
        assert detail["output_tokens"] == 280

    async def test_report_usage_nonexistent_session(self, client):
        """Returns 404 for non-existent session."""
        resp = await client.post(
            "/internal/sessions/nonexistent-id/usage",
            json={"input_tokens": 10, "output_tokens": 20},
        )
        assert resp.status_code == 404
