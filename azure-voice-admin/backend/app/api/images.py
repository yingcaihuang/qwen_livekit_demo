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

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.database import get_db
from app.models.image import (
    ImageGenerationRequest,
    ImageParams,
)
from app.services.image_service import ImageService

router = APIRouter(prefix="/api/images", tags=["images"])

# Singleton service instance (mirrors the pattern used in sessions.py / chat.py).
_image_service = ImageService()

# Maximum reference image size (50MB, Azure limit)
_MAX_IMAGE_BYTES = 50 * 1024 * 1024


async def _is_allowed_image(file: UploadFile) -> bool:
    """Check if file is PNG or JPEG by reading magic bytes."""
    header = await file.read(8)
    await file.seek(0)
    if not header:
        return False
    # PNG magic bytes
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    # JPEG SOI marker
    if header[:3] == b"\xff\xd8\xff":
        return True
    return False


async def _is_png(file: UploadFile) -> bool:
    """Check if file is PNG by reading magic bytes."""
    header = await file.read(8)
    await file.seek(0)
    return len(header) >= 8 and header[:8] == b"\x89PNG\r\n\x1a\n"


@router.get("")
async def list_generations(
    instance_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """List image generation history (most recent first), optionally by instance.

    Multi-tenant: only shows user's own generations unless user has
    ``resource:read:all``.
    """
    return await _image_service.list_generations(
        db, instance_id=instance_id, page=page, page_size=page_size, user=user
    )


@router.get("/queue")
async def list_queue(
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Return the live image job queue (pending + processing jobs).

    Multi-tenant: only shows user's own queued jobs unless user has
    ``resource:read:all``.
    """
    return await _image_service.list_queue(db, user=user)


@router.post("/generations", status_code=HTTP_202_ACCEPTED)
async def create_generation(
    instance_id: str = Form(...),
    prompt: str = Form(...),
    size: str = Form("1024x1024"),
    quality: str = Form("high"),
    output_format: str = Form("png"),
    compression: int = Form(100),
    n: int = Form(1),
    input_fidelity: str | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    mask: UploadFile | None = File(default=None),
    # Legacy single-file field for backward compatibility
    file: UploadFile | None = File(default=None),
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(require_permission("image:use")),
) -> JSONResponse:
    """Enqueue an image generation job from a ``multipart/form-data`` request.

    Supports multiple reference images (files field), optional mask, and input_fidelity.
    Legacy single-file (file field) is supported for backward compatibility.
    Records ``created_by = user.id`` for multi-tenant isolation.
    """
    # Merge legacy `file` into files list for unified handling
    all_files = list(files)
    if file is not None and not files:
        all_files = [file]

    # Validate reference image count (max 10)
    if len(all_files) > 10:
        raise HTTPException(status_code=422, detail="参考图最多 10 张")

    # Validate each reference image format and size
    for f in all_files:
        if not await _is_allowed_image(f):
            raise HTTPException(
                status_code=422, detail=f"仅支持 PNG 和 JPG 格式（文件: {f.filename}）"
            )
        content = await f.read()
        if len(content) > _MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413, detail=f"图片大小不能超过 50MB（文件: {f.filename}）"
            )
        await f.seek(0)

    # Validate mask
    if mask is not None:
        if not await _is_png(mask):
            raise HTTPException(status_code=422, detail="遮罩图必须是 PNG 格式")
        mask_content = await mask.read()
        if len(mask_content) > _MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="遮罩图大小不能超过 50MB")
        await mask.seek(0)
        if not all_files:
            raise HTTPException(status_code=422, detail="使用遮罩需要至少上传一张参考图")

    request = ImageGenerationRequest(
        instance_id=instance_id,
        prompt=prompt,
        params=ImageParams(
            size=size,
            quality=quality,
            output_format=output_format,
            compression=compression,
            n=n,
            input_fidelity=input_fidelity,
        ),
    )
    record = await _image_service.enqueue_generation(
        db,
        request,
        reference_images=all_files if all_files else None,
        mask=mask,
        created_by=user.id,
    )
    return JSONResponse(content=record, status_code=HTTP_202_ACCEPTED)


@router.get("/{generation_id}")
async def get_generation(
    generation_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Get a single image generation's metadata (prompt/params/usage/images).

    Returns 404 if the generation does not exist or not owned.
    """
    generation = await _image_service.get_generation(db, generation_id, user=user)
    if generation is None:
        raise HTTPException(status_code=404, detail="Image generation not found")

    # Enrich with instance endpoint/deployment for API code snippet
    if generation.get("instance_id"):
        inst_cursor = await db.execute(
            "SELECT endpoint, deployment FROM instances WHERE id = ?",
            (generation["instance_id"],),
        )
        inst_row = await inst_cursor.fetchone()
        if inst_row:
            generation["endpoint"] = inst_row[0]
            generation["deployment"] = inst_row[1]

    return generation


@router.get("/{generation_id}/ref/{ref_index}")
async def get_reference_image(
    generation_id: str,
    ref_index: int,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> FileResponse:
    """Serve a stored reference image file for history viewing."""
    from app.config import IMAGES_DIR

    # Ownership check
    cursor = await db.execute(
        "SELECT id, created_by FROM image_generations WHERE id = ?", (generation_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Image not found")
    if "resource:read:all" not in user.capabilities and row[1] != user.id:
        raise HTTPException(status_code=404, detail="Image not found")

    gen_dir = IMAGES_DIR / generation_id
    if not gen_dir.exists():
        raise HTTPException(status_code=404, detail="Reference image not found")

    # Find reference files (indexed format first, then legacy)
    refs = sorted(gen_dir.glob("_reference_*"))
    if not refs:
        refs = sorted(gen_dir.glob("_reference.*"))

    if ref_index < 0 or ref_index >= len(refs):
        raise HTTPException(status_code=404, detail="Reference image not found")

    path = refs[ref_index]
    # Path traversal guard
    if not path.resolve().is_relative_to(IMAGES_DIR.resolve()):
        raise HTTPException(status_code=404, detail="Reference image not found")

    # Determine media type from extension
    ext = path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    media_type = media_types.get(ext, "image/png")

    return FileResponse(str(path), media_type=media_type)


@router.get("/{generation_id}/{index}")
async def get_image_file(
    generation_id: str,
    index: int,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> FileResponse:
    """Serve a stored image file, guarded against path traversal (Req 9.5).

    Also checks ownership: returns 404 if not owned.
    """
    # Ownership check
    cursor = await db.execute(
        "SELECT id, created_by FROM image_generations WHERE id = ?", (generation_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Image not found")
    if "resource:read:all" not in user.capabilities and row[1] != user.id:
        raise HTTPException(status_code=404, detail="Image not found")

    resolved = _image_service.resolve_image_path(generation_id, index)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Image not found")
    path, media_type = resolved
    return FileResponse(str(path), media_type=media_type)


@router.delete("/{generation_id}", status_code=HTTP_204_NO_CONTENT)
async def delete_generation(
    generation_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    """Delete an image generation's on-disk files and metadata row.

    Returns 204 on success. Returns 404 when the generation does not
    exist or not owned.
    """
    # Ownership check
    cursor = await db.execute(
        "SELECT id, created_by FROM image_generations WHERE id = ?", (generation_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Image generation not found")
    if "resource:read:all" not in user.capabilities and row[1] != user.id:
        raise HTTPException(status_code=404, detail="Image generation not found")

    await _image_service.delete_generation(db, generation_id)
    return Response(status_code=HTTP_204_NO_CONTENT)
