"""Admin API for viewing audit logs."""

import aiosqlite
from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, require_permission
from app.database import get_db

router = APIRouter(prefix="/api/admin/audit", tags=["audit"])


@router.get("")
async def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user_id: str | None = Query(default=None),
    method: str | None = Query(default=None),
    path_contains: str | None = Query(default=None),
    user: CurrentUser = Depends(require_permission("audit:read")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """List audit logs with pagination and filters. Requires audit:read capability."""
    conditions = []
    params: list = []

    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)
    if method:
        conditions.append("method = ?")
        params.append(method.upper())
    if path_contains:
        conditions.append("path LIKE ?")
        params.append(f"%{path_contains}%")

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    # Count total
    count_row = await (
        await db.execute(f"SELECT COUNT(*) FROM audit_logs {where}", params)
    ).fetchone()
    total = count_row[0]

    # Fetch page
    offset = (page - 1) * page_size
    cursor = await db.execute(
        f"SELECT id, timestamp, user_id, username, method, path, status_code, ip_address, duration_ms, request_body, detail FROM audit_logs {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        params + [page_size, offset],
    )
    rows = await cursor.fetchall()

    items = [
        {
            "id": r[0],
            "timestamp": r[1],
            "user_id": r[2],
            "username": r[3],
            "method": r[4],
            "path": r[5],
            "status_code": r[6],
            "ip_address": r[7],
            "duration_ms": r[8],
            "request_body": r[9],
            "detail": r[10],
        }
        for r in rows
    ]

    return {"items": items, "total": total, "page": page, "page_size": page_size}
