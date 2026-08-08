"""SAML 2.0 SP public endpoints: Metadata, Login, ACS, SLO, SLS."""

import logging

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.database import get_db
from app.services import auth_service
from app.services.provisioning_service import provision_sso_user
from app.services.saml_service import (
    SAMLValidationError,
    generate_sp_metadata,
    initiate_login,
    load_saml_settings,
    prepare_request_from_fastapi,
    process_acs,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/saml", tags=["saml"])


async def _is_saml_login_enabled(db: aiosqlite.Connection) -> bool:
    """Check if SAML login button is enabled in saml_config."""
    cursor = await db.execute("SELECT login_button_enabled FROM saml_config WHERE id = 1")
    row = await cursor.fetchone()
    return bool(row[0]) if row else False


async def _get_cookie_secure(db: aiosqlite.Connection) -> bool:
    """Read cookie_secure setting. Check saml_config first, fallback to sso_config."""
    # For now, reuse the sso_config cookie_secure setting (same deployment)
    cursor = await db.execute("SELECT cookie_secure FROM sso_config WHERE id = 1")
    row = await cursor.fetchone()
    return bool(row[0]) if row else False


@router.get("/metadata")
async def sp_metadata(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Return SP Metadata XML. No auth required.

    IdP administrators use this endpoint to configure trust with this SP.
    """
    try:
        settings = await load_saml_settings(db, request)
    except SAMLValidationError:
        # SAML not configured — return a helpful error
        raise HTTPException(status_code=404, detail="SAML 未配置，无法生成 SP Metadata") from None

    try:
        metadata_xml = generate_sp_metadata(settings)
    except SAMLValidationError as e:
        raise HTTPException(status_code=500, detail=e.message) from None

    return Response(
        content=metadata_xml,
        media_type="application/samlmetadata+xml",
    )


@router.get("/login")
async def saml_login(
    request: Request,
    next: str | None = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Initiate SP-Initiated SAML login. Redirects to IdP SSO URL.

    Query params:
        next: Optional path to redirect to after login completes.
    """
    # Check that SAML login is enabled
    if not await _is_saml_login_enabled(db):
        raise HTTPException(status_code=403, detail="SAML 登录入口未启用")

    try:
        redirect_url = await initiate_login(db, request, next_url=next)
    except SAMLValidationError as e:
        raise HTTPException(status_code=500, detail=e.message) from None

    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/acs")
async def assertion_consumer_service(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Assertion Consumer Service: process SAMLResponse from IdP.

    Receives the SAMLResponse via HTTP-POST binding, validates it,
    provisions/updates the user, creates a session, and redirects.
    """
    # Parse form data
    form = await request.form()
    form_data = dict(form)

    # Validate that SAMLResponse is present
    if "SAMLResponse" not in form_data:
        raise HTTPException(status_code=400, detail="缺少 SAMLResponse 参数")

    try:
        result = await process_acs(db, request, form_data)
    except SAMLValidationError as e:
        logger.warning("SAML ACS validation error: %s (code=%s)", e.message, e.error_code)
        raise HTTPException(status_code=400, detail=e.message) from None

    # Extract user information from the validated assertion
    nameid = result["nameid"]
    attributes = result["attributes"]
    relay_state = result["relay_state"]

    # Extract groups from attributes using the configured groups_attribute name
    cursor = await db.execute("SELECT groups_attribute FROM saml_config WHERE id = 1")
    config_row = await cursor.fetchone()
    groups_attribute = config_row[0] if config_row else "groups"

    # Get groups from SAML attributes
    groups = attributes.get(groups_attribute, [])
    if isinstance(groups, str):
        groups = [groups]

    # Extract email from attributes (common attribute names)
    email = None
    for email_attr in (
        "email",
        "mail",
        "emailAddress",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        "urn:oid:0.9.2342.19200300.100.1.3",
    ):
        email_values = attributes.get(email_attr, [])
        if email_values:
            email = email_values[0] if isinstance(email_values, list) else email_values
            break

    # Use NameID as fallback for username; prefer email if available
    username = email or nameid

    # Provision or update the SAML user
    user_id = await provision_sso_user(
        db,
        subject=nameid,
        username=username,
        email=email,
        groups=groups,
        auth_source="saml",
    )

    # Create session
    session_token, _ = await auth_service.create_session(db, user_id)

    # Determine redirect target
    redirect_to = relay_state or "/"

    # Build response with session cookie
    cookie_secure = await _get_cookie_secure(db)
    resp = RedirectResponse(url=redirect_to, status_code=302)
    resp.set_cookie(
        key=auth_service.SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=auth_service.SESSION_LIFETIME_HOURS * 3600,
        path="/",
    )
    return resp


@router.get("/slo")
async def sp_initiated_logout(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    """SP-Initiated Single Logout.

    If SAML config has an SLO URL, generates a LogoutRequest and redirects
    to the IdP. Otherwise, just invalidates the local session.
    """
    from onelogin.saml2.auth import OneLogin_Saml2_Auth

    # Get session from cookie
    token = request.cookies.get(auth_service.SESSION_COOKIE_NAME)
    if not token:
        return RedirectResponse(url="/login", status_code=302)

    session = await auth_service.load_session(db, token)
    if not session:
        # No valid session, just redirect to login
        resp = RedirectResponse(url="/login", status_code=302)
        resp.delete_cookie(key=auth_service.SESSION_COOKIE_NAME, path="/")
        return resp

    # Load SAML settings
    try:
        settings = await load_saml_settings(db, request)
    except SAMLValidationError:  # noqa: B904
        # SAML not configured — just do local logout
        await auth_service.invalidate_session(db, token)
        resp = RedirectResponse(url="/login", status_code=302)
        resp.delete_cookie(key=auth_service.SESSION_COOKIE_NAME, path="/")
        return resp

    # Check if IdP SLO URL is configured
    idp_slo_url = settings.get("idp", {}).get("singleLogoutService", {}).get("url", "")

    if not idp_slo_url:
        # No SLO URL configured — local logout only
        await auth_service.invalidate_session(db, token)
        resp = RedirectResponse(url="/login", status_code=302)
        resp.delete_cookie(key=auth_service.SESSION_COOKIE_NAME, path="/")
        return resp

    # Build LogoutRequest and redirect to IdP
    req_dict = prepare_request_from_fastapi(request)
    auth = OneLogin_Saml2_Auth(req_dict, old_settings=settings)

    # Retrieve the user's NameID and session_index for the LogoutRequest
    # For simplicity, use the username as NameID (stored in subject)
    cursor = await db.execute("SELECT sso_subject FROM users WHERE id = ?", (session["user_id"],))
    user_row = await cursor.fetchone()
    name_id = user_row[0] if user_row else None

    # Invalidate local session
    await auth_service.invalidate_session(db, token)

    # Generate LogoutRequest redirect URL
    redirect_url = auth.logout(
        name_id=name_id,
        return_to="/login",
    )

    resp = RedirectResponse(url=redirect_url, status_code=302)
    resp.delete_cookie(key=auth_service.SESSION_COOKIE_NAME, path="/")
    return resp


@router.get("/sls")
async def single_logout_service(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    """SLS endpoint: handle IdP-initiated LogoutRequest or LogoutResponse.

    This endpoint handles:
    1. IdP-initiated LogoutRequest: IdP asks SP to log out a user.
    2. LogoutResponse: IdP confirms that SP-initiated logout succeeded.
    """
    from onelogin.saml2.auth import OneLogin_Saml2_Auth

    # Load SAML settings
    try:
        settings = await load_saml_settings(db, request)
    except SAMLValidationError as e:
        raise HTTPException(status_code=500, detail=e.message) from None

    # Prepare request dict with query parameters
    req_dict = prepare_request_from_fastapi(request)

    # Create auth instance and process the SLO
    auth = OneLogin_Saml2_Auth(req_dict, old_settings=settings)

    # Process the SLO request/response
    # python3-saml's process_slo handles both LogoutRequest and LogoutResponse
    redirect_url = auth.process_slo(
        delete_session_cb=lambda: None,  # Sync callback placeholder
        keep_local_session=False,
    )

    errors = auth.get_errors()
    if errors:
        error_reason = auth.get_last_error_reason() or ", ".join(errors)
        logger.warning("SAML SLS validation failed: %s", error_reason)
        raise HTTPException(
            status_code=400,
            detail=f"SAML 登出验证失败: {error_reason}",
        )

    # If this was a LogoutRequest from the IdP, try to invalidate the user's session
    # The NameID in the LogoutRequest identifies the user
    nameid = None
    try:
        nameid = auth.get_nameid()
    except Exception:
        pass

    if nameid:
        # Find user by sso_subject and invalidate their sessions
        cursor = await db.execute("SELECT id FROM users WHERE sso_subject = ?", (nameid,))
        user_row = await cursor.fetchone()
        if user_row:
            await auth_service.invalidate_user_sessions(db, user_row[0])
            logger.info("SAML SLS: invalidated sessions for user sso_subject=%s", nameid)

    # Redirect to the URL provided by python3-saml, or to /login
    if redirect_url:
        return RedirectResponse(url=redirect_url, status_code=302)

    return RedirectResponse(url="/login", status_code=302)
