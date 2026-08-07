"""Database connection management and initialization for Azure Voice Testing Admin."""

import os
from collections.abc import AsyncGenerator
from pathlib import Path

import aiosqlite

# Database file path from environment variable, default to ./data/voice_admin.db
DB_PATH = os.environ.get("DB_PATH", "./data/voice_admin.db")

# Path to the schema file
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def init_db() -> None:
    """Initialize the database: create the data directory and execute schema.sql.

    This function is idempotent — all CREATE statements use IF NOT EXISTS.
    """
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(str(db_path)) as db:
        # Enable WAL mode for better concurrent read performance
        await db.execute("PRAGMA journal_mode=WAL")
        # Enable foreign key enforcement
        await db.execute("PRAGMA foreign_keys = ON")

        # Read and execute the schema
        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        await db.executescript(schema_sql)
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
