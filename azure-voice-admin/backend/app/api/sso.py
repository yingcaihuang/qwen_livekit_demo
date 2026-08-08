"""SSO API: Authentik OIDC login flow (authorization code + PKCE)."""

import logging

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app.database import get_db
from app.services import auth_service, crypto_service, oidc_service
from app.services.provisioning_service import provision_sso_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth/sso", tags=["sso"])


async def _load_sso_config(db: aiosqlite.Connection) -> dict | None:
    """Load SSO config from database. Returns None if not configured."""
    cursor = await db.execute(
        "SELECT issuer, discovery_url, client_id, client_secret_encrypted, "
        "authorization_endpoint, token_endpoint, userinfo_endpoint, jwks_uri, "
        "redirect_uri, scopes, groups_claim, groups_source, end_session_endpoint, "
        "login_button_enabled, cookie_secure "
        "FROM sso_config WHERE id = 1"
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "issuer": row[0],
        "discovery_url": row[1],
        "client_id": row[2],
        "client_secret_encrypted": row[3],
        "authorization_endpoint": row[4],
        "token_endpoint": row[5],
        "userinfo_endpoint": row[6],
        "jwks_uri": row[7],
        "redirect_uri": row[8],
        "scopes": row[9],
        "groups_claim": row[10],
        "groups_source": row[11] or "userinfo",
        "end_session_endpoint": row[12],
        "login_button_enabled": bool(row[13]),
        "cookie_secure": bool(row[14]),
    }


@router.get("/public-config")
async def public_config(db: aiosqlite.Connection = Depends(get_db)):
    """Return public SSO config (login button enabled state). No auth required."""
    config = await _load_sso_config(db)

    # Check SAML login enabled status
    cursor = await db.execute("SELECT login_button_enabled FROM saml_config WHERE id = 1")
    saml_row = await cursor.fetchone()
    saml_login_enabled = bool(saml_row[0]) if saml_row else False

    return {
        "login_button_enabled": config["login_button_enabled"] if config else False,
        "saml_login_enabled": saml_login_enabled,
    }


