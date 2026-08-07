"""REST API routes for dashboard statistics.

Delegates cross-type aggregation (sessions + image_generations) to
``app.services.dashboard_service`` so voice/chat/image usage is combined
consistently. All endpoints accept optional filters and return zero values /
empty lists for empty match sets rather than errors (Requirement 7.5).
"""

import aiosqlite
from fastapi import APIRouter, Depends, Query

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
):
    """Return overall system statistics aggregated across all test types.

    Combines the ``sessions`` table (voice/chat) with ``image_generations``
    (image). ``total_tests`` is the combined count of sessions and image
    generations; ``total_sessions`` is retained for backward compatibility.

    - ``type``: optional filter restricting aggregation to a single test type.
    - ``instance_id``: optional filter restricting aggregation to one instance.
    """
    return await dashboard_service.compute_stats(db, type_filter=type, instance_id=instance_id)


@router.get("/usage-by-instance", response_model=list[InstanceUsage])
async def get_usage_by_instance(
    type: InstanceType | None = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Return per-instance aggregation of test count and token usage.

    Each instance's count combines its sessions and image generations. An
    optional ``type`` filter restricts to instances of a single test type.
    """
    return await dashboard_service.compute_usage_by_instance(db, type_filter=type)


@router.get("/usage-by-type", response_model=list[TypeUsage])
async def get_usage_by_type(
    instance_id: str | None = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Return usage aggregated by test type (``voice`` / ``chat`` / ``image``).

    Always returns one entry per type; a type with no matching records yields
    zero values. An optional ``instance_id`` filter restricts to one instance.
    """
    return await dashboard_service.compute_usage_by_type(db, instance_id=instance_id)
