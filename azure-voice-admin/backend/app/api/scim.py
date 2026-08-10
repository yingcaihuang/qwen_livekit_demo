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


async def _sync_group_members(
    db: aiosqlite.Connection, group_name: str, member_external_ids: list[str]
) -> None:
    """Sync group membership: update sso_groups and recompute roles for affected users.

    For each user whose sso_subject is in member_external_ids, ensure group_name
    is in their sso_groups. For users previously in this group but no longer listed,
    remove the group from their sso_groups.
    """
    import json as json_mod

    if not member_external_ids:
        # No members — remove this group from all users who had it
        cursor = await db.execute(
            "SELECT id, sso_groups FROM users WHERE auth_source = 'sso' AND sso_groups LIKE ?",
            (f"%{group_name}%",),
        )
        rows = await cursor.fetchall()
        for row in rows:
            user_id = row[0]
            groups = json_mod.loads(row[1] or "[]")
            if group_name in groups:
                groups.remove(group_name)
                await db.execute(
                    "UPDATE users SET sso_groups = ?, updated_at = datetime('now') WHERE id = ?",
                    (json_mod.dumps(groups), user_id),
                )
                # Recompute roles
                cursor2 = await db.execute(
                    "SELECT role_override FROM users WHERE id = ?", (user_id,)
                )
                override_row = await cursor2.fetchone()
                if not (override_row and override_row[0]):
                    roles = await _compute_roles(db, groups)
                    await db.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
                    for role in roles:
                        await db.execute(
                            "INSERT INTO user_roles (user_id, role) VALUES (?, ?)",
                            (user_id, role),
                        )
        return

    # Find users matching the member external IDs
    placeholders = ",".join("?" for _ in member_external_ids)
    cursor = await db.execute(
        f"SELECT id, sso_subject, sso_groups FROM users WHERE id IN ({placeholders}) OR sso_subject IN ({placeholders})",
        member_external_ids + member_external_ids,
    )
    member_rows = await cursor.fetchall()
    member_user_ids = set()

    for row in member_rows:
        user_id, _subject, raw_groups = row[0], row[1], row[2]
        member_user_ids.add(user_id)
        groups = json_mod.loads(raw_groups or "[]")
        if group_name not in groups:
            groups.append(group_name)
            await db.execute(
                "UPDATE users SET sso_groups = ?, updated_at = datetime('now') WHERE id = ?",
                (json_mod.dumps(groups), user_id),
            )
        # Recompute roles for this user
        cursor2 = await db.execute("SELECT role_override FROM users WHERE id = ?", (user_id,))
        override_row = await cursor2.fetchone()
        if not (override_row and override_row[0]):
            roles = await _compute_roles(db, groups)
            await db.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
            for role in roles:
                await db.execute(
                    "INSERT INTO user_roles (user_id, role) VALUES (?, ?)", (user_id, role)
                )

    # Remove group from users who are no longer members
    cursor = await db.execute(
        "SELECT id, sso_groups FROM users WHERE auth_source = 'sso' AND sso_groups LIKE ?",
        (f"%{group_name}%",),
    )
    all_with_group = await cursor.fetchall()
    for row in all_with_group:
        user_id = row[0]
        if user_id not in member_user_ids:
            groups = json_mod.loads(row[1] or "[]")
            if group_name in groups:
                groups.remove(group_name)
                await db.execute(
                    "UPDATE users SET sso_groups = ?, updated_at = datetime('now') WHERE id = ?",
                    (json_mod.dumps(groups), user_id),
                )
                # Recompute roles
                cursor2 = await db.execute(
                    "SELECT role_override FROM users WHERE id = ?", (user_id,)
                )
                override_row = await cursor2.fetchone()
                if not (override_row and override_row[0]):
                    roles = await _compute_roles(db, groups)
                    await db.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
                    for role in roles:
                        await db.execute(
                            "INSERT INTO user_roles (user_id, role) VALUES (?, ?)",
                            (user_id, role),
                        )

    logger.info("SCIM: synced group '%s' members (%d users)", group_name, len(member_user_ids))


