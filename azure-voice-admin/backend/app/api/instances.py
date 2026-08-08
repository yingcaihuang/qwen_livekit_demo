"""REST API routes for Instance configuration management."""

import aiosqlite
from fastapi import APIRouter, Depends, Query, Response
from starlette.status import HTTP_201_CREATED, HTTP_204_NO_CONTENT

from app.api.deps import CurrentUser, require_permission
from app.database import get_db
from app.models.instance import (
    InstanceCreate,
    InstanceDetail,
    InstanceSummary,
    InstanceUpdate,
)
from app.services.instance_service import InstanceService

router = APIRouter(prefix="/api/instances", tags=["instances"])

_service = InstanceService()


@router.get("", response_model=list[InstanceSummary])
async def list_instances(
    type: str | None = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(require_permission("instance:read")),
):
    """List all instance configurations (API keys are not exposed).

    An optional ``type`` query parameter filters the result to instances of the
    given type (Requirement 1.8). Multi-tenant: only shows user's own instances
    unless user has ``resource:read:all``.
    """
    return await _service.list_instances(db, type_filter=type, user=user)


@router.post("", status_code=HTTP_201_CREATED)
async def create_instance(
    data: InstanceCreate,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(require_permission("instance:write")),
):
    """Create a new instance configuration.

    Returns 422 if validation fails (empty fields).
    Returns 409 if the instance name already exists.
    Records ``created_by = user.id`` for multi-tenant isolation.
    """
    return await _service.create_instance(db, data, user=user)


@router.get("/{instance_id}", response_model=InstanceDetail)
async def get_instance(
    instance_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(require_permission("instance:read")),
):
    """Get instance detail including masked API key and token usage statistics.

    Returns 404 if not found or not owned by user (when lacking resource:read:all).
    """
    return await _service.get_instance(db, instance_id, user=user)


@router.put("/{instance_id}")
async def update_instance(
    instance_id: str,
    data: InstanceUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(require_permission("instance:write")),
):
    """Update an existing instance configuration (partial update).

    Returns 404 if not found or not owned by user.
    Returns 422 if validation fails (empty fields).
    Returns 409 if the updated name conflicts with another instance.
    """
    return await _service.update_instance(db, instance_id, data, user=user)


@router.delete("/{instance_id}", status_code=HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(require_permission("instance:write")),
):
    """Delete an instance configuration.

    Returns 404 if not found or not owned by user.
    Returns 409 if the instance has active sessions.
    """
    await _service.delete_instance(db, instance_id, user=user)
    return Response(status_code=HTTP_204_NO_CONTENT)
