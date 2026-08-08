"""Admin user management API (requires user:manage capability)."""

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
    roles: list[str]
    created_at: str


class UserCreate(BaseModel):
    username: str
    password: str
    email: str | None = None
    roles: list[str] = ["viewer"]


class UserUpdate(BaseModel):
    is_active: bool | None = None
    roles: list[str] | None = None


@router.get("", response_model=list[UserResponse])
async def list_users(
    user: CurrentUser = Depends(require_permission("user:manage")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """List all users with their roles."""
    cursor = await db.execute(
        "SELECT id, username, email, auth_source, is_active, must_change_password, created_at "
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
                roles=[rr[0] for rr in role_rows],
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
    cursor = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not await cursor.fetchone():
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

    await db.commit()

    # Return updated user
    cursor = await db.execute(
        "SELECT id, username, email, auth_source, is_active, must_change_password, created_at "
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
        roles=[rr[0] for rr in role_rows],
        created_at=r[6],
    )
