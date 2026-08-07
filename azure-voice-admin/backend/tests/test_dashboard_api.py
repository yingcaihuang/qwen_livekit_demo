"""Integration tests for the Dashboard API endpoints."""

import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

import aiosqlite

# Set temp DB path before imports
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")

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


async def _insert_instance(db_path: str, instance_id: str, name: str) -> None:
    """Helper to insert an instance directly into the DB."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            INSERT INTO instances (id, name, endpoint, api_key, deployment, created_at, updated_at)
            VALUES (?, ?, 'https://ep.com', 'key-12345', 'dep', datetime('now'), datetime('now'))
            """,
            (instance_id, name),
        )
        await db.commit()


async def _insert_session(
    db_path: str,
    session_id: str,
    instance_id: str,
    status: str = "completed",
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Helper to insert a session directly into the DB."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            INSERT INTO sessions (id, instance_id, room_name, status, start_time, input_tokens, output_tokens)
            VALUES (?, ?, ?, ?, datetime('now'), ?, ?)
            """,
            (session_id, instance_id, f"room-{session_id}", status, input_tokens, output_tokens),
        )
        await db.commit()


class TestDashboardStats:
    """Tests for GET /api/dashboard/stats."""

    async def test_stats_empty_db(self, client):
        """Returns all zeros when no data exists."""
        resp = await client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {
            "total_instances": 0,
            "total_sessions": 0,
            "active_sessions": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }

    async def test_stats_with_instances_and_sessions(self, client):
        """Returns correct counts with instances and sessions."""
        await _insert_instance(db_mod.DB_PATH, "inst-1", "Instance A")
        await _insert_instance(db_mod.DB_PATH, "inst-2", "Instance B")

        await _insert_session(db_mod.DB_PATH, "s1", "inst-1", "completed", 100, 200)
        await _insert_session(db_mod.DB_PATH, "s2", "inst-1", "connected", 50, 80)
        await _insert_session(db_mod.DB_PATH, "s3", "inst-2", "connecting", 10, 20)

        resp = await client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_instances"] == 2
        assert data["total_sessions"] == 3
        assert data["active_sessions"] == 2  # connected + connecting
        assert data["total_input_tokens"] == 160  # 100 + 50 + 10
        assert data["total_output_tokens"] == 300  # 200 + 80 + 20

    async def test_stats_active_sessions_only_counts_connecting_and_connected(self, client):
        """Only 'connecting' and 'connected' count as active sessions."""
        await _insert_instance(db_mod.DB_PATH, "inst-1", "Instance A")

        await _insert_session(db_mod.DB_PATH, "s1", "inst-1", "connecting", 0, 0)
        await _insert_session(db_mod.DB_PATH, "s2", "inst-1", "connected", 0, 0)
        await _insert_session(db_mod.DB_PATH, "s3", "inst-1", "completed", 0, 0)
        await _insert_session(db_mod.DB_PATH, "s4", "inst-1", "error", 0, 0)
        await _insert_session(db_mod.DB_PATH, "s5", "inst-1", "cancelled", 0, 0)

        resp = await client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_sessions"] == 2


class TestUsageByInstance:
    """Tests for GET /api/dashboard/usage-by-instance."""

    async def test_usage_empty_db(self, client):
        """Returns empty list when no instances exist."""
        resp = await client.get("/api/dashboard/usage-by-instance")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_usage_instance_with_no_sessions(self, client):
        """Returns instance with zero counts when it has no sessions."""
        await _insert_instance(db_mod.DB_PATH, "inst-1", "Instance A")

        resp = await client.get("/api/dashboard/usage-by-instance")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["instance_id"] == "inst-1"
        assert data[0]["instance_name"] == "Instance A"
        assert data[0]["session_count"] == 0
        assert data[0]["total_input_tokens"] == 0
        assert data[0]["total_output_tokens"] == 0

    async def test_usage_multiple_instances_with_sessions(self, client):
        """Returns correct per-instance aggregation."""
        await _insert_instance(db_mod.DB_PATH, "inst-1", "Instance A")
        await _insert_instance(db_mod.DB_PATH, "inst-2", "Instance B")

        await _insert_session(db_mod.DB_PATH, "s1", "inst-1", "completed", 100, 200)
        await _insert_session(db_mod.DB_PATH, "s2", "inst-1", "completed", 50, 100)
        await _insert_session(db_mod.DB_PATH, "s3", "inst-2", "completed", 30, 60)

        resp = await client.get("/api/dashboard/usage-by-instance")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        # Results ordered by instance name
        inst_a = next(d for d in data if d["instance_name"] == "Instance A")
        inst_b = next(d for d in data if d["instance_name"] == "Instance B")

        assert inst_a["session_count"] == 2
        assert inst_a["total_input_tokens"] == 150
        assert inst_a["total_output_tokens"] == 300

        assert inst_b["session_count"] == 1
        assert inst_b["total_input_tokens"] == 30
        assert inst_b["total_output_tokens"] == 60
