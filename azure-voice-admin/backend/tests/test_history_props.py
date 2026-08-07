"""Property-based tests for the Unified History API (Task 7.3).

Covers the following correctness properties from the design doc
(``.kiro/specs/azure-openai-testing-platform/design.md``):

- Property 14: 统一历史按开始时间降序
    Validates: Requirements 6.1
- Property 4 (history facet): 按类型筛选正确性
    Validates: Requirements 6.3, 6.4

Both properties seed a *random* mix of voice / chat / image records with random
start_times directly into a temp SQLite DB (via ``init_db``) and exercise the
merged ``GET /api/history`` endpoint over an in-process ``httpx`` ASGI client
(same pattern as ``test_history_api.py``). These are property tests: they assert
universal invariants over randomized inputs rather than fixed example cases (the
merged-ordering / filter smoke cases live in ``test_history_api.py``).

Each Hypothesis example seeds several DB rows and issues real HTTP calls, so the
example count is kept modest (40) with ``deadline=None``; the function-scoped DB
fixture is reused across examples (health check suppressed) and rows are reset
between examples so every example starts from an empty history.
"""

import os
import tempfile
from pathlib import Path

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Set a temp DB path before importing the database module (mirrors the
# convention used across the other backend tests).
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")

import app.database as db_mod  # noqa: E402
from app.main import app  # noqa: E402

# Shared PBT settings for tests that seed DB rows + issue HTTP calls per example:
# a modest example count, no per-example deadline, and reuse of the
# function-scoped DB fixture across Hypothesis examples.
_http_settings = settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------
@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    """Use a fresh temp database (real schema) for each test function."""
    test_db = str(tmp_path / "test.db")
    db_mod.DB_PATH = test_db
    from app.database import init_db

    await init_db()
    yield
    for suffix in ("", "-wal", "-shm"):
        p = Path(test_db + suffix)
        if p.exists():
            p.unlink()


@pytest.fixture
async def client():
    """Provide an async HTTP client bound to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ----------------------------------------------------------------------------
# Seeding helpers (mirror test_history_api.py; write rows directly via aiosqlite)
# ----------------------------------------------------------------------------
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
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            INSERT INTO sessions (id, instance_id, room_name, status, start_time, input_tokens, output_tokens)
            VALUES (?, ?, ?, ?, ?, 0, 0)
            """,
            (session_id, instance_id, room_name, status, start_time),
        )
        await db.commit()


async def _insert_image(
    db_path: str,
    generation_id: str,
    instance_id: str,
    prompt: str,
    created_at: str,
    status: str = "completed",
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            INSERT INTO image_generations (id, instance_id, prompt, status, input_tokens, output_tokens, created_at)
            VALUES (?, ?, ?, ?, 0, 0, ?)
            """,
            (generation_id, instance_id, prompt, status, created_at),
        )
        await db.commit()


async def _reset(db_path: str) -> None:
    """Clear all seeded rows so each Hypothesis example starts empty."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM session_messages")
        await db.execute("DELETE FROM sessions")
        await db.execute("DELETE FROM image_generations")
        await db.execute("DELETE FROM instances")
        await db.commit()


async def _seed_scenario(db_path: str, instances: list[dict], records: list[dict]) -> None:
    """Seed the given instances and records directly into the temp DB.

    A record whose type is ``image`` becomes an ``image_generations`` row (its
    ``created_at`` is the shared start_time); ``voice``/``chat`` records become
    ``sessions`` rows joined to an instance of that type. The history ``id`` for
    a record is ``g-<idx>`` for images and ``s-<idx>`` for sessions.
    """
    for inst in instances:
        await _insert_instance(db_path, inst["id"], f"name-{inst['id']}", inst["type"])
    for r in records:
        if r["type"] == "image":
            await _insert_image(
                db_path, f"g-{r['idx']}", r["instance_id"], f"prompt-{r['idx']}", r["start_time"]
            )
        else:
            await _insert_session(
                db_path, f"s-{r['idx']}", r["instance_id"], f"room-{r['idx']}", r["start_time"]
            )


def _history_id(record: dict) -> str:
    """Return the id the history API assigns to a seeded record."""
    return f"g-{record['idx']}" if record["type"] == "image" else f"s-{record['idx']}"