@router.put("/Groups/{group_id}")
async def replace_group(
    group_id: str,
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
    _=Depends(verify_scim_token),
):
    """Replace (full update) a group. Processes members for role sync."""
    body = await request.json()
    display_name = body.get("displayName", "")
    members = body.get("members", [])

    cursor = await db.execute(
        "SELECT id, group_name FROM group_role_mappings WHERE id = ?", (group_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Group not found")

    current_group_name = row[1]

    if display_name and display_name != current_group_name:
        await db.execute(
            "UPDATE group_role_mappings SET group_name = ? WHERE id = ?",
            (display_name, group_id),
        )
        current_group_name = display_name

    # Sync members - extract external IDs from members array
    member_external_ids = [m.get("value", "") for m in members if m.get("value")]
    await _sync_group_members(db, current_group_name, member_external_ids)

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
    """Patch a group (partial update). Handles member add/remove from Authentik."""
    import json as json_mod

    body = await request.json()
    cursor = await db.execute(
        "SELECT id, group_name FROM group_role_mappings WHERE id = ?", (group_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Group not found")

    group_name = row[1]

    for op in body.get("Operations", []):
        op_type = op.get("op", "").lower()
        path = op.get("path", "")
        value = op.get("value")

        if path == "displayName" and value:
            await db.execute(
                "UPDATE group_role_mappings SET group_name = ? WHERE id = ?",
                (value, group_id),
            )
            group_name = value
        elif "members" in path or (not path and isinstance(value, list)):
            # Handle member operations
            member_values = value if isinstance(value, list) else [value] if value else []
            member_ids = [m.get("value", m) if isinstance(m, dict) else m for m in member_values]
            member_ids = [mid for mid in member_ids if mid]

            if op_type == "add" or op_type == "replace":
                # Add these users to the group
                for ext_id in member_ids:
                    cursor2 = await db.execute(
                        "SELECT id, sso_groups FROM users WHERE id = ? OR sso_subject = ?",
                        (ext_id, ext_id),
                    )
                    user_row = await cursor2.fetchone()
                    if user_row:
                        user_id = user_row[0]
                        groups = json_mod.loads(user_row[1] or "[]")
                        if group_name not in groups:
                            groups.append(group_name)
                            await db.execute(
                                "UPDATE users SET sso_groups = ?, updated_at = datetime('now') "
                                "WHERE id = ?",
                                (json_mod.dumps(groups), user_id),
                            )
                            # Recompute roles
                            cursor3 = await db.execute(
                                "SELECT role_override FROM users WHERE id = ?", (user_id,)
                            )
                            override_row = await cursor3.fetchone()
                            if not (override_row and override_row[0]):
                                roles = await _compute_roles(db, groups)
                                await db.execute(
                                    "DELETE FROM user_roles WHERE user_id = ?", (user_id,)
                                )
                                for role in roles:
                                    await db.execute(
                                        "INSERT INTO user_roles (user_id, role) VALUES (?, ?)",
                                        (user_id, role),
                                    )
                        logger.info("SCIM: added user %s to group '%s'", user_id, group_name)

            elif op_type == "remove":
                # Remove these users from the group
                for ext_id in member_ids:
                    cursor2 = await db.execute(
                        "SELECT id, sso_groups FROM users WHERE id = ? OR sso_subject = ?",
                        (ext_id, ext_id),
                    )
                    user_row = await cursor2.fetchone()
                    if user_row:
                        user_id = user_row[0]
                        groups = json_mod.loads(user_row[1] or "[]")
                        if group_name in groups:
                            groups.remove(group_name)
                            await db.execute(
                                "UPDATE users SET sso_groups = ?, updated_at = datetime('now') "
                                "WHERE id = ?",
                                (json_mod.dumps(groups), user_id),
                            )
                            # Recompute roles
                            cursor3 = await db.execute(
                                "SELECT role_override FROM users WHERE id = ?", (user_id,)
                            )
                            override_row = await cursor3.fetchone()
                            if not (override_row and override_row[0]):
                                roles = await _compute_roles(db, groups)
                                await db.execute(
                                    "DELETE FROM user_roles WHERE user_id = ?", (user_id,)
                                )
                                for role in roles:
                                    await db.execute(
                                        "INSERT INTO user_roles (user_id, role) VALUES (?, ?)",
                                        (user_id, role),
                                    )
                        logger.info("SCIM: removed user %s from group '%s'", user_id, group_name)

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
