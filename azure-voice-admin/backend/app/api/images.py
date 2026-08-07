"""REST API routes for Image Generation (Images generations/edits).

Exposes the image test path described in ``design.md`` (section "Image API").
All heavy lifting (Azure calls, file persistence, path-traversal guarding,
lifecycle) lives in :class:`ImageService`; these routes are thin adapters that
parse ``multipart/form-data`` input, serve stored image files, and expose the
generation history / detail.

Route ordering note:
FastAPI matches routes by path *shape*, so the single-segment detail route
(``/{generation_id}``) and the two-segment file route
(``/{generation_id}/{index}``) do not collide with each other or with the list
route (path ``""``). The list route is registered with an empty path so
``GET /api/images`` resolves to the history list rather than being shadowed by a
``{generation_id}`` matcher. ``POST /generations`` is a distinct verb+path and
never conflicts with the ``GET /{generation_id}`` detail route.
"""

import aiosqlite
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from starlette.status import HTTP_202_ACCEPTED, HTTP_204_NO_CONTENT

from app.database import get_db
from app.models.image import (
    ImageGenerationRequest,
    ImageParams,
)
from app.services.image_service import ImageService

router = APIRouter(prefix="/api/images", tags=["images"])

# Singleton service instance (mirrors the pattern used in sessions.py / chat.py).
_image_service = ImageService()


@router.get("")
async def list_generations(
    instance_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: aiosqlite.Connection = Depends(get_db),
) -> list[dict]:
    """List image generation history (most recent first), optionally by instance.

    Registered with an empty path so ``GET /api/images`` is not shadowed by the
    ``/{generation_id}`` detail route.
    """
    return await _image_service.list_generations(
        db, instance_id=instance_id, page=page, page_size=page_size
    )


@router.post("/generations", status_code=HTTP_202_ACCEPTED)
async def create_generation(
    instance_id: str = Form(...),
    prompt: str = Form(...),
    size: str = Form("1024x1024"),
    quality: str = Form("high"),
    output_format: str = Form("png"),
    compression: int = Form(100),
    n: int = Form(1),
    file: UploadFile | None = File(default=None),
    db: aiosqlite.Connection = Depends(get_db),
) -> JSONResponse:
    """Enqueue an image generation job from a ``multipart/form-data`` request.

    Builds an :class:`ImageGenerationRequest` (with nested :class:`ImageParams`)
    from the form fields and delegates to
    :meth:`ImageService.enqueue_generation`. Azure is NOT called here: the
    request returns immediately (HTTP 202) with a ``pending`` record (same shape
    as the detail endpoint, with empty ``images``). A background worker performs
    the Azure call and updates the row status to ``completed`` / ``failed``.
    When a reference ``file`` is attached, the worker takes the Azure *edits*
    path; otherwise it uses *generations*.
    """
    request = ImageGenerationRequest(
        instance_id=instance_id,
        prompt=prompt,
        params=ImageParams(
            size=size,
            quality=quality,
            output_format=output_format,
            compression=compression,
            n=n,
        ),
    )
    record = await _image_service.enqueue_generation(db, request, reference_image=file)
    return JSONResponse(content=record, status_code=HTTP_202_ACCEPTED)


@router.get("/{generation_id}")
async def get_generation(generation_id: str, db: aiosqlite.Connection = Depends(get_db)) -> dict:
    """Get a single image generation's metadata (prompt/params/usage/images).

    Returns 404 if the generation does not exist.
    """
    generation = await _image_service.get_generation(db, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Image generation not found")
    return generation


@router.get("/{generation_id}/{index}")
async def get_image_file(generation_id: str, index: int) -> FileResponse:
    """Serve a stored image file, guarded against path traversal (Req 9.5).

    Delegates path resolution to :meth:`ImageService.resolve_image_path`, which
    returns ``None`` when the resolved path escapes the images root or the file
    is missing. Both cases surface as 404 (no file outside the root is served).
    """
    resolved = _image_service.resolve_image_path(generation_id, index)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Image not found")
    path, media_type = resolved
    return FileResponse(str(path), media_type=media_type)


@router.delete("/{generation_id}", status_code=HTTP_204_NO_CONTENT)
async def delete_generation(
    generation_id: str, db: aiosqlite.Connection = Depends(get_db)
) -> Response:
    """Delete an image generation's on-disk files and metadata row.

    Returns 204 on success. The service raises 404 when the generation does not
    exist.
    """
    await _image_service.delete_generation(db, generation_id)
    return Response(status_code=HTTP_204_NO_CONTENT)
