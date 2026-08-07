"""Integration tests for Instance type handling via the REST API.

Covers the instance-type behavior added by the Azure OpenAI Testing Platform:

- Creating an instance with a valid type returns 201 and the type round-trips.
- Creating without ``type`` (or with an invalid value) returns 422.
- ``GET /api/instances?type=chat`` filters by type.
- ``PUT`` cannot change an instance's type (type is immutable).
- ``GET /api/instances/{id}`` returns a masked API key and the correct type.

Requirements: 1.1, 1.2, 1.7, 1.8, 9.3
"""

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


def _payload(name: str, type_: str, **overrides) -> dict:
    """Build a valid instance-create payload with the given name and type."""
    data = {
        "name": name,
        "endpoint": "https://ep.openai.azure.com",
        "api_key": "sk-secret-abcd1234",
        "deployment": "dep",
        "type": type_,
    }
    data.update(overrides)
    return data


class TestCreateWithType:
    """Requirement 1.1: instance type persists and round-trips."""

    @pytest.mark.parametrize("type_", ["voice", "chat", "image"])
    async def test_create_valid_type_roundtrips(self, client, type_):
        """Creating with a valid type returns 201 and the type round-trips."""
        create_resp = await client.post("/api/instances", json=_payload(f"inst-{type_}", type_))
        assert create_resp.status_code == 201
        assert create_resp.json()["type"] == type_

        instance_id = create_resp.json()["id"]

        # Round-trips via detail endpoint
        detail_resp = await client.get(f"/api/instances/{instance_id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["type"] == type_

        # Round-trips via list endpoint
        list_resp = await client.get("/api/instances")
        assert list_resp.status_code == 200
        entry = next(i for i in list_resp.json() if i["id"] == instance_id)
        assert entry["type"] == type_


class TestCreateTypeValidation:
    """Requirement 1.2: missing or invalid type is rejected with 422."""

    async def test_create_without_type_returns_422(self, client):
        """Omitting the required ``type`` field returns 422."""
        resp = await client.post(
            "/api/instances",
            json={
                "name": "no-type",
                "endpoint": "https://ep.openai.azure.com",
                "api_key": "sk-secret-abcd1234",
                "deployment": "dep",
            },
        )
        assert resp.status_code == 422

    async def test_create_invalid_type_returns_422(self, client):
        """An unsupported ``type`` value returns 422."""
        resp = await client.post("/api/instances", json=_payload("bad-type", "audio"))
        assert resp.status_code == 422


class TestFilterByType:
    """Requirement 1.8: listing filters by type."""

    async def test_filter_returns_only_matching_type(self, client):
        """GET /api/instances?type=chat returns only chat instances."""
        # Create a mix of types
        await client.post("/api/instances", json=_payload("voice-1", "voice"))
        await client.post("/api/instances", json=_payload("chat-1", "chat"))
        await client.post("/api/instances", json=_payload("chat-2", "chat"))
        await client.post("/api/instances", json=_payload("image-1", "image"))

        resp = await client.get("/api/instances?type=chat")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert {i["name"] for i in data} == {"chat-1", "chat-2"}
        assert all(i["type"] == "chat" for i in data)

        # Sanity: no filter returns everything
        all_resp = await client.get("/api/instances")
        assert len(all_resp.json()) == 4

    async def test_filter_no_match_returns_empty(self, client):
        """Filtering by a type with no instances returns an empty list."""
        await client.post("/api/instances", json=_payload("voice-only", "voice"))
        resp = await client.get("/api/instances?type=image")
        assert resp.status_code == 200
        assert resp.json() == []


class TestTypeImmutable:
    """Requirement 1.7: type is immutable after creation."""

    async def test_update_does_not_change_type(self, client):
        """PUT updates other fields but leaves the type unchanged.

        InstanceUpdate has no ``type`` field, so even sending one in the body
        must not alter the stored type.
        """
        create_resp = await client.post("/api/instances", json=_payload("chat-inst", "chat"))
        instance_id = create_resp.json()["id"]

        # Attempt to change type alongside a legitimate field update.
        resp = await client.put(
            f"/api/instances/{instance_id}",
            json={"description": "updated", "type": "image"},
        )
        assert resp.status_code == 200
        assert resp.json()["type"] == "chat"
        assert resp.json()["description"] == "updated"

        # Confirm persisted type is still the original.
        detail_resp = await client.get(f"/api/instances/{instance_id}")
        assert detail_resp.json()["type"] == "chat"


class TestDetailMaskingAndType:
    """Requirements 9.3 & 1.1: detail returns masked key and correct type."""

    async def test_detail_masks_key_and_returns_type(self, client):
        """GET /{id} returns api_key_masked (last 4 preserved) and the type."""
        create_resp = await client.post(
            "/api/instances",
            json=_payload("masked-inst", "image", api_key="sk-super-secret-9876"),
        )
        instance_id = create_resp.json()["id"]

        resp = await client.get(f"/api/instances/{instance_id}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["type"] == "image"
        # Last 4 characters preserved, everything else masked.
        assert data["api_key_masked"].endswith("9876")
        assert data["api_key_masked"] == "*" * (len("sk-super-secret-9876") - 4) + "9876"
        # The full key is never exposed.
        assert "sk-super-secret-9876" != data["api_key_masked"]
        assert "api_key" not in data
