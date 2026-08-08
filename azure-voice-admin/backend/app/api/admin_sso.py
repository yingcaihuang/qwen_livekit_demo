"""Admin SSO configuration API (requires sso:manage capability)."""

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUser, require_permission
from app.database import get_db
from app.services import crypto_service

router = APIRouter(prefix="/api/admin/sso-config", tags=["admin-sso"])


class SsoConfigResponse(BaseModel):
    issuer: str | None = None
    discovery_url: str | None = None
    client_id: str | None = None
    client_secret_set: bool = False
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None
    redirect_uri: str | None = None
    scopes: str = "openid profile email groups"
    groups_claim: str = "groups"
    end_session_endpoint: str | None = None
    login_button_enabled: bool = False
    cookie_secure: bool = False


class SsoConfigUpdate(BaseModel):
    issuer: str | None = None
    discovery_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None  # plaintext on input; encrypted before storage
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None
    redirect_uri: str | None = None
    scopes: str | None = None
    groups_claim: str | None = None
    end_session_endpoint: str | None = None
    login_button_enabled: bool | None = None
    cookie_secure: bool | None = None


@router.get("", response_model=SsoConfigResponse)
async def get_sso_config(
    user: CurrentUser = Depends(require_permission("sso:manage")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Get SSO configuration (client_secret is redacted)."""
    cursor = await db.execute(
        "SELECT issuer, discovery_url, client_id, client_secret_encrypted, "
        "authorization_endpoint, token_endpoint, userinfo_endpoint, jwks_uri, "
        "redirect_uri, scopes, groups_claim, end_session_endpoint, login_button_enabled, "
        "cookie_secure "
        "FROM sso_config WHERE id = 1"
    )
    row = await cursor.fetchone()
    if not row:
        return SsoConfigResponse()
    return SsoConfigResponse(
        issuer=row[0],
        discovery_url=row[1],
        client_id=row[2],
        client_secret_set=bool(row[3]),
        authorization_endpoint=row[4],
        token_endpoint=row[5],
        userinfo_endpoint=row[6],
        jwks_uri=row[7],
        redirect_uri=row[8],
        scopes=row[9] or "openid profile email groups",
        groups_claim=row[10] or "groups",
        end_session_endpoint=row[11],
        login_button_enabled=bool(row[12]),
        cookie_secure=bool(row[13]),
    )


@router.put("", response_model=SsoConfigResponse)
async def update_sso_config(
    body: SsoConfigUpdate,
    user: CurrentUser = Depends(require_permission("sso:manage")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Update SSO configuration. Client_secret is encrypted before storage."""
    # Build update fields
    fields: dict = {}
    if body.issuer is not None:
        fields["issuer"] = body.issuer
    if body.discovery_url is not None:
        fields["discovery_url"] = body.discovery_url
    if body.client_id is not None:
        fields["client_id"] = body.client_id
    if body.client_secret is not None:
        fields["client_secret_encrypted"] = crypto_service.encrypt(body.client_secret)
    if body.authorization_endpoint is not None:
        fields["authorization_endpoint"] = body.authorization_endpoint
    if body.token_endpoint is not None:
        fields["token_endpoint"] = body.token_endpoint
    if body.userinfo_endpoint is not None:
        fields["userinfo_endpoint"] = body.userinfo_endpoint
    if body.jwks_uri is not None:
        fields["jwks_uri"] = body.jwks_uri
    if body.redirect_uri is not None:
        fields["redirect_uri"] = body.redirect_uri
    if body.scopes is not None:
        fields["scopes"] = body.scopes
    if body.groups_claim is not None:
        fields["groups_claim"] = body.groups_claim
    if body.end_session_endpoint is not None:
        fields["end_session_endpoint"] = body.end_session_endpoint
    if body.login_button_enabled is not None:
        fields["login_button_enabled"] = int(body.login_button_enabled)
    if body.cookie_secure is not None:
        fields["cookie_secure"] = int(body.cookie_secure)

    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values())
        await db.execute(
            f"UPDATE sso_config SET {set_clause}, updated_at = datetime('now') WHERE id = 1",
            values,
        )
        await db.commit()

    # Return updated config
    return await get_sso_config(user=user, db=db)


class DiscoverRequest(BaseModel):
    discovery_url: str


class DiscoverResponse(BaseModel):
    issuer: str | None = None
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None
    end_session_endpoint: str | None = None


@router.post("/discover", response_model=DiscoverResponse)
async def discover_endpoints(
    body: DiscoverRequest,
    user: CurrentUser = Depends(require_permission("sso:manage")),
):
    """Fetch OIDC discovery document and return discovered endpoints."""
    from app.services.oidc_service import discover

    try:
        doc = await discover(body.discovery_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法获取 discovery 文档: {e}") from None

    return DiscoverResponse(
        issuer=doc.get("issuer"),
        authorization_endpoint=doc.get("authorization_endpoint"),
        token_endpoint=doc.get("token_endpoint"),
        userinfo_endpoint=doc.get("userinfo_endpoint"),
        jwks_uri=doc.get("jwks_uri"),
        end_session_endpoint=doc.get("end_session_endpoint"),
    )
