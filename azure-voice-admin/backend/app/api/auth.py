"""Authentication API: login, logout, current user."""

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.api.deps import CurrentUser, get_current_user
from app.database import get_db
from app.services import auth_service
from app.services.rbac import capabilities_for

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class MeResponse(BaseModel):
    id: str
    username: str
    roles: list[str]
    capabilities: list[str]
    must_change_password: bool = False


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Local account login. Returns user info and sets session cookie."""
    client_ip = request.client.host if request.client else "unknown"
    source_key = f"{client_ip}:{body.username}"

    # Check rate limit
    if await auth_service.check_rate_limit(db, source_key):
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试")

    # Lookup user
    cursor = await db.execute(
        "SELECT id, password_hash, is_active, must_change_password FROM users "
        "WHERE username = ? AND auth_source = 'local'",
        (body.username,),
    )
    row = await cursor.fetchone()

    # Unified rejection (don't reveal whether username exists)
    if not row or not auth_service.verify_password(body.password, row[1]):
        await auth_service.record_login_attempt(db, source_key, success=False)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user_id, _, is_active, must_change_password = row

    if not is_active:
        await auth_service.record_login_attempt(db, source_key, success=False)
        raise HTTPException(status_code=401, detail="账号已禁用")

    # Success
    await auth_service.record_login_attempt(db, source_key, success=True)
    session_token, csrf_token = await auth_service.create_session(db, user_id)

    # Load roles/capabilities for response
    cursor = await db.execute("SELECT role FROM user_roles WHERE user_id = ?", (user_id,))
    role_rows = await cursor.fetchall()
    roles = [r[0] for r in role_rows]
    caps = list(capabilities_for(set(roles)))

    # Set cookie
    response.set_cookie(
        key=auth_service.SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=auth_service.SESSION_LIFETIME_HOURS * 3600,
        path="/",
    )

    return {
        "id": user_id,
        "username": body.username,
        "roles": roles,
        "capabilities": caps,
        "must_change_password": bool(must_change_password),
        "csrf_token": csrf_token,
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Invalidate current session and clear cookie."""
    token = request.cookies.get(auth_service.SESSION_COOKIE_NAME)
    if token:
        await auth_service.invalidate_session(db, token)
    response.delete_cookie(
        key=auth_service.SESSION_COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return {"detail": "已退出登录"}


@router.get("/me")
async def me(user: CurrentUser = Depends(get_current_user)):
    """Return current authenticated user info."""
    return MeResponse(
        id=user.id,
        username=user.username,
        roles=list(user.roles),
        capabilities=list(user.capabilities),
    )
