"""Integration/smoke tests for the Unified History API (GET /api/history).

Seeds a mix of voice / chat / image rows directly into a temp DB (no Azure
needed) and asserts merged ordering (Req 6.1), type/instance filtering
(Req 6.3, 6.4), pagination, title derivation, and that existing voice sessions
remain accessible (Req 6.6).
"""

import os
import tempfile
from pathlib import Path

import aiosqlite
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


async def _insert_instance(db_path: str, instance_id: str, name: str, type_: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            INSERT INTO instances (id, name, endpoint, api_key, deployment, type, created_at, updated_at)
            VALUES (?, ?, 'https://ep.com', 'key-12345', 'dep', ?, datetime('now'), datetime('now'))
            """,
            (instance_id, name, type_),
        )
        await db.commit()


async def _insert_session(
    db_path: str,
    session_id: str,
    instance_id: str,
    room_name: str,
    start_time: str,
    status: str = "completed",
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            INSERT INTO sessions (id, instance_id, room_name, status, start_time, input_tokens, output_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, instance_id, room_name, status, start_time, input_tokens, output_tokens),
        )
        await db.commit()


async def _insert_message(db_path: str, session_id: str, role: str, content: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            INSERT INTO session_messages (session_id, role, content, timestamp)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (session_id, role, content),
        )
        await db.commit()


async def _insert_image(
    db_path: str,
    generation_id: str,
    instance_id: str,
    prompt: str,
    created_at: str,
    status: str = "completed",
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            INSERT INTO image_generations (id, instance_id, prompt, status, input_tokens, output_tokens, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (generation_id, instance_id, prompt, status, input_tokens, output_tokens, created_at),
        )
        await db.commit()


async def _seed_mix(db_path: str) -> None:
    """Seed one voice session, one chat session (with a user message), one image."""
    await _insert_instance(db_path, "inst-v", "Voice Inst", "voice")
    await _insert_instance(db_path, "inst-c", "Chat Inst", "chat")
    await _insert_instance(db_path, "inst-i", "Image Inst", "image")

    # Distinct start_times so ordering is deterministic: image newest, then chat, then voice.
    await _insert_session(
        db_path,
        "s-v",
        "inst-v",
        "room-abc",
        "2024-01-01 10:00:00",
        status="completed",
        input_tokens=5,
        output_tokens=7,
    )
    await _insert_session(
        db_path,
        "s-c",
        "inst-c",
        "",
        "2024-01-02 10:00:00",
        status="active",
        input_tokens=11,
        output_tokens=13,
    )
    await _insert_message(db_path, "s-c", "user", "Hello chat world")
    await _insert_message(db_path, "s-c", "assistant", "Hi there")
    await _insert_image(
        db_path,
        "g-1",
        "inst-i",
        "A serene mountain lake",
        "2024-01-03 10:00:00",
        status="completed",
        input_tokens=3,
        output_tokens=0,
    )


class TestUnifiedHistory:
    async def test_empty_db(self, client):
        resp = await client.get("/api/history")
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}

    async def test_merged_ordering_and_titles(self, client):
        """Merged result is start_time DESC; titles derive per type (Req 6.1)."""
        await _seed_mix(db_mod.DB_PATH)

        resp = await client.get("/api/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3

        items = data["items"]
        assert [i["type"] for i in items] == ["image", "chat", "voice"]

        # start_time strictly descending
        starts = [i["start_time"] for i in items]
        assert starts == sorted(starts, reverse=True)

        by_type = {i["type"]: i for i in items}
        assert by_type["image"]["title"] == "A serene mountain lake"
        assert by_type["chat"]["title"] == "Hello chat world"  # first user message
        assert by_type["voice"]["title"] == "room-abc"  # room_name

        # token + status passthrough
        assert by_type["chat"]["input_tokens"] == 11
        assert by_type["chat"]["output_tokens"] == 13
        assert by_type["voice"]["status"] == "completed"

    async def test_filter_by_type(self, client):
        await _seed_mix(db_mod.DB_PATH)

        for t in ("voice", "chat", "image"):
            resp = await client.get(f"/api/history?type={t}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert all(i["type"] == t for i in data["items"])

    async def test_filter_by_instance(self, client):
        await _seed_mix(db_mod.DB_PATH)

        resp = await client.get("/api/history?instance_id=inst-c")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["instance_id"] == "inst-c"
        assert data["items"][0]["type"] == "chat"

    async def test_pagination(self, client):
        await _seed_mix(db_mod.DB_PATH)

        p1 = (await client.get("/api/history?page=1&page_size=2")).json()
        assert p1["total"] == 3
        assert len(p1["items"]) == 2
        assert [i["type"] for i in p1["items"]] == ["image", "chat"]

        p2 = (await client.get("/api/history?page=2&page_size=2")).json()
        assert p2["total"] == 3
        assert len(p2["items"]) == 1
        assert p2["items"][0]["type"] == "voice"

    async def test_unknown_type_returns_empty(self, client):
        await _seed_mix(db_mod.DB_PATH)

        resp = await client.get("/api/history?type=bogus")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    async def test_voice_sessions_preserved(self, client):
        """Existing voice sessions remain accessible (Req 6.6)."""
        await _insert_instance(db_mod.DB_PATH, "inst-v", "Voice Inst", "voice")
        await _insert_session(
            db_mod.DB_PATH,
            "s-old",
            "inst-v",
            "legacy-room",
            "2023-06-01 09:00:00",
            status="completed",
            input_tokens=1,
            output_tokens=2,
        )

        resp = await client.get("/api/history")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == "s-old"
        assert data["items"][0]["type"] == "voice"
        assert data["items"][0]["title"] == "legacy-room"
