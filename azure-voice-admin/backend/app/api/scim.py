"""SCIM v2 server endpoints for Authentik user/group provisioning."""

import logging
import secrets
from typing import Any

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.database import get_db
from app.services import auth_service
from app.services.provisioning_service import _compute_roles, provision_sso_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scim/v2", tags=["scim"])

SCIM_CONTENT_TYPE = "application/scim+json"


async def verify_scim_token(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """Verify Bearer token for SCIM endpoints."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header[7:]
    cursor = await db.execute("SELECT scim_token FROM sso_config WHERE id = 1")
    row = await cursor.fetchone()
    if not row or not row[0] or row[0] != token:
        raise HTTPException(status_code=401, detail="Invalid SCIM token")
    return True


# --- Service Provider Config ---
@router.get("/ServiceProviderConfig")
async def service_provider_config():
    """Return SCIM ServiceProviderConfig (no auth required per spec)."""
    return JSONResponse(
        content={
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
            "documentationUri": "",
            "patch": {"supported": True},
            "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
            "filter": {"supported": False, "maxResults": 200},
            "changePassword": {"supported": False},
            "sort": {"supported": False},
            "etag": {"supported": False},
            "authenticationSchemes": [
                {
                    "type": "oauthbearertoken",
                    "name": "OAuth Bearer Token",
                    "description": "Authentication using Bearer token",
                }
            ],
        },
        media_type=SCIM_CONTENT_TYPE,
    )


@router.get("/Schemas")
async def schemas():
    """Return supported SCIM schemas."""
    return JSONResponse(
        content={
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": 2,
            "Resources": [
                {"id": "urn:ietf:params:scim:schemas:core:2.0:User", "name": "User"},
                {"id": "urn:ietf:params:scim:schemas:core:2.0:Group", "name": "Group"},
            ],
        },
        media_type=SCIM_CONTENT_TYPE,
    )


# --- Users ---
@router.get("/Users")
async def list_users(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
    _=Depends(verify_scim_token),
):
    """List all SSO-provisioned users."""
    cursor = await db.execute(
        "SELECT id, username, email, sso_subject, is_active FROM users WHERE auth_source = 'sso'"
    )
    rows = await cursor.fetchall()
    resources = [_user_to_scim(r[0], r[1], r[2], r[3], bool(r[4])) for r in rows]
    return JSONResponse(
        content={
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": len(resources),
            "Resources": resources,
        },
        media_type=SCIM_CONTENT_TYPE,
    )


@router.get("/Users/{user_id}")
async def get_user(
    user_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    _=Depends(verify_scim_token),
):
    """Get a single user by internal id or sso_subject."""
    cursor = await db.execute(
        "SELECT id, username, email, sso_subject, is_active FROM users "
        "WHERE id = ? OR sso_subject = ?",
        (user_id, user_id),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return JSONResponse(
        content=_user_to_scim(row[0], row[1], row[2], row[3], bool(row[4])),
        media_type=SCIM_CONTENT_TYPE,
    )


@router.post("/Users", status_code=201)
async def create_user(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
    _=Depends(verify_scim_token),
):
    """Create (provision) a new SSO user."""
    body = await request.json()
    external_id = body.get("externalId", "")
    username = body.get("userName", "")
    active = body.get("active", True)
    emails = body.get("emails", [])
    email = emails[0]["value"] if emails else None
    display_name = body.get("displayName", username)
    groups = [g.get("display", g.get("value", "")) for g in body.get("groups", [])]

    # Provision user (reuse existing logic)
    user_id = await provision_sso_user(
        db,
        subject=external_id or username,
        username=username or display_name,
        email=email,
        groups=groups,
    )

    # Handle active flag
    if not active:
        await db.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        await auth_service.invalidate_user_sessions(db, user_id)
        await db.commit()

    cursor = await db.execute(
        "SELECT id, username, email, sso_subject, is_active FROM users WHERE id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    return JSONResponse(
        content=_user_to_scim(row[0], row[1], row[2], row[3], bool(row[4])),
        status_code=201,
        media_type=SCIM_CONTENT_TYPE,
    )


@router.put("/Users/{user_id}")
async def replace_user(
    user_id: str,
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
    _=Depends(verify_scim_token),
):
    """Replace (full update) a user."""
    body = await request.json()
    username = body.get("userName", "")
    active = body.get("active", True)
    emails = body.get("emails", [])
    email = emails[0]["value"] if emails else None

    # Find user by id or sso_subject
    cursor = await db.execute(
        "SELECT id FROM users WHERE id = ? OR sso_subject = ?", (user_id, user_id)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    internal_id = row[0]

    await db.execute(
        "UPDATE users SET username = ?, email = ?, is_active = ?, updated_at = datetime('now') "
        "WHERE id = ?",
        (username, email, int(active), internal_id),
    )

    if not active:
        await auth_service.invalidate_user_sessions(db, internal_id)

    # Update groups if provided
    groups = [g.get("display", g.get("value", "")) for g in body.get("groups", [])]
    if groups:
        roles = await _compute_roles(db, groups)
        await db.execute("DELETE FROM user_roles WHERE user_id = ?", (internal_id,))
        for role in roles:
            await db.execute(
                "INSERT INTO user_roles (user_id, role) VALUES (?, ?)", (internal_id, role)
            )

    await db.commit()

    cursor = await db.execute(
        "SELECT id, username, email, sso_subject, is_active FROM users WHERE id = ?",
        (internal_id,),
    )
    row = await cursor.fetchone()
    return JSONResponse(
        content=_user_to_scim(row[0], row[1], row[2], row[3], bool(row[4])),
        media_type=SCIM_CONTENT_TYPE,
    )


@router.patch("/Users/{user_id}")
async def patch_user(
    user_id: str,
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
    _=Depends(verify_scim_token),
):
    """Patch a user (partial update)."""
    body = await request.json()
    cursor = await db.execute(
        "SELECT id, is_active FROM users WHERE id = ? OR sso_subject = ?", (user_id, user_id)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    internal_id = row[0]

    for op in body.get("Operations", []):
        path = op.get("path", "")
        value = op.get("value")
        if path == "active" or (not path and isinstance(value, dict) and "active" in value):
            active = value if isinstance(value, bool) else value.get("active", True)
            await db.execute(
                "UPDATE users SET is_active = ?, updated_at = datetime('now') WHERE id = ?",
                (int(active), internal_id),
            )
            if not active:
                await auth_service.invalidate_user_sessions(db, internal_id)
                logger.info("SCIM: deactivated user %s", internal_id)
        elif path == "userName" or (not path and isinstance(value, dict) and "userName" in value):
            new_name = value if isinstance(value, str) else value.get("userName", "")
            if new_name:
                await db.execute(
                    "UPDATE users SET username = ?, updated_at = datetime('now') WHERE id = ?",
                    (new_name, internal_id),
                )

    await db.commit()

    cursor = await db.execute(
        "SELECT id, username, email, sso_subject, is_active FROM users WHERE id = ?",
        (internal_id,),
    )
    row = await cursor.fetchone()
    return JSONResponse(
        content=_user_to_scim(row[0], row[1], row[2], row[3], bool(row[4])),
        media_type=SCIM_CONTENT_TYPE,
    )


@router.delete("/Users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    _=Depends(verify_scim_token),
):
    """Delete (deactivate) a user."""
    cursor = await db.execute(
        "SELECT id FROM users WHERE id = ? OR sso_subject = ?", (user_id, user_id)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    internal_id = row[0]
    # Deactivate rather than hard delete (preserve audit trail)
    await db.execute(
        "UPDATE users SET is_active = 0, updated_at = datetime('now') WHERE id = ?",
        (internal_id,),
    )
    await auth_service.invalidate_user_sessions(db, internal_id)
    await db.commit()
    logger.info("SCIM: user %s deleted (deactivated)", internal_id)
    return Response(status_code=204)


# --- Groups ---
@router.get("/Groups")
async def list_groups(
    db: aiosqlite.Connection = Depends(get_db),
    _=Depends(verify_scim_token),
):
    """List all group-role mappings as SCIM groups."""
    cursor = await db.execute("SELECT id, group_name, role FROM group_role_mappings")
    rows = await cursor.fetchall()
    resources = [_group_to_scim(r[0], r[1]) for r in rows]
    return JSONResponse(
        content={
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": len(resources),
            "Resources": resources,
        },
        media_type=SCIM_CONTENT_TYPE,
    )


@router.get("/Groups/{group_id}")
async def get_group(
    group_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    _=Depends(verify_scim_token),
):
    """Get a single group by id."""
    cursor = await db.execute(
        "SELECT id, group_name FROM group_role_mappings WHERE id = ?", (group_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Group not found")
    return JSONResponse(content=_group_to_scim(row[0], row[1]), media_type=SCIM_CONTENT_TYPE)


@router.post("/Groups", status_code=201)
async def create_group(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
    _=Depends(verify_scim_token),
):
    """Create a new group (maps to group_role_mappings with default 'viewer' role)."""
    body = await request.json()
    display_name = body.get("displayName", "")
    if not display_name:
        raise HTTPException(status_code=400, detail="displayName required")

    # Check if already exists
    cursor = await db.execute(
        "SELECT id, group_name FROM group_role_mappings WHERE group_name = ?", (display_name,)
    )
    existing = await cursor.fetchone()
    if existing:
        # Return existing (idempotent)
        return JSONResponse(
            content=_group_to_scim(existing[0], existing[1]),
            status_code=200,
            media_type=SCIM_CONTENT_TYPE,
        )

    group_id = secrets.token_hex(16)
    # Default role for SCIM-created groups: viewer (admin can change in UI)
    await db.execute(
        "INSERT INTO group_role_mappings (id, group_name, role) VALUES (?, ?, 'viewer')",
        (group_id, display_name),
    )
    await db.commit()
    logger.info("SCIM: created group '%s' with default role 'viewer'", display_name)
    return JSONResponse(
        content=_group_to_scim(group_id, display_name),
        status_code=201,
        media_type=SCIM_CONTENT_TYPE,
    )


@router.put("/Groups/{group_id}")
async def replace_group(
    group_id: str,
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
    _=Depends(verify_scim_token),
):
    """Replace (full update) a group."""
    body = await request.json()
    display_name = body.get("displayName", "")
    cursor = await db.execute("SELECT id FROM group_role_mappings WHERE id = ?", (group_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Group not found")
    if display_name:
        await db.execute(
            "UPDATE group_role_mappings SET group_name = ? WHERE id = ?",
            (display_name, group_id),
        )
        await db.commit()
    cursor = await db.execute(
        "SELECT id, group_name FROM group_role_mappings WHERE id = ?", (group_id,)
    )
    row = await cursor.fetchone()
    return JSONResponse(content=_group_to_scim(row[0], row[1]), media_type=SCIM_CONTENT_TYPE)


@router.patch("/Groups/{group_id}")
async def patch_group(
    group_id: str,
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
    _=Depends(verify_scim_token),
):
    """Patch a group (partial update). Authentik sends member changes via PATCH."""
    body = await request.json()
    cursor = await db.execute(
        "SELECT id, group_name FROM group_role_mappings WHERE id = ?", (group_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Group not found")

    for op in body.get("Operations", []):
        path = op.get("path", "")
        value = op.get("value")
        if path == "displayName" and value:
            await db.execute(
                "UPDATE group_role_mappings SET group_name = ? WHERE id = ?",
                (value, group_id),
            )

    await db.commit()
    cursor = await db.execute(
        "SELECT id, group_name FROM group_role_mappings WHERE id = ?", (group_id,)
    )
    row = await cursor.fetchone()
    return JSONResponse(content=_group_to_scim(row[0], row[1]), media_type=SCIM_CONTENT_TYPE)


@router.delete("/Groups/{group_id}", status_code=204)
async def delete_group(
    group_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    _=Depends(verify_scim_token),
):
    """Delete a group mapping."""
    cursor = await db.execute("SELECT id FROM group_role_mappings WHERE id = ?", (group_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Group not found")
    await db.execute("DELETE FROM group_role_mappings WHERE id = ?", (group_id,))
    await db.commit()
    logger.info("SCIM: deleted group %s", group_id)
    return Response(status_code=204)


# --- Helpers ---
def _user_to_scim(
    user_id: str,
    username: str,
    email: str | None,
    sso_subject: str | None,
    active: bool,
) -> dict[str, Any]:
    """Convert internal user record to SCIM User resource."""
    resource: dict[str, Any] = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": user_id,
        "externalId": sso_subject or user_id,
        "userName": username,
        "active": active,
        "meta": {"resourceType": "User"},
    }
    if email:
        resource["emails"] = [{"value": email, "primary": True}]
    return resource


def _group_to_scim(group_id: str, name: str) -> dict[str, Any]:
    """Convert internal group_role_mapping to SCIM Group resource."""
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
        "id": group_id,
        "displayName": name,
        "meta": {"resourceType": "Group"},
    }
