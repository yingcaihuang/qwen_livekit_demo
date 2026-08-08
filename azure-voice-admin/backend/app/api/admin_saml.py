"""Admin SAML configuration API (requires sso:manage capability)."""

import logging

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUser, require_permission
from app.database import get_db
from app.services.saml_service import parse_idp_metadata, validate_x509_cert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/saml-config", tags=["admin-saml"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SamlConfigResponse(BaseModel):
    idp_entity_id: str | None = None
    idp_sso_url: str | None = None
    idp_slo_url: str | None = None
    idp_x509_cert: str | None = None
    sp_entity_id: str | None = None
    groups_attribute: str = "groups"
    nameid_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
    sign_algorithm: str = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
    login_button_enabled: bool = False
    idp_metadata_url: str | None = None


class SamlConfigUpdate(BaseModel):
    idp_entity_id: str | None = None
    idp_sso_url: str | None = None
    idp_slo_url: str | None = None
    idp_x509_cert: str | None = None
    sp_entity_id: str | None = None
    groups_attribute: str | None = None
    nameid_format: str | None = None
    sign_algorithm: str | None = None
    login_button_enabled: bool | None = None
    idp_metadata_url: str | None = None


class ParseMetadataRequest(BaseModel):
    metadata_url: str | None = None
    metadata_xml: str | None = None


class ParseMetadataResponse(BaseModel):
    idp_entity_id: str
    idp_sso_url: str
    idp_slo_url: str | None = None
    idp_x509_cert: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=SamlConfigResponse)
async def get_saml_config(
    user: CurrentUser = Depends(require_permission("sso:manage")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Get SAML configuration. Returns defaults if not yet configured."""
    cursor = await db.execute(
        "SELECT idp_entity_id, idp_sso_url, idp_slo_url, idp_x509_cert, "
        "sp_entity_id, groups_attribute, nameid_format, sign_algorithm, "
        "login_button_enabled, idp_metadata_url "
        "FROM saml_config WHERE id = 1"
    )
    row = await cursor.fetchone()
    if not row:
        return SamlConfigResponse()
    return SamlConfigResponse(
        idp_entity_id=row[0],
        idp_sso_url=row[1],
        idp_slo_url=row[2],
        idp_x509_cert=row[3],
        sp_entity_id=row[4],
        groups_attribute=row[5] or "groups",
        nameid_format=row[6] or "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        sign_algorithm=row[7] or "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
        login_button_enabled=bool(row[8]),
        idp_metadata_url=row[9],
    )


@router.put("", response_model=SamlConfigResponse)
async def update_saml_config(
    body: SamlConfigUpdate,
    user: CurrentUser = Depends(require_permission("sso:manage")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Save SAML configuration. Validates required fields and certificate format."""
    # Validate required fields: idp_entity_id, idp_sso_url, idp_x509_cert
    missing: list[str] = []
    if not body.idp_entity_id:
        missing.append("idp_entity_id")
    if not body.idp_sso_url:
        missing.append("idp_sso_url")
    if not body.idp_x509_cert:
        missing.append("idp_x509_cert")

    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"缺少必填字段: {', '.join(missing)}",
        )

    # Validate X.509 certificate format
    if not validate_x509_cert(body.idp_x509_cert):  # type: ignore[arg-type]
        raise HTTPException(
            status_code=422,
            detail="证书格式无效：请提供有效的 PEM 编码 X.509 证书（不超过 64KB）",
        )

    # Upsert: INSERT OR REPLACE with id=1
    await db.execute(
        """
        INSERT INTO saml_config (
            id, idp_entity_id, idp_sso_url, idp_slo_url, idp_x509_cert,
            sp_entity_id, groups_attribute, nameid_format, sign_algorithm,
            login_button_enabled, idp_metadata_url, updated_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            idp_entity_id = excluded.idp_entity_id,
            idp_sso_url = excluded.idp_sso_url,
            idp_slo_url = excluded.idp_slo_url,
            idp_x509_cert = excluded.idp_x509_cert,
            sp_entity_id = excluded.sp_entity_id,
            groups_attribute = excluded.groups_attribute,
            nameid_format = excluded.nameid_format,
            sign_algorithm = excluded.sign_algorithm,
            login_button_enabled = excluded.login_button_enabled,
            idp_metadata_url = excluded.idp_metadata_url,
            updated_at = datetime('now')
        """,
        (
            body.idp_entity_id,
            body.idp_sso_url,
            body.idp_slo_url,
            body.idp_x509_cert,
            body.sp_entity_id,
            body.groups_attribute or "groups",
            body.nameid_format or "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
            body.sign_algorithm or "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
            int(body.login_button_enabled) if body.login_button_enabled is not None else 0,
            body.idp_metadata_url,
        ),
    )
    await db.commit()

    # Return the saved configuration
    return await get_saml_config(user=user, db=db)


@router.post("/parse-metadata", response_model=ParseMetadataResponse)
async def parse_metadata(
    body: ParseMetadataRequest,
    user: CurrentUser = Depends(require_permission("sso:manage")),
):
    """Parse IdP Metadata from URL or raw XML. Returns extracted IdP fields."""
    if not body.metadata_url and not body.metadata_xml:
        raise HTTPException(
            status_code=400,
            detail="必须提供 metadata_url 或 metadata_xml 中的至少一个",
        )

    try:
        result = await parse_idp_metadata(url=body.metadata_url, xml=body.metadata_xml)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    return ParseMetadataResponse(
        idp_entity_id=result["idp_entity_id"],
        idp_sso_url=result["idp_sso_url"],
        idp_slo_url=result.get("idp_slo_url"),
        idp_x509_cert=result["idp_x509_cert"],
    )
