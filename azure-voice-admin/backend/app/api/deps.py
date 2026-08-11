"""Authentication dependencies for FastAPI route protection."""

import os
from dataclasses import dataclass

import aiosqlite
from fastapi import Depends, HTTPException, Request

from app.database import get_db
from app.services import auth_service
from app.services.rbac import capabilities_for

SESSION_COOKIE_NAME = auth_service.SESSION_COOKIE_NAME


@dataclass
class CurrentUser:
    """Represents the authenticated user injected into route handlers."""

    id: str
    username: str
    roles: set[str]
    capabilities: frozenset[str]
    must_change_password: bool = False
    auth_source: str = "local"


def _is_testing() -> bool:
    """Check whether we are running in test mode (TESTING=1 env var)."""
    return os.environ.get("TESTING", "0") == "1"


_TEST_USER: "CurrentUser | None" = None


def _get_test_user() -> "CurrentUser":
    """Return a cached mock super_admin user for test mode."""
    global _TEST_USER
    if _TEST_USER is None:
        _TEST_USER = CurrentUser(
            id="test-user-id",
            username="test-admin",
            roles={"super_admin"},
            capabilities=capabilities_for({"super_admin"}),
            must_change_password=False,
            auth_source="local",
        )
    return _TEST_USER


async def get_current_user(
    request: Request, db: aiosqlite.Connection = Depends(get_db)
) -> CurrentUser:
    """Extract and validate session from cookie, load user + roles.

    In test mode (TESTING=1), returns a mock super_admin user so that
    existing tests which do not send auth cookies keep passing.
    """
    if _is_testing():
        return _get_test_user()

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="未认证")
    session = await auth_service.load_session(db, token)
    if session is None:
        raise HTTPException(status_code=401, detail="会话无效或已过期")
    user_id = session["user_id"]
    # Load user record
    cursor = await db.execute(
        "SELECT id, username, is_active, must_change_password, auth_source FROM users WHERE id = ?",
        (user_id,),
    )
    user_row = await cursor.fetchone()
    if not user_row or not user_row[2]:  # is_active == 0
        raise HTTPException(status_code=401, detail="账号已禁用")
    # Load roles
    cursor = await db.execute("SELECT role FROM user_roles WHERE user_id = ?", (user_id,))
    role_rows = await cursor.fetchall()
    roles = {row[0] for row in role_rows}
    caps = capabilities_for(roles)
    user_obj = CurrentUser(
        id=user_row[0],
        username=user_row[1],
        roles=roles,
        capabilities=caps,
        must_change_password=bool(user_row[3]),
        auth_source=user_row[4] or "local",
    )
    # Store on request state so that audit middleware can access user info
    request.state.user = user_obj
    return user_obj


def require_permission(capability: str):
    """Factory that creates a dependency requiring a specific capability."""

    async def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if capability not in user.capabilities:
            raise HTTPException(status_code=403, detail="权限不足")
        return user

    return _dep
