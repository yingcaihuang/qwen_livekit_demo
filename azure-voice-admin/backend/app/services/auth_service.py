"""Authentication service: password hashing and server-side session management."""

import secrets
from datetime import UTC, datetime, timedelta

import aiosqlite
import bcrypt

SESSION_LIFETIME_HOURS = 8
SESSION_COOKIE_NAME = "session_token"
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_FAILURES = 5


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


async def create_session(db: aiosqlite.Connection, user_id: str) -> tuple[str, str]:
    """Create a new auth session. Returns (session_token, csrf_token)."""
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(16)
    expires_at = (datetime.now(UTC) + timedelta(hours=SESSION_LIFETIME_HOURS)).isoformat()
    await db.execute(
        "INSERT INTO auth_sessions (id, user_id, expires_at, csrf_token) VALUES (?, ?, ?, ?)",
        (session_token, user_id, expires_at, csrf_token),
    )
    await db.commit()
    return session_token, csrf_token


async def load_session(db: aiosqlite.Connection, token: str) -> dict | None:
    """Load and validate a session. Returns dict or None if expired/missing."""
    cursor = await db.execute(
        "SELECT user_id, expires_at, csrf_token FROM auth_sessions WHERE id = ?",
        (token,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    user_id, expires_at_str, csrf_token = row
    expires_at = datetime.fromisoformat(expires_at_str)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) > expires_at:
        # Session expired — clean it up
        await db.execute("DELETE FROM auth_sessions WHERE id = ?", (token,))
        await db.commit()
        return None
    return {"user_id": user_id, "csrf_token": csrf_token, "expires_at": expires_at_str}


async def invalidate_session(db: aiosqlite.Connection, token: str) -> None:
    """Delete a specific session (logout)."""
    await db.execute("DELETE FROM auth_sessions WHERE id = ?", (token,))
    await db.commit()


async def invalidate_user_sessions(db: aiosqlite.Connection, user_id: str) -> None:
    """Delete all sessions for a user (e.g. when disabled)."""
    await db.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
    await db.commit()


async def check_rate_limit(db: aiosqlite.Connection, source_key: str) -> bool:
    """Check if the source_key is rate-limited. Returns True if blocked."""
    cursor = await db.execute(
        "SELECT COUNT(*) FROM login_attempts "
        "WHERE source_key = ? AND success = 0 "
        "AND attempted_at > datetime('now', ? || ' seconds')",
        (source_key, f"-{RATE_LIMIT_WINDOW_SECONDS}"),
    )
    (count,) = await cursor.fetchone()
    return count >= RATE_LIMIT_MAX_FAILURES


async def record_login_attempt(db: aiosqlite.Connection, source_key: str, *, success: bool) -> None:
    """Record a login attempt for rate limiting."""
    await db.execute(
        "INSERT INTO login_attempts (source_key, success) VALUES (?, ?)",
        (source_key, int(success)),
    )
    await db.commit()