# ----------------------------------------------------------------------------
# Scenario generator: a random pool of typed instances + a random mix of records
# ----------------------------------------------------------------------------
@st.composite
def _history_scenario(draw):
    """Draw (instances, records).

    Each instance gets a random type in {voice, chat, image}. Each record
    references one of those instances and inherits its type, so the history
    type reported for the record matches both its source table and its
    instance's declared type. start_times are drawn from a small pool of
    day/hour combinations so ties are common (exercising the id tiebreaker).
    """
    n_inst = draw(st.integers(min_value=1, max_value=4))
    instances = [
        {"id": f"inst-{k}", "type": draw(st.sampled_from(["voice", "chat", "image"]))}
        for k in range(n_inst)
    ]

    n_rec = draw(st.integers(min_value=0, max_value=12))
    records = []
    for j in range(n_rec):
        inst = draw(st.sampled_from(instances))
        day = draw(st.integers(min_value=1, max_value=9))
        hour = draw(st.integers(min_value=0, max_value=9))
        records.append(
            {
                "idx": j,
                "instance_id": inst["id"],
                "type": inst["type"],
                "start_time": f"2024-01-0{day} 0{hour}:00:00",
            }
        )
    return instances, records


# ----------------------------------------------------------------------------
# Property 14: 统一历史按开始时间降序 (Validates: Requirements 6.1)
# ----------------------------------------------------------------------------
class TestProperty14HistoryOrdering:
    """Property 14: 统一历史按开始时间降序 (Validates: Requirements 6.1)."""

    @_http_settings
    @given(scenario=_history_scenario())
    async def test_property14_start_time_strictly_descending(self, client, scenario):
        """A random voice/chat/image mix returns start_time-descending items.

        Every entry's ``start_time`` is >= the next entry's (most recent first),
        regardless of type, with ``id`` as the tiebreaker on equal start_times
        (matching ``ORDER BY start_time DESC, id DESC``). ``total`` equals the
        number of seeded records.
        """
        instances, records = scenario
        await _reset(db_mod.DB_PATH)
        await _seed_scenario(db_mod.DB_PATH, instances, records)

        # page_size large enough to return the whole seeded set in one page.
        resp = await client.get("/api/history?page=1&page_size=1000")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == len(records)
        items = data["items"]
        assert len(items) == len(records)

        # Composite (start_time, id) key must be STRICTLY descending: start_time
        # non-increasing, and id breaking ties in descending (text) order. ids
        # are unique, so the composite key is strictly descending overall.
        keys = [(i["start_time"], i["id"]) for i in items]
        for higher, lower in zip(keys, keys[1:], strict=False):
            assert higher > lower, f"ordering violated: {higher} !> {lower}"


# ----------------------------------------------------------------------------
# Property 4 (history facet): 按类型筛选正确性 (Validates: Requirements 6.3, 6.4)
# ----------------------------------------------------------------------------
class TestProperty4HistoryFiltering:
    """Property 4 (history facet): 按类型筛选正确性 (Req 6.3, 6.4)."""

    @_http_settings
    @given(scenario=_history_scenario())
    async def test_property4_type_filter_returns_exactly_matching_records(self, client, scenario):
        """``?type=T`` returns exactly the records of type T and none other."""
        instances, records = scenario
        await _reset(db_mod.DB_PATH)
        await _seed_scenario(db_mod.DB_PATH, instances, records)

        for t in ("voice", "chat", "image"):
            expected_ids = {_history_id(r) for r in records if r["type"] == t}

            resp = await client.get(f"/api/history?type={t}&page=1&page_size=1000")
            assert resp.status_code == 200
            data = resp.json()

            got_ids = {i["id"] for i in data["items"]}
            assert data["total"] == len(expected_ids)
            assert got_ids == expected_ids
            assert all(i["type"] == t for i in data["items"])

    @_http_settings
    @given(scenario=_history_scenario())
    async def test_property4_instance_filter_returns_exactly_matching_records(
        self, client, scenario
    ):
        """``?instance_id=X`` returns exactly the records for instance X (Req 6.4)."""
        instances, records = scenario
        await _reset(db_mod.DB_PATH)
        await _seed_scenario(db_mod.DB_PATH, instances, records)

        for inst in instances:
            expected_ids = {_history_id(r) for r in records if r["instance_id"] == inst["id"]}

            resp = await client.get(f"/api/history?instance_id={inst['id']}&page=1&page_size=1000")
            assert resp.status_code == 200
            data = resp.json()

            got_ids = {i["id"] for i in data["items"]}
            assert data["total"] == len(expected_ids)
            assert got_ids == expected_ids
            assert all(i["instance_id"] == inst["id"] for i in data["items"])
