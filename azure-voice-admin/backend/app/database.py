"""Database connection management and initialization for Azure Voice Testing Admin."""

import logging
import os
import secrets
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

    # 2) image_generations timing columns — databases created before per-image
    #    performance timing was added lack these columns. SQLite has no
    #    "ADD COLUMN IF NOT EXISTS", so check the existing columns first and add
    #    only the missing ones. All are nullable so pre-existing rows keep NULL
    #    (old records have no timing). Mirrors the instances.type pattern above.
    cursor = await db.execute("PRAGMA table_info(image_generations)")
    image_columns = {row[1] for row in await cursor.fetchall()}
    timing_columns = {
        "started_at": "TEXT",
        "ended_at": "TEXT",
        "duration_ms": "INTEGER",
        "ttfb_ms": "INTEGER",
    }
    for column_name, column_type in timing_columns.items():
        if column_name not in image_columns:
            await db.execute(
                f"ALTER TABLE image_generations ADD COLUMN {column_name} {column_type}"
            )

    # 3) session_messages model/endpoint columns — databases created before
    #    per-assistant-turn model/endpoint tracking was added lack these
    #    columns. SQLite has no "ADD COLUMN IF NOT EXISTS", so check the
    #    existing columns first and add only the missing ones. Both are nullable
    #    so pre-existing rows keep NULL (old messages have no model/endpoint).
    #    Mirrors the instances.type / image_generations timing patterns above.
    cursor = await db.execute("PRAGMA table_info(session_messages)")
    message_columns = {row[1] for row in await cursor.fetchall()}
    for column_name in ("model", "endpoint"):
        if column_name not in message_columns:
            await db.execute(f"ALTER TABLE session_messages ADD COLUMN {column_name} TEXT")

    # 4) created_by column — for resource multi-tenant isolation (Req 7.5.1,
    #    7.4). Existing tables instances, sessions, and image_generations need
    #    a nullable `created_by TEXT` column so each resource can be attributed
    #    to the user who created it. Old rows keep NULL (visible to all / admin).
    for table in ("instances", "sessions", "image_generations"):
        cursor = await db.execute(f"PRAGMA table_info({table})")
        cols = {row[1] for row in await cursor.fetchall()}
        if "created_by" not in cols:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN created_by TEXT")

    # 5) end_session_endpoint column for OIDC RP-Initiated Logout.
    cursor = await db.execute("PRAGMA table_info(sso_config)")
    sso_cols = {row[1] for row in await cursor.fetchall()}
    if "end_session_endpoint" not in sso_cols:
        await db.execute("ALTER TABLE sso_config ADD COLUMN end_session_endpoint TEXT")

    # 6) cookie_secure column for sso_config.
    if "cookie_secure" not in sso_cols:
        await db.execute(
            "ALTER TABLE sso_config ADD COLUMN cookie_secure INTEGER NOT NULL DEFAULT 0"
        )

    # 6b) scim_token column for sso_config (SCIM v2 bearer token).
    if "scim_token" not in sso_cols:
        await db.execute("ALTER TABLE sso_config ADD COLUMN scim_token TEXT")

    # 6b2) groups_source column for sso_config ('userinfo' | 'id_token').
    if "groups_source" not in sso_cols:
        await db.execute(
            "ALTER TABLE sso_config ADD COLUMN groups_source TEXT NOT NULL DEFAULT 'userinfo'"
        )

    # 6c) sso_groups column for storing user's Authentik groups
    cursor = await db.execute("PRAGMA table_info(users)")
    user_cols = {row[1] for row in await cursor.fetchall()}
    if "sso_groups" not in user_cols:
        await db.execute("ALTER TABLE users ADD COLUMN sso_groups TEXT DEFAULT '[]'")

    # 6d) role_override column — when 1, SSO login will not auto-update roles
    if "role_override" not in user_cols:
        await db.execute("ALTER TABLE users ADD COLUMN role_override INTEGER NOT NULL DEFAULT 0")

    # 9) target_language and source_language columns for translate/transcribe sessions
    cursor = await db.execute("PRAGMA table_info(sessions)")
    session_cols = {row[1] for row in await cursor.fetchall()}
    if "target_language" not in session_cols:
        await db.execute("ALTER TABLE sessions ADD COLUMN target_language TEXT")
    if "source_language" not in session_cols:
        await db.execute("ALTER TABLE sessions ADD COLUMN source_language TEXT")

    # 7) Seed sso_config singleton row (Req 9.6, 3.1). The table is created in
    #    schema.sql; here we ensure the single-row configuration placeholder
    #    exists so that queries never fail on an empty table.
    await db.execute("INSERT OR IGNORE INTO sso_config (id, login_button_enabled) VALUES (1, 0)")

    # 8) Seed super_admin account if none exists (Req 3.1, 3.2).
    #    Idempotent: only creates the account when no super_admin role exists
    #    in the database. If SEED_ADMIN_PASSWORD is not set, uses a fixed default
    #    password that is shown on the login page until changed.
    #    The account is marked must_change_password=1.
    cursor = await db.execute("SELECT COUNT(*) FROM user_roles WHERE role = 'super_admin'")
    (count,) = await cursor.fetchone()
    if count == 0:
        from app.services.auth_service import hash_password

        seed_username = os.environ.get("SEED_ADMIN_USERNAME", "admin")
        seed_password = os.environ.get("SEED_ADMIN_PASSWORD", "ChangeMe@2024")
        _logger.info(
            "Seed admin '%s' created. Default password: %s (must change on first login)",
            seed_username,
            seed_password,
        )
        user_id = secrets.token_hex(16)
        password_hash = hash_password(seed_password)
        await db.execute(
            "INSERT OR IGNORE INTO users "
            "(id, username, auth_source, password_hash, must_change_password) "
            "VALUES (?, ?, 'local', ?, 1)",
            (user_id, seed_username, password_hash),
        )
        await db.execute(
            "INSERT OR IGNORE INTO user_roles (user_id, role) VALUES (?, 'super_admin')",
            (user_id,),
        )
        _logger.info("Seed admin '%s' created with super_admin role.", seed_username)

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
