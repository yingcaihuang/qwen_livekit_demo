"""REST API routes for Instance configuration management."""

import aiosqlite
from fastapi import APIRouter, Depends, Query, Response
from starlette.status import HTTP_201_CREATED, HTTP_204_NO_CONTENT

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
):
    """List all instance configurations (API keys are not exposed).

    An optional ``type`` query parameter filters the result to instances of the
    given type (Requirement 1.8).
    """
    return await _service.list_instances(db, type_filter=type)


@router.post("", status_code=HTTP_201_CREATED)
async def create_instance(data: InstanceCreate, db: aiosqlite.Connection = Depends(get_db)):
    """Create a new instance configuration.

    Returns 422 if validation fails (empty fields).
    Returns 409 if the instance name already exists.
    """
    return await _service.create_instance(db, data)


@router.get("/{instance_id}", response_model=InstanceDetail)
async def get_instance(instance_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Get instance detail including masked API key and token usage statistics.

    Returns 404 if not found.
    """
    return await _service.get_instance(db, instance_id)


@router.put("/{instance_id}")
async def update_instance(
    instance_id: str,
    data: InstanceUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Update an existing instance configuration (partial update).

    Returns 404 if not found.
    Returns 422 if validation fails (empty fields).
    Returns 409 if the updated name conflicts with another instance.
    """
    return await _service.update_instance(db, instance_id, data)


@router.delete("/{instance_id}", status_code=HTTP_204_NO_CONTENT)
async def delete_instance(instance_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Delete an instance configuration.

    Returns 404 if not found.
    Returns 409 if the instance has active sessions.
    """
    await _service.delete_instance(db, instance_id)
    return Response(status_code=HTTP_204_NO_CONTENT)
