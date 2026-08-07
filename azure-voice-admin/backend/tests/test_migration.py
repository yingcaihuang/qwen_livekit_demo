"""Migration idempotency tests for the voice-only -> multi-type schema upgrade.

Property 16: 迁移幂等且默认归类为 voice
    For any pre-existing voice-only database, running the migration once or
    multiple times SHALL be idempotent (no failure, no duplicate schema), SHALL
    preserve all existing rows, and SHALL set the type of every pre-existing
    instance to 'voice'.

Validates: Requirements 8.1, 8.2, 8.3, 8.4, 6.6
"""

import os
import tempfile
from pathlib import Path

import aiosqlite
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Set a temp DB path before importing the database module (matches existing
# test conventions in test_database.py / test_instance_service.py).
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")

import app.database as db_mod  # noqa: E402
from app.database import init_db  # noqa: E402

# The old voice-only schema: an `instances` table WITHOUT the `type` column and
# WITHOUT the `image_generations` table. Mirrors the pre-upgrade production DB.
_OLD_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS instances (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    api_key TEXT NOT NULL,
    deployment TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    instance_id TEXT NOT NULL REFERENCES instances(id),
    room_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'connecting',
    start_time TEXT NOT NULL DEFAULT (datetime('now')),
    end_time TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    error_message TEXT
);

-- An early session_messages table WITHOUT the per-assistant-turn model /
-- endpoint columns. The migration must add these idempotently to pre-existing
-- databases (both nullable, so old messages keep NULL).
CREATE TABLE IF NOT EXISTS session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

-- An early image_generations table WITHOUT the performance timing columns
-- (started_at / ended_at / duration_ms / ttfb_ms). The migration must add
-- these idempotently to pre-existing databases.
CREATE TABLE IF NOT EXISTS image_generations (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    instance_id TEXT NOT NULL,
    session_id TEXT,
    prompt TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    size TEXT,
    quality TEXT,
    output_format TEXT,
    compression INTEGER,
    n INTEGER DEFAULT 1,
    has_reference INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    image_paths TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'completed',
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Performance timing columns added to image_generations by the migration.
_TIMING_COLUMNS = {"started_at", "ended_at", "duration_ms", "ttfb_ms"}

# Per-assistant-turn columns added to session_messages by the migration.
_MESSAGE_COLUMNS = {"model", "endpoint"}


async def _build_old_db(db_path: str, legacy_rows: list[dict]) -> None:
    """Create a temp DB with the OLD voice-only schema and seed legacy rows."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_OLD_SCHEMA_SQL)
        for row in legacy_rows:
            await db.execute(
                """
                INSERT INTO instances (id, name, endpoint, api_key, deployment, description)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["name"],
                    row["endpoint"],
                    row["api_key"],
                    row["deployment"],
                    row.get("description", ""),
                ),
            )
        await db.commit()


async def _column_names(db: aiosqlite.Connection, table: str) -> set[str]:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    return {r[1] for r in await cursor.fetchall()}


async def _table_exists(db: aiosqlite.Connection, table: str) -> bool:
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return await cursor.fetchone() is not None


