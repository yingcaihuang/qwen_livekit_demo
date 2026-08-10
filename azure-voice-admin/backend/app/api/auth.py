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
    auth_source: str = "local"


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
    cookie_secure = await auth_service.get_cookie_secure(db)
    response.set_cookie(
        key=auth_service.SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=cookie_secure,
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
    """Invalidate current session and clear cookie. For SSO users, return end_session_url."""
    token = request.cookies.get(auth_service.SESSION_COOKIE_NAME)
    end_session_url = None

    if token:
        # Load session to get user_id before invalidating
        session = await auth_service.load_session(db, token)
        if session:
            user_id = session["user_id"]
            # Check if user is SSO-sourced
            cursor = await db.execute("SELECT auth_source FROM users WHERE id = ?", (user_id,))
            user_row = await cursor.fetchone()
            if user_row and user_row[0] == "sso":
                # Look up end_session_endpoint from sso_config
                cursor = await db.execute(
                    "SELECT end_session_endpoint FROM sso_config WHERE id = 1"
                )
                sso_row = await cursor.fetchone()
                if sso_row and sso_row[0]:
                    # Derive post_logout_redirect_uri from request
                    referer = request.headers.get("referer", "")
                    if referer:
                        from urllib.parse import urlparse

                        parsed = urlparse(referer)
                        origin = f"{parsed.scheme}://{parsed.netloc}"
                    else:
                        # Fallback to Host header
                        host = request.headers.get("host", "localhost")
                        scheme = request.headers.get("x-forwarded-proto", "https")
                        origin = f"{scheme}://{host}"
                    post_logout_uri = f"{origin}/login"
                    end_session_url = f"{sso_row[0]}?post_logout_redirect_uri={post_logout_uri}"

        await auth_service.invalidate_session(db, token)

    cookie_secure = await auth_service.get_cookie_secure(db)
    response.delete_cookie(
        key=auth_service.SESSION_COOKIE_NAME,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        path="/",
    )

    result: dict = {"detail": "已退出登录"}
    if end_session_url:
        result["end_session_url"] = end_session_url
    return result


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Change current user's password. Requires valid current password."""
    # Validate new password length
    if len(body.new_password) < 12:
        raise HTTPException(status_code=422, detail="新密码长度至少12个字符")

    # Load current password hash
    cursor = await db.execute(
        "SELECT password_hash, auth_source FROM users WHERE id = ?", (user.id,)
    )
    row = await cursor.fetchone()
    if not row or row[1] != "local":
        raise HTTPException(status_code=400, detail="仅本地账号可修改密码")

    # Verify current password
    if not auth_service.verify_password(body.current_password, row[0]):
        raise HTTPException(status_code=400, detail="当前密码错误")

    # Update password and clear must_change_password flag
    new_hash = auth_service.hash_password(body.new_password)
    await db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = datetime('now') WHERE id = ?",
        (new_hash, user.id),
    )
    await db.commit()

    return {"detail": "密码已修改"}


@router.get("/me")
async def me(user: CurrentUser = Depends(get_current_user)):
    """Return current authenticated user info."""
    return MeResponse(
        id=user.id,
        username=user.username,
        roles=list(user.roles),
        capabilities=list(user.capabilities),
        must_change_password=user.must_change_password,
        auth_source=user.auth_source,
    )
