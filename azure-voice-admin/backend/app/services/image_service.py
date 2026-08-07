"""Service layer for Image Generation (Azure OpenAI Images generations/edits).

Implements the image test path described in ``design.md`` (section "Image 服务层"):
calls Azure Images ``generations`` (no reference image) or ``edits`` (with a
reference image), decodes the returned base64 images, writes them to disk under
``DATA_DIR/images/<generation_id>/<index>.<ext>`` and persists a metadata row.

Key invariants (Correctness Properties):
- Property 7:  ``compression`` is clamped to ``[0, 100]``.
- Property 11: the number of requested variations equals the number of saved
  files / returned URLs.
- Property 12: files are written FIRST; if any file write fails the partial
  directory is cleaned up and NO metadata row is persisted (no dangling refs).
- Property 18: ``resolve_image_path`` guards against path traversal by ensuring
  the resolved absolute path stays within the images root directory.

All Azure calls capture failures and surface a readable error (Requirement 9.2);
the ``api-key`` is never written to logs (Requirement 9.3).
"""

import base64
import binascii
import json
import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

import aiohttp
import aiosqlite
from fastapi import HTTPException, UploadFile
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.config import (
    IMAGES_DIR,
    MAX_REFERENCE_IMAGE_BYTES,
)
from app.models.image import (
    ImageGenerationRequest,
    ImageGenerationResponse,
    ImageParams,
)
from app.services.azure_urls import resolve_azure_url

logger = logging.getLogger("azure_openai_admin")

# Reference image (UploadFile / bytes) or None.
ReferenceImage = UploadFile | bytes | None


