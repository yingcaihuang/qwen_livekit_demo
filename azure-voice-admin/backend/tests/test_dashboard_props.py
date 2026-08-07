"""Property-based tests for unified dashboard aggregation (Task 8.3).

Covers the following correctness properties from the design doc:

- Property 15: 仪表盘跨类型聚合正确性
    Validates: Requirements 7.1, 7.3, 7.5
- Property 4:  按类型筛选正确性 (dashboard facet)
    Validates: Requirements 7.2

The aggregation service under test lives in ``app/services/dashboard_service.py``:
``compute_stats``, ``compute_usage_by_instance`` and ``compute_usage_by_type``.

Rows are seeded directly via aiosqlite into a temp database created from the
production schema (``init_db`` against a temp DB_PATH), following the
conventions in test_dashboard_api.py / test_instance_type.py. The service
functions are called directly against an open aiosqlite connection.

Note on iteration counts: the DB-seeding property tests insert several rows per
example, so they run 40 Hypothesis examples (within the 30-50 range acceptable
for DB-heavy tests). The empty-DB test is DB-light and does not need parameters.
"""

import os
import tempfile
import uuid
from pathlib import Path

import aiosqlite
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Set a temp DB path before importing the database module (matches existing
# test conventions in test_dashboard_api.py / test_instance_type.py).
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")

import app.database as db_mod  # noqa: E402
from app.database import init_db  # noqa: E402
from app.services.dashboard_service import (  # noqa: E402
    compute_stats,
    compute_usage_by_instance,
    compute_usage_by_type,
)

VALID_TYPES = ("voice", "chat", "image")
_SESSION_TYPES = ("voice", "chat")

# Token counts: non-negative integers with a bounded range.
_token = st.integers(min_value=0, max_value=10_000)

# DB-seeding property settings: 40 examples (30-50 range acceptable for
# DB-heavy tests), no deadline (DB IO varies), reuse the function-scoped DB
# fixture across examples.
_pbt_settings = settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    """Use a fresh temp database (real schema) for each test function."""
    test_db = str(tmp_path / "test.db")
    db_mod.DB_PATH = test_db
    await init_db()
    yield
    for suffix in ("", "-wal", "-shm"):
        p = Path(test_db + suffix)
        if p.exists():
            p.unlink()


@pytest.fixture
async def db():
    """Provide a database connection bound to the current test DB."""
    async with aiosqlite.connect(db_mod.DB_PATH) as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn


@st.composite
def _dashboard_scenario(draw):
    """Generate a random mix of instances, sessions and image generations.

    Returns a tuple ``(instances, sessions, images)`` where:
      - ``instances`` is a list of ``(id, name, type)``
      - ``sessions``  is a list of ``(id, instance_id, input_tokens, output_tokens)``
        each attached to a ``voice``/``chat`` instance
      - ``images``    is a list of ``(id, instance_id, input_tokens, output_tokens)``
        each attached to an ``image`` instance
    """
    instances: list[tuple[str, str, str]] = []
    for itype in VALID_TYPES:
        for _ in range(draw(st.integers(min_value=0, max_value=3))):
            iid = uuid.uuid4().hex
            instances.append((iid, f"inst-{iid[:12]}", itype))

    session_instances = [i for i in instances if i[2] in _SESSION_TYPES]
    image_instances = [i for i in instances if i[2] == "image"]

    sessions: list[tuple[str, str, int, int]] = []
    if session_instances:
        for _ in range(draw(st.integers(min_value=0, max_value=8))):
            inst = draw(st.sampled_from(session_instances))
            sessions.append((uuid.uuid4().hex, inst[0], draw(_token), draw(_token)))

    images: list[tuple[str, str, int, int]] = []
    if image_instances:
        for _ in range(draw(st.integers(min_value=0, max_value=8))):
            inst = draw(st.sampled_from(image_instances))
            images.append((uuid.uuid4().hex, inst[0], draw(_token), draw(_token)))

    return instances, sessions, images


async def _clear(db: aiosqlite.Connection) -> None:
    """Reset all tables (the DB fixture persists across Hypothesis examples)."""
    for table in ("session_messages", "session_logs", "sessions", "image_generations", "instances"):
        await db.execute(f"DELETE FROM {table}")
    await db.commit()


async def _seed(db, instances, sessions, images) -> None:
    """Insert the generated scenario rows directly into the DB."""
    for iid, name, itype in instances:
        await db.execute(
            """
            INSERT INTO instances (id, name, endpoint, api_key, deployment, type, created_at, updated_at)
            VALUES (?, ?, 'https://ep.com', 'key-12345', 'dep', ?, datetime('now'), datetime('now'))
            """,
            (iid, name, itype),
        )
    for sid, inst_id, inp, out in sessions:
        await db.execute(
            """
            INSERT INTO sessions (id, instance_id, room_name, status, start_time, input_tokens, output_tokens)
            VALUES (?, ?, ?, 'completed', datetime('now'), ?, ?)
            """,
            (sid, inst_id, f"room-{sid}", inp, out),
        )
    for gid, inst_id, inp, out in images:
        await db.execute(
            """
            INSERT INTO image_generations (id, instance_id, prompt, input_tokens, output_tokens, created_at)
            VALUES (?, ?, 'a prompt', ?, ?, datetime('now'))
            """,
            (gid, inst_id, inp, out),
        )
    await db.commit()


def _type_of(instances, instance_id: str) -> str:
    for iid, _name, itype in instances:
        if iid == instance_id:
            return itype
    raise AssertionError(f"unknown instance id {instance_id}")


class TestProperty15DashboardAggregation:
    """Property 15: 仪表盘跨类型聚合正确性 (Validates: Requirements 7.1, 7.3, 7.5)."""

    async def test_property15_empty_db_yields_zeros(self, db):
        """An empty database yields zero totals rather than an error (Req 7.5)."""
        stats = await compute_stats(db)
        assert stats.total_instances == 0
        assert stats.total_sessions == 0
        assert stats.total_tests == 0
        assert stats.active_sessions == 0
        assert stats.total_input_tokens == 0
        assert stats.total_output_tokens == 0

        assert await compute_usage_by_instance(db) == []

        by_type = {u.type: u for u in await compute_usage_by_type(db)}
        assert set(by_type) == set(VALID_TYPES)
        for usage in by_type.values():
            assert usage.test_count == 0
            assert usage.total_input_tokens == 0
            assert usage.total_output_tokens == 0

    @_pbt_settings
    @given(scenario=_dashboard_scenario())
    async def test_property15_totals_equal_independent_sums(self, db, scenario):
        """compute_stats totals equal independently-computed sums (Req 7.1, 7.3)."""
        instances, sessions, images = scenario
        await _clear(db)
        await _seed(db, instances, sessions, images)

        expected_input = sum(s[2] for s in sessions) + sum(g[2] for g in images)
        expected_output = sum(s[3] for s in sessions) + sum(g[3] for g in images)

        stats = await compute_stats(db)
        assert stats.total_instances == len(instances)
        assert stats.total_sessions == len(sessions)
        assert stats.total_tests == len(sessions) + len(images)
        assert stats.total_input_tokens == expected_input
        assert stats.total_output_tokens == expected_output

    @_pbt_settings
    @given(scenario=_dashboard_scenario())
    async def test_property15_per_instance_sums_to_overall(self, db, scenario):
        """Per-instance aggregation sums consistently to the overall totals."""
        instances, sessions, images = scenario
        await _clear(db)
        await _seed(db, instances, sessions, images)

        stats = await compute_stats(db)
        per_instance = await compute_usage_by_instance(db)

        # Every instance appears exactly once.
        assert {u.instance_id for u in per_instance} == {i[0] for i in instances}
        # Combined per-instance test counts and token sums equal the overall.
        assert sum(u.session_count for u in per_instance) == stats.total_tests
        assert sum(u.total_input_tokens for u in per_instance) == stats.total_input_tokens
        assert sum(u.total_output_tokens for u in per_instance) == stats.total_output_tokens

        # Cross-check each instance against independently computed expectations.
        for iid, _name, _itype in instances:
            exp_count = sum(1 for s in sessions if s[1] == iid) + sum(
                1 for g in images if g[1] == iid
            )
            exp_in = sum(s[2] for s in sessions if s[1] == iid) + sum(
                g[2] for g in images if g[1] == iid
            )
            exp_out = sum(s[3] for s in sessions if s[1] == iid) + sum(
                g[3] for g in images if g[1] == iid
            )
            row = next(u for u in per_instance if u.instance_id == iid)
            assert row.session_count == exp_count
            assert row.total_input_tokens == exp_in
            assert row.total_output_tokens == exp_out

    @_pbt_settings
    @given(scenario=_dashboard_scenario())
    async def test_property15_per_type_sums_to_overall(self, db, scenario):
        """Per-type aggregation sums consistently to the overall totals."""
        instances, sessions, images = scenario
        await _clear(db)
        await _seed(db, instances, sessions, images)

        stats = await compute_stats(db)
        per_type = await compute_usage_by_type(db)

        assert {u.type for u in per_type} == set(VALID_TYPES)
        assert sum(u.test_count for u in per_type) == stats.total_tests
        assert sum(u.total_input_tokens for u in per_type) == stats.total_input_tokens
        assert sum(u.total_output_tokens for u in per_type) == stats.total_output_tokens


class TestProperty4DashboardFilterByType:
    """Property 4: 按类型筛选正确性 (dashboard facet) (Validates: Requirements 7.2)."""

    @_pbt_settings
    @given(scenario=_dashboard_scenario())
    async def test_property4_compute_stats_restricts_to_type(self, db, scenario):
        """compute_stats(type_filter=T) restricts totals to exactly type T."""
        instances, sessions, images = scenario
        await _clear(db)
        await _seed(db, instances, sessions, images)

        for t in VALID_TYPES:
            if t in _SESSION_TYPES:
                matching = [s for s in sessions if _type_of(instances, s[1]) == t]
            else:
                matching = images
            exp_count = len(matching)
            exp_in = sum(r[2] for r in matching)
            exp_out = sum(r[3] for r in matching)
            exp_instances = sum(1 for i in instances if i[2] == t)

            stats = await compute_stats(db, type_filter=t)
            assert stats.total_instances == exp_instances
            assert stats.total_tests == exp_count
            assert stats.total_sessions == (exp_count if t in _SESSION_TYPES else 0)
            assert stats.total_input_tokens == exp_in
            assert stats.total_output_tokens == exp_out

    @_pbt_settings
    @given(scenario=_dashboard_scenario())
    async def test_property4_usage_by_instance_restricts_to_type(self, db, scenario):
        """compute_usage_by_instance(type_filter=T) returns only type-T instances."""
        instances, sessions, images = scenario
        await _clear(db)
        await _seed(db, instances, sessions, images)

        for t in VALID_TYPES:
            expected_ids = {i[0] for i in instances if i[2] == t}
            rows = await compute_usage_by_instance(db, type_filter=t)
            assert {u.instance_id for u in rows} == expected_ids

    @_pbt_settings
    @given(scenario=_dashboard_scenario())
    async def test_property4_usage_by_type_matches_seeded_sums(self, db, scenario):
        """compute_usage_by_type entries match the per-type seeded sums."""
        instances, sessions, images = scenario
        await _clear(db)
        await _seed(db, instances, sessions, images)

        by_type = {u.type: u for u in await compute_usage_by_type(db)}
        assert set(by_type) == set(VALID_TYPES)

        for t in _SESSION_TYPES:
            matching = [s for s in sessions if _type_of(instances, s[1]) == t]
            assert by_type[t].test_count == len(matching)
            assert by_type[t].total_input_tokens == sum(r[2] for r in matching)
            assert by_type[t].total_output_tokens == sum(r[3] for r in matching)

        assert by_type["image"].test_count == len(images)
        assert by_type["image"].total_input_tokens == sum(g[2] for g in images)
        assert by_type["image"].total_output_tokens == sum(g[3] for g in images)
