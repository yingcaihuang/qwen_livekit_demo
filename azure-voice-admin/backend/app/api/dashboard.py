"""REST API routes for dashboard statistics.

Delegates cross-type aggregation (sessions + image_generations) to
``app.services.dashboard_service`` so voice/chat/image usage is combined
consistently. All endpoints accept optional filters and return zero values /
empty lists for empty match sets rather than errors (Requirement 7.5).
"""

import aiosqlite
from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, require_permission
from app.database import get_db
from app.models.dashboard import DashboardStats, InstanceUsage, TypeUsage
from app.models.instance import InstanceType
from app.services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    type: InstanceType | None = Query(default=None),
    instance_id: str | None = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(require_permission("dashboard:read")),
):
    """Return overall system statistics aggregated across all test types.

    Combines the ``sessions`` table (voice/chat) with ``image_generations``
    (image). Multi-tenant: filters by ``created_by`` when user lacks
    ``resource:read:all``.
    """
    owner_id = None if "resource:read:all" in user.capabilities else user.id
    return await dashboard_service.compute_stats(
        db, type_filter=type, instance_id=instance_id, owner_id=owner_id
    )


@router.get("/usage-by-instance", response_model=list[InstanceUsage])
async def get_usage_by_instance(
    type: InstanceType | None = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(require_permission("dashboard:read")),
):
    """Return per-instance aggregation of test count and token usage.

    Multi-tenant: filters by ``created_by`` when user lacks ``resource:read:all``.
    """
    owner_id = None if "resource:read:all" in user.capabilities else user.id
    return await dashboard_service.compute_usage_by_instance(
        db, type_filter=type, owner_id=owner_id
    )


@router.get("/usage-by-type", response_model=list[TypeUsage])
async def get_usage_by_type(
    instance_id: str | None = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(require_permission("dashboard:read")),
):
    """Return usage aggregated by test type (``voice`` / ``chat`` / ``image``).

    Multi-tenant: filters by ``created_by`` when user lacks ``resource:read:all``.
    """
    owner_id = None if "resource:read:all" in user.capabilities else user.id
    return await dashboard_service.compute_usage_by_type(
        db, instance_id=instance_id, owner_id=owner_id
    )
