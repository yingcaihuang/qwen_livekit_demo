"""Admin group-role mapping API (requires role:manage capability)."""

import secrets

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUser, require_permission
from app.database import get_db
from app.services.rbac import VALID_ROLES

router = APIRouter(prefix="/api/admin/group-mappings", tags=["admin-roles"])


class GroupMappingCreate(BaseModel):
    group_name: str
    role: str


class GroupMappingResponse(BaseModel):
    id: str
    group_name: str
    role: str
    created_at: str


@router.get("", response_model=list[GroupMappingResponse])
async def list_mappings(
    user: CurrentUser = Depends(require_permission("role:manage")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """List all group → role mappings."""
    cursor = await db.execute(
        "SELECT id, group_name, role, created_at FROM group_role_mappings ORDER BY created_at"
    )
    rows = await cursor.fetchall()
    return [
        GroupMappingResponse(id=r[0], group_name=r[1], role=r[2], created_at=r[3]) for r in rows
    ]


@router.post("", response_model=GroupMappingResponse, status_code=201)
async def create_mapping(
    body: GroupMappingCreate,
    user: CurrentUser = Depends(require_permission("role:manage")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Create a new group → role mapping."""
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"无效角色 '{body.role}'，有效值: {', '.join(sorted(VALID_ROLES))}",
        )
    mapping_id = secrets.token_hex(16)
    try:
        await db.execute(
            "INSERT INTO group_role_mappings (id, group_name, role) VALUES (?, ?, ?)",
            (mapping_id, body.group_name, body.role),
        )
        await db.commit()
    except Exception:
        raise HTTPException(status_code=409, detail=f"组名 '{body.group_name}' 已存在") from None

    cursor = await db.execute(
        "SELECT id, group_name, role, created_at FROM group_role_mappings WHERE id = ?",
        (mapping_id,),
    )
    row = await cursor.fetchone()
    return GroupMappingResponse(id=row[0], group_name=row[1], role=row[2], created_at=row[3])


@router.put("/{mapping_id}", response_model=GroupMappingResponse)
async def update_mapping(
    mapping_id: str,
    body: GroupMappingCreate,
    user: CurrentUser = Depends(require_permission("role:manage")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Update an existing group → role mapping."""
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"无效角色 '{body.role}'，有效值: {', '.join(sorted(VALID_ROLES))}",
        )
    cursor = await db.execute("SELECT id FROM group_role_mappings WHERE id = ?", (mapping_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="映射不存在")

    await db.execute(
        "UPDATE group_role_mappings SET group_name = ?, role = ? WHERE id = ?",
        (body.group_name, body.role, mapping_id),
    )
    await db.commit()

    cursor = await db.execute(
        "SELECT id, group_name, role, created_at FROM group_role_mappings WHERE id = ?",
        (mapping_id,),
    )
    row = await cursor.fetchone()
    return GroupMappingResponse(id=row[0], group_name=row[1], role=row[2], created_at=row[3])


@router.delete("/{mapping_id}", status_code=204)
async def delete_mapping(
    mapping_id: str,
    user: CurrentUser = Depends(require_permission("role:manage")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Delete a group → role mapping."""
    cursor = await db.execute("SELECT id FROM group_role_mappings WHERE id = ?", (mapping_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="映射不存在")
    await db.execute("DELETE FROM group_role_mappings WHERE id = ?", (mapping_id,))
    await db.commit()
