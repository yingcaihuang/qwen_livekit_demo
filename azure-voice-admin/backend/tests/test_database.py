"""Tests for database initialization and connection management."""

import os
import tempfile
from pathlib import Path

import pytest
import aiosqlite

# Set a temp DB path before importing database module
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")

from app.database import init_db, get_db, DB_PATH  # noqa: E402
import app.database as db_mod  # noqa: E402

# Override the module-level DB_PATH for tests
db_mod.DB_PATH = os.environ["DB_PATH"]


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    """Use a fresh temp database for each test."""
    test_db = str(tmp_path / "test.db")
    db_mod.DB_PATH = test_db
    await init_db()
    yield
    # Cleanup
    if Path(test_db).exists():
        Path(test_db).unlink()


class TestInitDb:
    """Tests for init_db function."""

    async def test_creates_data_directory(self, tmp_path):
        """init_db creates the parent directory if it doesn't exist."""
        nested_path = str(tmp_path / "nested" / "dir" / "test.db")
        db_mod.DB_PATH = nested_path
        await init_db()
        assert Path(nested_path).exists()

    async def test_creates_instances_table(self, tmp_path):
        """init_db creates the instances table."""
        async with aiosqlite.connect(db_mod.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='instances'"
            )
            result = await cursor.fetchone()
            assert result is not None

    async def test_creates_sessions_table(self, tmp_path):
        """init_db creates the sessions table."""
        async with aiosqlite.connect(db_mod.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
            )
            result = await cursor.fetchone()
            assert result is not None

    async def test_creates_session_logs_table(self, tmp_path):
        """init_db creates the session_logs table."""
        async with aiosqlite.connect(db_mod.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='session_logs'"
            )
            result = await cursor.fetchone()
            assert result is not None

    async def test_creates_indexes(self, tmp_path):
        """init_db creates expected indexes."""
        expected_indexes = [
            "idx_sessions_instance_id",
            "idx_sessions_start_time",
            "idx_session_logs_session_id",
            "idx_session_logs_event_type",
        ]
        async with aiosqlite.connect(db_mod.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            )
            indexes = await cursor.fetchall()
            index_names = [i[0] for i in indexes]
            for expected in expected_indexes:
                assert expected in index_names

    async def test_enables_wal_mode(self, tmp_path):
        """init_db enables WAL journal mode."""
        async with aiosqlite.connect(db_mod.DB_PATH) as db:
            cursor = await db.execute("PRAGMA journal_mode")
            result = await cursor.fetchone()
            assert result[0] == "wal"

    async def test_is_idempotent(self, tmp_path):
        """init_db can be called multiple times without error."""
        # Already called once in fixture, call again
        await init_db()
        # Should still work
        async with aiosqlite.connect(db_mod.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='instances'"
            )
            result = await cursor.fetchone()
            assert result is not None


class TestGetDb:
    """Tests for get_db dependency."""

    async def test_returns_connection(self, tmp_path):
        """get_db yields a working database connection."""
        async for db in get_db():
            cursor = await db.execute("SELECT 1")
            result = await cursor.fetchone()
            assert result[0] == 1

    async def test_enables_foreign_keys(self, tmp_path):
        """get_db enables foreign key enforcement."""
        async for db in get_db():
            cursor = await db.execute("PRAGMA foreign_keys")
            result = await cursor.fetchone()
            assert result[0] == 1

    async def test_uses_row_factory(self, tmp_path):
        """get_db sets row_factory to aiosqlite.Row."""
        async for db in get_db():
            assert db.row_factory == aiosqlite.Row
