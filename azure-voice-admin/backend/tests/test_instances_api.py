"""Integration tests for the Instance REST API endpoints."""

import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

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


class TestListInstances:
    """Tests for GET /api/instances."""

    async def test_list_empty(self, client):
        """Returns empty list when no instances exist."""
        resp = await client.get("/api/instances")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_after_create(self, client):
        """Returns created instances."""
        await client.post(
            "/api/instances",
            json={
                "name": "inst-1",
                "endpoint": "https://ep.com",
                "api_key": "key-123",
                "deployment": "dep-1",
                "type": "voice",
            },
        )
        resp = await client.get("/api/instances")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "inst-1"
        # API key should not be in the list response
        assert "api_key" not in data[0]
        assert "api_key_masked" not in data[0]


class TestCreateInstance:
    """Tests for POST /api/instances."""

    async def test_create_success(self, client):
        """Successfully creates an instance and returns 201."""
        resp = await client.post(
            "/api/instances",
            json={
                "name": "new-instance",
                "endpoint": "https://test.openai.azure.com",
                "api_key": "sk-abc123",
                "deployment": "gpt-4o-realtime",
                "type": "voice",
                "description": "My test instance",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "new-instance"
        assert data["endpoint"] == "https://test.openai.azure.com"
        assert data["deployment"] == "gpt-4o-realtime"
        assert data["description"] == "My test instance"
        assert "id" in data
        assert "created_at" in data

    async def test_create_validation_error_empty_endpoint(self, client):
        """Returns 422 when endpoint is empty."""
        resp = await client.post(
            "/api/instances",
            json={
                "name": "test",
                "endpoint": "",
                "api_key": "key",
                "deployment": "dep",
                "type": "voice",
            },
        )
        assert resp.status_code == 422

    async def test_create_validation_error_empty_api_key(self, client):
        """Returns 422 when api_key is empty."""
        resp = await client.post(
            "/api/instances",
            json={
                "name": "test",
                "endpoint": "https://ep.com",
                "api_key": "  ",
                "deployment": "dep",
                "type": "voice",
            },
        )
        assert resp.status_code == 422

    async def test_create_duplicate_name(self, client):
        """Returns 409 when instance name already exists."""
        payload = {
            "name": "dup-name",
            "endpoint": "https://ep.com",
            "api_key": "key",
            "deployment": "dep",
            "type": "voice",
        }
        resp1 = await client.post("/api/instances", json=payload)
        assert resp1.status_code == 201

        resp2 = await client.post("/api/instances", json=payload)
        assert resp2.status_code == 409


class TestGetInstance:
    """Tests for GET /api/instances/{id}."""

    async def test_get_existing(self, client):
        """Returns instance detail with masked API key."""
        create_resp = await client.post(
            "/api/instances",
            json={
                "name": "detail-inst",
                "endpoint": "https://ep.com",
                "api_key": "sk-secret-key-12345",
                "deployment": "dep",
                "type": "voice",
            },
        )
        instance_id = create_resp.json()["id"]

        resp = await client.get(f"/api/instances/{instance_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "detail-inst"
        assert data["api_key_masked"].endswith("2345")
        assert "***" in data["api_key_masked"]
        assert data["total_sessions"] == 0
        assert data["total_input_tokens"] == 0
        assert data["total_output_tokens"] == 0

    async def test_get_nonexistent(self, client):
        """Returns 404 for non-existent instance."""
        resp = await client.get("/api/instances/nonexistent-id")
        assert resp.status_code == 404


class TestUpdateInstance:
    """Tests for PUT /api/instances/{id}."""

    async def test_update_success(self, client):
        """Successfully updates instance fields."""
        create_resp = await client.post(
            "/api/instances",
            json={
                "name": "orig-name",
                "endpoint": "https://ep.com",
                "api_key": "key",
                "deployment": "dep",
                "type": "voice",
            },
        )
        instance_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/instances/{instance_id}",
            json={"name": "updated-name", "description": "Updated desc"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "updated-name"
        assert data["description"] == "Updated desc"

    async def test_update_nonexistent(self, client):
        """Returns 404 for non-existent instance."""
        resp = await client.put("/api/instances/no-such-id", json={"name": "new"})
        assert resp.status_code == 404

    async def test_update_duplicate_name(self, client):
        """Returns 409 when renaming to an existing name."""
        await client.post(
            "/api/instances",
            json={
                "name": "name-a",
                "endpoint": "https://ep.com",
                "api_key": "key",
                "deployment": "dep",
                "type": "voice",
            },
        )
        create_resp = await client.post(
            "/api/instances",
            json={
                "name": "name-b",
                "endpoint": "https://ep2.com",
                "api_key": "key2",
                "deployment": "dep2",
                "type": "voice",
            },
        )
        instance_id = create_resp.json()["id"]

        resp = await client.put(f"/api/instances/{instance_id}", json={"name": "name-a"})
        assert resp.status_code == 409


class TestDeleteInstance:
    """Tests for DELETE /api/instances/{id}."""

    async def test_delete_success(self, client):
        """Successfully deletes and returns 204."""
        create_resp = await client.post(
            "/api/instances",
            json={
                "name": "to-delete",
                "endpoint": "https://ep.com",
                "api_key": "key",
                "deployment": "dep",
                "type": "voice",
            },
        )
        instance_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/instances/{instance_id}")
        assert resp.status_code == 204

        # Verify it's gone
        get_resp = await client.get(f"/api/instances/{instance_id}")
        assert get_resp.status_code == 404

    async def test_delete_nonexistent(self, client):
        """Returns 404 for non-existent instance."""
        resp = await client.delete("/api/instances/no-such-id")
        assert resp.status_code == 404

    async def test_delete_with_active_session(self, client):
        """Returns 409 when instance has active sessions."""
        import aiosqlite

        create_resp = await client.post(
            "/api/instances",
            json={
                "name": "active-inst",
                "endpoint": "https://ep.com",
                "api_key": "key",
                "deployment": "dep",
                "type": "voice",
            },
        )
        instance_id = create_resp.json()["id"]

        # Directly insert an active session into the DB
        async with aiosqlite.connect(db_mod.DB_PATH) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                """
                INSERT INTO sessions (id, instance_id, room_name, status, start_time)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                ("sess-1", instance_id, "room-1", "connected"),
            )
            await db.commit()

        resp = await client.delete(f"/api/instances/{instance_id}")
        assert resp.status_code == 409