@router.get("/login")
async def sso_login(db: aiosqlite.Connection = Depends(get_db)):
    """Initiate SSO login: store state/nonce/PKCE and redirect to Authentik."""
    config = await _load_sso_config(db)
    if not config or not config["login_button_enabled"]:
        raise HTTPException(status_code=403, detail="统一认证入口未启用")
    if not config["client_id"] or not config["authorization_endpoint"]:
        raise HTTPException(status_code=500, detail="SSO 配置不完整")

    # Generate PKCE + state + nonce
    code_verifier, code_challenge = oidc_service.generate_pkce()
    state = oidc_service.generate_state()
    nonce = oidc_service.generate_nonce()

    # Store login state
    await db.execute(
        "INSERT INTO oidc_login_state (state, nonce, code_verifier) VALUES (?, ?, ?)",
        (state, nonce, code_verifier),
    )
    await db.commit()

    # Build authorization URL
    auth_url = oidc_service.build_authorization_url(
        authorization_endpoint=config["authorization_endpoint"],
        client_id=config["client_id"],
        redirect_uri=config["redirect_uri"] or "",
        scopes=config["scopes"],
        state=state,
        nonce=nonce,
        code_challenge=code_challenge,
    )
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/callback")
async def sso_callback(
    state: str,
    code: str,
    request: Request,
    response: Response,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Handle OIDC callback: validate state, exchange code, verify token, provision user."""
    # Validate state
    cursor = await db.execute(
        "SELECT nonce, code_verifier FROM oidc_login_state WHERE state = ?", (state,)
    )
    login_state = await cursor.fetchone()
    if not login_state:
        raise HTTPException(status_code=400, detail="OIDC 校验失败：state 无效")
    nonce, code_verifier = login_state

    # Clean up used state
    await db.execute("DELETE FROM oidc_login_state WHERE state = ?", (state,))
    await db.commit()

    # Load SSO config
    config = await _load_sso_config(db)
    if not config:
        raise HTTPException(status_code=500, detail="SSO 配置缺失")

    # Reject if SSO login is disabled (Req 4.7)
    if not config["login_button_enabled"]:
        raise HTTPException(status_code=403, detail="统一认证入口未启用")

    # Decrypt client_secret
    client_secret = ""
    if config["client_secret_encrypted"]:
        try:
            client_secret = crypto_service.decrypt(config["client_secret_encrypted"])
        except Exception:
            raise HTTPException(status_code=500, detail="SSO 配置错误：无法解密密钥") from None

    # Exchange code for tokens
    try:
        tokens = await oidc_service.exchange_code(
            token_endpoint=config["token_endpoint"],
            client_id=config["client_id"],
            client_secret=client_secret,
            code=code,
            code_verifier=code_verifier,
            redirect_uri=config["redirect_uri"] or "",
        )
    except Exception as e:
        logger.error("Token exchange failed: %s", e)
        raise HTTPException(status_code=400, detail="令牌交换失败") from None

    # Verify ID token
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="IdP 未返回 ID Token")

    try:
        jwks = await oidc_service.fetch_jwks(config["jwks_uri"])
        payload = oidc_service.verify_id_token(
            id_token,
            jwks=jwks,
            issuer=config["issuer"],
            audience=config["client_id"],
            nonce=nonce,
        )
    except Exception as e:
        logger.error("ID token verification failed: %s", e)
        raise HTTPException(status_code=400, detail="令牌校验失败") from None

    # Fetch userinfo
    access_token = tokens.get("access_token", "")
    try:
        userinfo = await oidc_service.fetch_userinfo(config["userinfo_endpoint"], access_token)
    except Exception as e:
        logger.error("Userinfo fetch failed: %s", e)
        raise HTTPException(status_code=400, detail="获取用户信息失败") from None

    # Provision/update user
    subject = payload.get("sub") or userinfo.get("sub", "")
    username = userinfo.get("preferred_username") or userinfo.get("email") or subject
    email = userinfo.get("email")
    groups_claim = config["groups_claim"]
    groups_source = config.get("groups_source", "userinfo")
    if groups_source == "id_token":
        groups = payload.get(groups_claim, [])
    else:
        groups = userinfo.get(groups_claim, [])
    if isinstance(groups, str):
        groups = [groups]

    user_id = await provision_sso_user(
        db, subject=subject, username=username, email=email, groups=groups
    )

    # Create session
    session_token, _ = await auth_service.create_session(db, user_id)

    # Set cookie and redirect to SPA root
    resp = RedirectResponse(url="/", status_code=302)
    resp.set_cookie(
        key=auth_service.SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=config["cookie_secure"],
        samesite="lax",
        max_age=auth_service.SESSION_LIFETIME_HOURS * 3600,
        path="/",
    )
    return resp


@router.post("/backchannel-logout")
async def backchannel_logout(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    """OIDC Back-Channel Logout: Authentik POSTs a signed logout_token to invalidate user sessions.

    This endpoint is called server-to-server by the IdP. No browser session required.
    The request body is application/x-www-form-urlencoded with a single field: logout_token.
    """
    # Parse form body
    form_data = await request.form()
    logout_token = form_data.get("logout_token")
    if not logout_token:
        raise HTTPException(status_code=400, detail="Missing logout_token")

    # Load SSO config to get JWKS for verification
    config = await _load_sso_config(db)
    if not config or not config["jwks_uri"]:
        raise HTTPException(status_code=500, detail="SSO config incomplete")

    # Fetch JWKS and verify the logout_token
    try:
        from jose import jwt as jose_jwt

        jwks = await oidc_service.fetch_jwks(config["jwks_uri"])
        # Decode without audience validation (logout_token may not have aud matching client_id in all IdPs)
        payload = jose_jwt.decode(
            logout_token,
            jwks,
            algorithms=["RS256", "ES256"],
            options={"verify_aud": False},
        )
    except Exception as e:
        logger.error("Back-channel logout token verification failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid logout_token") from None

    # Validate it's a logout token (has "events" claim with backchannel-logout event)
    events = payload.get("events", {})
    if "http://schemas.openid.net/event/backchannel-logout" not in events:
        raise HTTPException(status_code=400, detail="Not a backchannel logout token")

    # Get the subject (sub) from the token
    sub = payload.get("sub")
    if not sub:
        # Some IdPs use sid (session id) instead — for now we require sub
        raise HTTPException(status_code=400, detail="logout_token missing sub claim")

    # Find the user by sso_subject and invalidate all their sessions
    cursor = await db.execute("SELECT id FROM users WHERE sso_subject = ?", (sub,))
    user_row = await cursor.fetchone()
    if user_row:
        user_id = user_row[0]
        await auth_service.invalidate_user_sessions(db, user_id)
        logger.info("Back-channel logout: invalidated sessions for user %s (sub=%s)", user_id, sub)

    # OIDC spec requires 200 OK response on success
    return Response(status_code=200)


@router.get("/frontchannel-logout")
async def frontchannel_logout(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    """OIDC Front-Channel Logout: called via hidden iframe in the user's browser.

    When Authentik logs out a user, it renders an iframe pointing to this URL.
    Since the browser makes the request, it carries the session cookie.
    We simply invalidate the session from the cookie.
    """
    token = request.cookies.get(auth_service.SESSION_COOKIE_NAME)
    if token:
        session = await auth_service.load_session(db, token)
        if session:
            await auth_service.invalidate_session(db, token)
            logger.info("Front-channel logout: invalidated session for user %s", session["user_id"])

    # Must return 200 with empty or minimal HTML (iframe response)
    from fastapi.responses import HTMLResponse

    return HTMLResponse(content="<html><body>Logged out</body></html>", status_code=200)