class TestMigrationIntegration:
    """Deterministic integration test for the voice-only -> multi-type migration."""

    async def test_migrate_old_voice_db_preserves_and_defaults_to_voice(self, tmp_path):
        """Running init_db against an old voice-only DB migrates it in place.

        Asserts: type column added, all legacy rows default to 'voice', legacy
        data preserved, image_generations table created, and repeated init_db
        calls remain idempotent with data intact.

        Validates: Requirements 8.1, 8.2, 8.3, 8.4, 6.6
        """
        test_db = str(tmp_path / "legacy.db")
        legacy_rows = [
            {
                "id": "inst-1",
                "name": "legacy-voice-1",
                "endpoint": "https://ep1.openai.azure.com",
                "api_key": "sk-legacy-key-0001",
                "deployment": "gpt-4o-realtime",
                "description": "first legacy instance",
            },
            {
                "id": "inst-2",
                "name": "legacy-voice-2",
                "endpoint": "https://ep2.openai.azure.com",
                "api_key": "sk-legacy-key-0002",
                "deployment": "gpt-4o-realtime",
                "description": "",
            },
        ]
        await _build_old_db(test_db, legacy_rows)

        # Sanity: the old DB really lacks the new column and the timing columns.
        async with aiosqlite.connect(test_db) as db:
            assert "type" not in await _column_names(db, "instances")
            # The old image_generations table exists but WITHOUT timing columns.
            assert await _table_exists(db, "image_generations")
            assert not (_TIMING_COLUMNS & await _column_names(db, "image_generations"))
            # The old session_messages table exists but WITHOUT model/endpoint.
            assert await _table_exists(db, "session_messages")
            assert not (_MESSAGE_COLUMNS & await _column_names(db, "session_messages"))

        db_mod.DB_PATH = test_db

        # Run migration three times to exercise idempotency (8.3).
        await init_db()
        await init_db()
        await init_db()

        async with aiosqlite.connect(test_db) as db:
            db.row_factory = aiosqlite.Row

            # 8.1: the `type` column now exists on instances.
            assert "type" in await _column_names(db, "instances")

            # 8.3: image_generations table now exists.
            assert await _table_exists(db, "image_generations")

            # Performance timing columns were added to the pre-existing
            # image_generations table (idempotent ALTER TABLE migration).
            assert _TIMING_COLUMNS <= await _column_names(db, "image_generations")

            # model/endpoint columns were added to the pre-existing
            # session_messages table (idempotent ALTER TABLE migration).
            assert _MESSAGE_COLUMNS <= await _column_names(db, "session_messages")

            cursor = await db.execute(
                "SELECT id, name, endpoint, api_key, deployment, description, type "
                "FROM instances ORDER BY id"
            )
            rows = await cursor.fetchall()

            # 8.4 / 6.6: no data loss — same number of rows preserved.
            assert len(rows) == len(legacy_rows)

            by_id = {r["id"]: r for r in rows}
            for original in legacy_rows:
                migrated = by_id[original["id"]]
                # 8.2: every pre-existing row is classified as 'voice'.
                assert migrated["type"] == "voice"
                # 8.4 / 6.6: existing field values are preserved unchanged.
                assert migrated["name"] == original["name"]
                assert migrated["endpoint"] == original["endpoint"]
                assert migrated["api_key"] == original["api_key"]
                assert migrated["deployment"] == original["deployment"]
                assert migrated["description"] == original["description"]

    async def test_migrate_empty_old_db_is_safe(self, tmp_path):
        """Migrating an old DB with zero legacy rows succeeds and is idempotent."""
        test_db = str(tmp_path / "empty_legacy.db")
        await _build_old_db(test_db, [])

        db_mod.DB_PATH = test_db
        await init_db()
        await init_db()

        async with aiosqlite.connect(test_db) as db:
            assert "type" in await _column_names(db, "instances")
            assert await _table_exists(db, "image_generations")
            assert _TIMING_COLUMNS <= await _column_names(db, "image_generations")
            assert _MESSAGE_COLUMNS <= await _column_names(db, "session_messages")
            cursor = await db.execute("SELECT COUNT(*) FROM instances")
            assert (await cursor.fetchone())[0] == 0


# Strategy for legacy instance names: non-empty, no NUL, unique-able identifiers.
_name_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1,
    max_size=40,
)


class TestMigrationProperty16:
    """Property 16: 迁移幂等且默认归类为 voice."""

    @settings(
        max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(names=st.lists(_name_text, min_size=0, max_size=8, unique=True))
    async def test_property16_all_legacy_rows_default_to_voice_idempotently(self, tmp_path, names):
        """For a variable number of legacy rows, migration is idempotent and
        classifies every pre-existing instance as 'voice' without data loss.

        Validates: Requirements 8.1, 8.2, 8.3, 8.4, 6.6
        """
        test_db = str(tmp_path / "prop_legacy.db")
        # Remove any leftover DB from a previous Hypothesis example.
        for suffix in ("", "-wal", "-shm"):
            p = Path(test_db + suffix)
            if p.exists():
                p.unlink()

        legacy_rows = [
            {
                "id": f"id-{i}",
                "name": name,
                "endpoint": f"https://ep-{i}.openai.azure.com",
                "api_key": f"sk-key-{i:04d}",
                "deployment": "gpt-4o-realtime",
                "description": f"desc-{i}",
            }
            for i, name in enumerate(names)
        ]
        await _build_old_db(test_db, legacy_rows)

        db_mod.DB_PATH = test_db

        # Idempotency: run migration twice.
        await init_db()
        await init_db()

        async with aiosqlite.connect(test_db) as db:
            db.row_factory = aiosqlite.Row
            assert "type" in await _column_names(db, "instances")
            assert await _table_exists(db, "image_generations")

            cursor = await db.execute("SELECT id, name, type FROM instances")
            rows = await cursor.fetchall()
            # No data loss.
            assert len(rows) == len(legacy_rows)
            # Every pre-existing row classified as 'voice'.
            assert all(r["type"] == "voice" for r in rows)
            # Names preserved.
            assert {r["name"] for r in rows} == {row["name"] for row in legacy_rows}
