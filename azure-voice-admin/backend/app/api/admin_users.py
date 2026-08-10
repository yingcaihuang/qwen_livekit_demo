"""Admin user management API (requires user:manage capability)."""

import json
import secrets

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUser, require_permission
from app.database import get_db
from app.services import auth_service
from app.services.rbac import VALID_ROLES

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


class UserResponse(BaseModel):
    id: str
    username: str
    email: str | None = None
    auth_source: str
    is_active: bool
    must_change_password: bool
    role_override: bool = False
    roles: list[str]
    groups: list[str] = []
    created_at: str


class UserCreate(BaseModel):
    username: str
    password: str
    email: str | None = None
    roles: list[str] = ["viewer"]


class UserUpdate(BaseModel):
    is_active: bool | None = None
    roles: list[str] | None = None
    role_override: bool | None = None


@router.get("", response_model=list[UserResponse])
async def list_users(
    user: CurrentUser = Depends(require_permission("user:manage")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """List all users with their roles."""
    cursor = await db.execute(
        "SELECT id, username, email, auth_source, is_active, must_change_password, created_at, sso_groups, role_override "
        "FROM users ORDER BY created_at"
    )
    rows = await cursor.fetchall()
    result = []
    for r in rows:
        role_cursor = await db.execute("SELECT role FROM user_roles WHERE user_id = ?", (r[0],))
        role_rows = await role_cursor.fetchall()
        result.append(
            UserResponse(
                id=r[0],
                username=r[1],
                email=r[2],
                auth_source=r[3],
                is_active=bool(r[4]),
                must_change_password=bool(r[5]),
                role_override=bool(r[8]),
                roles=[rr[0] for rr in role_rows],
                groups=json.loads(r[7] or "[]"),
                created_at=r[6],
            )
        )
    return result


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreate,
    user: CurrentUser = Depends(require_permission("user:manage")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Create a local user account (hashed password, must_change_password=1)."""
    for role in body.roles:
        if role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"无效角色: {role}")

    user_id = secrets.token_hex(16)
    password_hash = auth_service.hash_password(body.password)
    try:
        await db.execute(
            "INSERT INTO users (id, username, email, auth_source, password_hash, must_change_password) "
            "VALUES (?, ?, ?, 'local', ?, 1)",
            (user_id, body.username, body.email, password_hash),
        )
        for role in body.roles:
            await db.execute(
                "INSERT INTO user_roles (user_id, role) VALUES (?, ?)",
                (user_id, role),
            )
        await db.commit()
    except Exception:
        raise HTTPException(status_code=409, detail=f"用户名 '{body.username}' 已存在") from None

    # Return created user
    cursor = await db.execute(
        "SELECT id, username, email, auth_source, is_active, must_change_password, created_at "
        "FROM users WHERE id = ?",
        (user_id,),
    )
    r = await cursor.fetchone()
    return UserResponse(
        id=r[0],
        username=r[1],
        email=r[2],
        auth_source=r[3],
        is_active=bool(r[4]),
        must_change_password=bool(r[5]),
        roles=body.roles,
        created_at=r[6],
    )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UserUpdate,
    user: CurrentUser = Depends(require_permission("user:manage")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Update user: enable/disable or change roles. Disabling invalidates sessions."""
    cursor = await db.execute("SELECT id, auth_source FROM users WHERE id = ?", (user_id,))
    existing = await cursor.fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="用户不存在")

    if body.is_active is not None:
        await db.execute(
            "UPDATE users SET is_active = ?, updated_at = datetime('now') WHERE id = ?",
            (int(body.is_active), user_id),
        )
        # If disabling, invalidate all sessions (Req 11.4)
        if not body.is_active:
            await auth_service.invalidate_user_sessions(db, user_id)

    if body.roles is not None:
        for role in body.roles:
            if role not in VALID_ROLES:
                raise HTTPException(status_code=400, detail=f"无效角色: {role}")
        await db.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
        for role in body.roles:
            await db.execute(
                "INSERT INTO user_roles (user_id, role) VALUES (?, ?)",
                (user_id, role),
            )
        # For SSO users, manually changing roles implies override
        if existing[1] == "sso":
            await db.execute(
                "UPDATE users SET role_override = 1, updated_at = datetime('now') WHERE id = ?",
                (user_id,),
            )

    if body.role_override is not None:
        await db.execute(
            "UPDATE users SET role_override = ?, updated_at = datetime('now') WHERE id = ?",
            (int(body.role_override), user_id),
        )
        # If clearing override, recompute roles from current group mappings
        if not body.role_override and existing[1] == "sso":
            from app.services.provisioning_service import _compute_roles

            groups_cursor = await db.execute(
                "SELECT sso_groups FROM users WHERE id = ?", (user_id,)
            )
            groups_row = await groups_cursor.fetchone()
            groups = json.loads(groups_row[0] or "[]") if groups_row else []
            roles = await _compute_roles(db, groups)
            await db.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
            for role in roles:
                await db.execute(
                    "INSERT INTO user_roles (user_id, role) VALUES (?, ?)",
                    (user_id, role),
                )

    await db.commit()

    # Return updated user
    cursor = await db.execute(
        "SELECT id, username, email, auth_source, is_active, must_change_password, created_at, sso_groups, role_override "
        "FROM users WHERE id = ?",
        (user_id,),
    )
    r = await cursor.fetchone()
    role_cursor = await db.execute("SELECT role FROM user_roles WHERE user_id = ?", (user_id,))
    role_rows = await role_cursor.fetchall()
    return UserResponse(
        id=r[0],
        username=r[1],
        email=r[2],
        auth_source=r[3],
        is_active=bool(r[4]),
        must_change_password=bool(r[5]),
        role_override=bool(r[8]),
        roles=[rr[0] for rr in role_rows],
        groups=json.loads(r[7] or "[]"),
        created_at=r[6],
    )


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    user: CurrentUser = Depends(require_permission("user:manage")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Delete a user and all associated data (sessions, roles)."""
    # Prevent self-deletion
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")

    cursor = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="用户不存在")

    # Invalidate all sessions first
    await auth_service.invalidate_user_sessions(db, user_id)
    # Delete user (CASCADE will clean up user_roles and auth_sessions)
    await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    await db.commit()


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    user: CurrentUser = Depends(require_permission("user:manage")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Reset a local user's password to a random value. Returns the new password."""
    # Check user exists and is local
    cursor = await db.execute("SELECT id, auth_source FROM users WHERE id = ?", (user_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    if row[1] != "local":
        raise HTTPException(status_code=400, detail="仅本地账号可重置密码")

    # Generate random password (16 chars, URL-safe)
    new_password = secrets.token_urlsafe(12)  # 16 characters
    new_hash = auth_service.hash_password(new_password)

    # Update password and set must_change_password
    await db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 1, updated_at = datetime('now') WHERE id = ?",
        (new_hash, user_id),
    )
    await db.commit()

    # Invalidate existing sessions so user must re-login
    await auth_service.invalidate_user_sessions(db, user_id)

    return {"new_password": new_password}