class ImageService:
    """Business logic for image generation, storage, and lifecycle."""

    # Map output_format -> media type served by GET /api/images/{id}/{index}.
    _MEDIA_TYPES: dict[str, str] = {
        "png": "image/png",
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
    }

    # ------------------------------------------------------------------
    # Parameter / URL helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clamp_compression(value: int) -> int:
        """Constrain the compression level to ``[0, 100]`` (Requirement 4.7)."""
        return max(0, min(100, int(value)))

    @staticmethod
    def _azure_generations_url(endpoint: str) -> str:
        """Resolve the Azure Images *generations* URL (v1 surface).

        See ``resolve_azure_url``.
        """
        return resolve_azure_url(endpoint, "images/generations")

    @staticmethod
    def _azure_edits_url(endpoint: str) -> str:
        """Resolve the Azure Images *edits* URL (v1 surface).

        The edits operation is derived even when the configured endpoint is a
        full URL that ends in a different verb (e.g. ``…/images/generations``).
        See ``resolve_azure_url``.
        """
        return resolve_azure_url(endpoint, "images/edits")

    @classmethod
    def _media_type_for(cls, output_format: str) -> str:
        """Return the media type for a given output format, defaulting to png."""
        return cls._MEDIA_TYPES.get((output_format or "").lower(), "image/png")

    # ------------------------------------------------------------------
    # Credential loading
    # ------------------------------------------------------------------
    @staticmethod
    async def _load_instance(db: aiosqlite.Connection, instance_id: str) -> tuple[str, str, str]:
        """Load ``(endpoint, api_key, deployment)`` for an image instance.

        Raises HTTPException 404 if the instance does not exist.
        """
        cursor = await db.execute(
            "SELECT endpoint, api_key, deployment FROM instances WHERE id = ?",
            (instance_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Instance not found")
        return row[0], row[1], row[2]

    @staticmethod
    async def _read_reference_bytes(reference_image: ReferenceImage) -> bytes | None:
        """Normalize a reference image (UploadFile | bytes | None) to bytes.

        Enforces the configured maximum size (Requirement defensive guard).
        Returns ``None`` when no reference image was supplied.
        """
        if reference_image is None:
            return None

        if isinstance(reference_image, bytes):
            data = reference_image
        elif isinstance(reference_image, UploadFile | StarletteUploadFile):
            # FastAPI may inject Starlette's UploadFile (which fastapi.UploadFile
            # subclasses), so accept both to keep the edits path working.
            data = await reference_image.read()
        else:  # pragma: no cover - defensive
            raise HTTPException(status_code=422, detail="Unsupported reference image type")

        if not data:
            return None
        if len(data) > MAX_REFERENCE_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Reference image exceeds the maximum allowed size "
                    f"({MAX_REFERENCE_IMAGE_BYTES} bytes)"
                ),
            )
        return data

    # ------------------------------------------------------------------
    # Azure calls
    # ------------------------------------------------------------------
    async def _call_generations(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        prompt: str,
        params: ImageParams,
    ) -> dict:
        """Call Azure Images ``generations`` with a JSON body (no reference image)."""
        url = self._azure_generations_url(endpoint)
        body = {
            "model": deployment,
            "prompt": prompt,
            "size": params.size,
            "quality": params.quality,
            "output_format": params.output_format,
            "output_compression": params.compression,
            "n": params.n,
        }
        headers = {"api-key": api_key, "Content-Type": "application/json"}
        return await self._post(url, headers=headers, json_body=body)

    async def _call_edits(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        prompt: str,
        params: ImageParams,
        reference_bytes: bytes,
    ) -> dict:
        """Call Azure Images ``edits`` with multipart form-data (with reference image)."""
        url = self._azure_edits_url(endpoint)
        form = aiohttp.FormData()
        form.add_field("model", deployment)
        form.add_field(
            "image",
            reference_bytes,
            filename="reference.png",
            content_type="application/octet-stream",
        )
        form.add_field("prompt", prompt)
        form.add_field("size", params.size)
        form.add_field("quality", params.quality)
        form.add_field("output_format", params.output_format)
        form.add_field("output_compression", str(params.compression))
        form.add_field("n", str(params.n))
        headers = {"api-key": api_key}
        return await self._post(url, headers=headers, data=form)

    @staticmethod
    async def _post(
        url: str,
        *,
        headers: dict,
        json_body: dict | None = None,
        data: aiohttp.FormData | None = None,
    ) -> dict:
        """Execute a POST to Azure and return the parsed JSON body.

        Converts network errors and non-2xx responses into a readable
        HTTPException (Requirement 9.2). The ``api-key`` header is never logged
        (Requirement 9.3).
        """
        # Log the exact outgoing request URL so users can see the real path in
        # `docker compose logs backend` (never log the api-key or headers).
        logger.info("Azure image request -> POST %s", url)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=json_body, data=data) as resp:
                    text = await resp.text()
                    if resp.status < 200 or resp.status >= 300:
                        logger.error(
                            "Azure Images call failed: status=%s url=%s body=%s",
                            resp.status,
                            url,
                            text[:1000],
                        )
                        raise HTTPException(
                            status_code=502,
                            detail=(
                                "Azure image API returned an error "
                                f"(status {resp.status}): {text[:500]}"
                            ),
                        )
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise HTTPException(
                            status_code=502,
                            detail="Azure image API returned a non-JSON response",
                        ) from exc
        except aiohttp.ClientError as exc:
            logger.error("Azure Images request error (url=%s): %s", url, exc)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach Azure image API: {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    async def generate(
        self,
        db: aiosqlite.Connection,
        request: ImageGenerationRequest,
        reference_image: ReferenceImage = None,
    ) -> ImageGenerationResponse:
        """Generate (or edit) images, persist files then metadata, and return URLs.

        Order of operations enforces Property 12: all files are written first;
        if any write fails the partial directory is removed and no metadata row
        is persisted (Requirement 5.5). Only after files are safely on disk is
        the ``image_generations`` metadata row inserted.
        """
        # 1) Load credentials for the target instance.
        endpoint, api_key, deployment = await self._load_instance(db, request.instance_id)

        # 2) Normalize / clamp parameters (Requirement 4.7 / Property 7).
        params = ImageParams(
            size=request.params.size,
            quality=request.params.quality,
            output_format=request.params.output_format,
            compression=self._clamp_compression(request.params.compression),
            n=max(1, int(request.params.n)),
        )

        reference_bytes = await self._read_reference_bytes(reference_image)
        has_reference = reference_bytes is not None

        # 3) Call Azure (edits when a reference image is present, else generations).
        if has_reference:
            payload = await self._call_edits(
                endpoint, api_key, deployment, request.prompt, params, reference_bytes
            )
        else:
            payload = await self._call_generations(
                endpoint, api_key, deployment, request.prompt, params
            )

        # 4) Extract the base64 image variations.
        data_items = payload.get("data") or []
        if not data_items:
            raise HTTPException(
                status_code=502,
                detail="Azure image API returned no image data",
            )

        usage = payload.get("usage") or {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)

        generation_id = uuid.uuid4().hex
        ext = (params.output_format or "png").lower()
        gen_dir = IMAGES_DIR / generation_id

        # 5) Write ALL files FIRST (Property 12). On any failure, clean up and
        #    raise WITHOUT persisting a metadata row.
        relative_paths: list[str] = []
        try:
            gen_dir.mkdir(parents=True, exist_ok=True)
            for index, item in enumerate(data_items):
                b64 = item.get("b64_json")
                if not b64:
                    raise ValueError(f"missing b64_json for image index {index}")
                try:
                    raw = base64.b64decode(b64)
                except (binascii.Error, ValueError) as exc:
                    raise ValueError(f"invalid base64 image data at index {index}") from exc
                file_path = gen_dir / f"{index}.{ext}"
                file_path.write_bytes(raw)
                # image_paths stores paths relative to the images root.
                relative_paths.append(f"{generation_id}/{index}.{ext}")
        except Exception as exc:
            # Clean up any partially-written files; do NOT persist metadata.
            shutil.rmtree(gen_dir, ignore_errors=True)
            logger.error("Image file write failed for generation %s: %s", generation_id, exc)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to persist generated image files: {exc}",
            ) from exc

        # 6) Files are safely on disk -> persist the metadata row.
        created_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        params_json = json.dumps(params.model_dump())
        image_paths_json = json.dumps(relative_paths)
        try:
            await db.execute(
                """
                INSERT INTO image_generations (
                    id, instance_id, session_id, prompt, params, size, quality,
                    output_format, compression, n, has_reference,
                    input_tokens, output_tokens, image_paths, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    generation_id,
                    request.instance_id,
                    None,
                    request.prompt,
                    params_json,
                    params.size,
                    params.quality,
                    params.output_format,
                    params.compression,
                    params.n,
                    1 if has_reference else 0,
                    input_tokens,
                    output_tokens,
                    image_paths_json,
                    "completed",
                    created_at,
                ),
            )
            await db.commit()
        except Exception as exc:
            # If metadata persistence fails, remove the orphaned files so we do
            # not leave files without a referencing row.
            shutil.rmtree(gen_dir, ignore_errors=True)
            logger.error(
                "Image metadata insert failed for generation %s: %s",
                generation_id,
                exc,
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to persist image generation metadata",
            ) from exc

        # 7) Build the response with accessible URLs (one per saved file).
        image_urls = [
            f"/api/images/{generation_id}/{index}" for index in range(len(relative_paths))
        ]
        return ImageGenerationResponse(
            generation_id=generation_id,
            instance_id=request.instance_id,
            prompt=request.prompt,
            params=params,
            images=image_urls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            has_reference=has_reference,
            created_at=created_at,
        )

    # ------------------------------------------------------------------
    # Path resolution (path-traversal guard, Property 18 / Requirement 9.5)
    # ------------------------------------------------------------------
    def resolve_image_path(self, generation_id: str, index: int) -> tuple[Path, str] | None:
        """Resolve the on-disk path for an image and validate it stays in root.

        Returns ``(path, media_type)`` when the resolved absolute path is inside
        the images root directory AND the file exists; returns ``None`` when the
        path escapes the root (path traversal) or the file is missing.
        """
        root = IMAGES_DIR.resolve()
        candidate_dir = (IMAGES_DIR / generation_id).resolve()

        # Reject any generation_id that escapes the images root (e.g. "../..").
        if not self._is_within(root, candidate_dir):
            logger.warning("Rejected image path outside root for generation_id=%r", generation_id)
            return None

        # index must be a non-negative integer; reject anything else defensively.
        try:
            idx = int(index)
        except (TypeError, ValueError):
            return None
        if idx < 0:
            return None

        # Find the file named "<index>.<ext>" (extension unknown at this layer).
        matches = sorted(candidate_dir.glob(f"{idx}.*"))
        for match in matches:
            resolved = match.resolve()
            if not self._is_within(root, resolved):
                return None
            if resolved.is_file():
                return resolved, self._media_type_for(resolved.suffix.lstrip("."))
        return None

    @staticmethod
    def _is_within(root: Path, target: Path) -> bool:
        """Return True if ``target`` is the same as or inside ``root``."""
        try:
            target.relative_to(root)
            return True
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # History reads (used by task 5.3 / 7.2)
    # ------------------------------------------------------------------
    async def list_generations(
        self,
        db: aiosqlite.Connection,
        instance_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[dict]:
        """List image generation metadata rows, most recent first, paginated."""
        page = max(1, int(page))
        page_size = max(1, int(page_size))
        offset = (page - 1) * page_size

        query = "SELECT * FROM image_generations"
        params: tuple = ()
        if instance_id is not None:
            query += " WHERE instance_id = ?"
            params = (instance_id,)
        query += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
        params = params + (page_size, offset)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def get_generation(self, db: aiosqlite.Connection, generation_id: str) -> dict | None:
        """Return a single image generation metadata row as a dict, or None."""
        cursor = await db.execute("SELECT * FROM image_generations WHERE id = ?", (generation_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    @staticmethod
    def _row_to_dict(row: aiosqlite.Row) -> dict:
        """Convert an ``image_generations`` row into a dict with parsed JSON."""
        data = dict(row)
        # Parse JSON-encoded columns into structured values.
        try:
            data["params"] = json.loads(data.get("params") or "{}")
        except (json.JSONDecodeError, TypeError):
            data["params"] = {}
        try:
            data["image_paths"] = json.loads(data.get("image_paths") or "[]")
        except (json.JSONDecodeError, TypeError):
            data["image_paths"] = []
        data["has_reference"] = bool(data.get("has_reference"))
        # Provide accessible URLs alongside the stored relative paths.
        data["images"] = [
            f"/api/images/{data['id']}/{index}" for index in range(len(data["image_paths"]))
        ]
        return data

    # ------------------------------------------------------------------
    # Deletion (Requirement 5.4: delete files first, then DB row)
    # ------------------------------------------------------------------
    async def delete_generation(self, db: aiosqlite.Connection, generation_id: str) -> None:
        """Delete on-disk files/directory first, then remove the DB metadata row.

        Raises HTTPException 404 when the generation does not exist.
        """
        cursor = await db.execute("SELECT id FROM image_generations WHERE id = ?", (generation_id,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Image generation not found")

        # 1) Remove the on-disk directory (files) first (Requirement 5.4). Guard
        #    against path traversal by ensuring the directory is within the root.
        root = IMAGES_DIR.resolve()
        gen_dir = (IMAGES_DIR / generation_id).resolve()
        if self._is_within(root, gen_dir) and gen_dir != root:
            shutil.rmtree(gen_dir, ignore_errors=True)

        # 2) Then delete the metadata row.
        await db.execute("DELETE FROM image_generations WHERE id = ?", (generation_id,))
        await db.commit()
