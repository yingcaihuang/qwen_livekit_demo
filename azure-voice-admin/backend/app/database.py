"""Database connection management and initialization for Azure Voice Testing Admin."""

import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path

import aiosqlite

# Database file path from environment variable, default to ./data/voice_admin.db
DB_PATH = os.environ.get("DB_PATH", "./data/voice_admin.db")

# Path to the schema file
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_logger = logging.getLogger("azure_openai_admin")


async def _migrate(db: aiosqlite.Connection) -> None:
    """Apply idempotent backward-compatible migrations.

    This is the single place for schema migrations that cannot be expressed as
    ``CREATE ... IF NOT EXISTS`` in ``schema.sql`` (e.g. adding a column to a
    table that already exists in databases created by the old voice-only
    schema). Every migration here MUST be idempotent so repeated startups do
    not fail.

    Any exception raised here is expected to propagate to the caller so that
    startup halts rather than proceeding on a partially-migrated database.
    """
    # 1) instances.type — databases created by the old voice-only schema lack
    #    this column. SQLite has no "ADD COLUMN IF NOT EXISTS", so check first.
    cursor = await db.execute("PRAGMA table_info(instances)")
    columns = {row[1] for row in await cursor.fetchall()}
    if "type" not in columns:
        # NOT NULL + DEFAULT 'voice' backfills every pre-existing row to 'voice'.
        await db.execute("ALTER TABLE instances ADD COLUMN type TEXT NOT NULL DEFAULT 'voice'")

    # 2) image_generations and other new tables are created via IF NOT EXISTS
    #    in schema.sql (already idempotent), so no extra work is needed here.

    await db.commit()


async def init_db() -> None:
    """Initialize the database: create the data directory and execute schema.sql.

    This function is idempotent — all CREATE statements use IF NOT EXISTS, and
    ``_migrate`` guards its ALTER statements with existence checks.
    """
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(str(db_path)) as db:
        # Enable WAL mode for better concurrent read performance
        await db.execute("PRAGMA journal_mode=WAL")
        # Enable foreign key enforcement
        await db.execute("PRAGMA foreign_keys = ON")

        # Read and execute the schema (fresh DB path: creates tables with the
        # current column set; existing tables are left untouched via IF NOT EXISTS)
        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        await db.executescript(schema_sql)

        # Apply idempotent migrations for pre-existing (old-schema) databases.
        try:
            await _migrate(db)
        except Exception as exc:
            _logger.error(
                "Database schema migration failed, halting startup: %s",
                exc,
                exc_info=True,
            )
            raise

        await db.commit()


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async generator providing a database connection for FastAPI dependency injection.

    Usage:
        @app.get("/example")
        async def example(db: aiosqlite.Connection = Depends(get_db)):
            ...
    """
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        # Enable foreign key enforcement per connection
        await db.execute("PRAGMA foreign_keys = ON")
        yield db
    finally:
        await db.close()
