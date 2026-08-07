"""Service layer for Image Generation (Azure OpenAI Images generations/edits).

Implements the image test path described in ``design.md`` (section "Image 服务层")
as an ASYNC queue/job model:

- :meth:`ImageService.enqueue_generation` runs in the request handler. It
  validates the instance, normalizes params, persists any reference image to
  disk, inserts a ``pending`` row, enqueues the job id, and returns immediately.
  It NEVER calls Azure.
- :meth:`ImageService.process_job` runs on a background worker (own DB
  connection). It calls Azure Images ``generations`` (no reference) or ``edits``
  (with a saved reference), decodes the returned base64 images, writes them to
  ``DATA_DIR/images/<generation_id>/<index>.<ext>`` and updates the row status to
  ``completed`` / ``failed``. It never re-raises: failures are captured on the
  row's ``error_message`` so the worker keeps serving subsequent jobs.

Key invariants (Correctness Properties):
- Property 7:  ``compression`` is clamped to ``[0, 100]``.
- Property 11: the number of requested variations equals the number of saved
  files / returned URLs.
- Property 12: on success the row is ``completed`` with one on-disk file per
  ``image_paths`` entry; on failure the row is ``failed`` with ``image_paths``
  left empty (no dangling references).
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
import time
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
    async def _read_reference_bytes(
        reference_image: ReferenceImage,
    ) -> tuple[bytes, str | None, str | None] | None:
        """Normalize a reference image to ``(data, content_type, filename)``.

        Enforces the configured maximum size (Requirement defensive guard).
        Returns ``None`` when no reference image was supplied. For raw ``bytes``
        input the content type / filename are unknown and returned as ``None``;
        for an ``UploadFile`` the client-supplied ``content_type``/``filename``
        are carried through so the edits path can send the correct multipart
        mimetype.
        """
        if reference_image is None:
            return None

        upload_content_type: str | None = None
        filename: str | None = None
        if isinstance(reference_image, bytes):
            data = reference_image
        elif isinstance(reference_image, UploadFile | StarletteUploadFile):
            # FastAPI may inject Starlette's UploadFile (which fastapi.UploadFile
            # subclasses), so accept both to keep the edits path working.
            data = await reference_image.read()
            upload_content_type = reference_image.content_type
            filename = reference_image.filename
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
        return data, upload_content_type, filename

    # Map an ``image/*`` mimetype to a reference filename extension.
    _IMAGE_EXTENSIONS: dict[str, str] = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
        "image/gif": "gif",
    }

    @classmethod
    def _detect_image_type(
        cls,
        data: bytes,
        upload_content_type: str | None,
        filename: str | None,
    ) -> tuple[str, str]:
        """Resolve ``(content_type, filename)`` for a reference image part.

        Azure validates the multipart ``image`` part's mimetype and rejects
        ``application/octet-stream``. We detect the real type robustly:

        1. Sniff the leading magic bytes (most reliable — ignores a wrong or
           missing client-supplied content type):
             - PNG  -> ("image/png", "reference.png")
             - JPEG -> ("image/jpeg", "reference.jpg")
             - WEBP -> ("image/webp", "reference.webp")
             - GIF  -> ("image/gif", "reference.gif")  (Azure edits doesn't
               support gif, but we detect it honestly; Azure returns a clear
               error if unsupported)
        2. Fallback: if ``upload_content_type`` is a non-empty ``image/*`` type,
           use it and derive the filename extension from it (or from the given
           ``filename``).
        3. Default: ("image/png", "reference.png").
        """
        # 1) Magic-byte sniffing (authoritative).
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png", "reference.png"
        if data[:3] == b"\xff\xd8\xff":
            return "image/jpeg", "reference.jpg"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp", "reference.webp"
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif", "reference.gif"

        # 2) Fallback to a valid client-supplied image/* content type.
        content_type = (upload_content_type or "").strip().lower()
        if content_type.startswith("image/"):
            ext = cls._IMAGE_EXTENSIONS.get(content_type)
            if ext is None and filename and "." in filename:
                ext = filename.rsplit(".", 1)[-1].lower()
            if ext is None:
                ext = content_type.split("/", 1)[-1] or "png"
            return content_type, f"reference.{ext}"

        # 3) Sensible default.
        return "image/png", "reference.png"

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
    ) -> tuple[dict, int, int]:
        """Call Azure Images ``generations`` with a JSON body (no reference image).

        Returns ``(data, ttfb_ms, total_ms)`` (see ``_post``).
        """
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
        reference_content_type: str | None = None,
        reference_filename: str | None = None,
    ) -> tuple[dict, int, int]:
        """Call Azure Images ``edits`` with multipart form-data (with reference image).

        The multipart ``image`` part is sent with the reference image's *real*
        mimetype (detected via :meth:`_detect_image_type`) and a matching
        filename. Azure validates this mimetype and rejects
        ``application/octet-stream``.

        Returns ``(data, ttfb_ms, total_ms)`` (see ``_post``).
        """
        url = self._azure_edits_url(endpoint)
        content_type, filename = self._detect_image_type(
            reference_bytes, reference_content_type, reference_filename
        )
        form = aiohttp.FormData()
        form.add_field("model", deployment)
        form.add_field(
            "image",
            reference_bytes,
            filename=filename,
            content_type=content_type,
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
    ) -> tuple[dict, int, int]:
        """Execute a POST to Azure and return ``(data, ttfb_ms, total_ms)``.

        Measures request timing with ``time.perf_counter()``:
          - ``ttfb_ms``: ms from just before sending the request to when the
            response headers / first byte are received (the ``async with
            session.post(...)`` context is entered).
          - ``total_ms``: ms from just before the request to after the response
            body has been fully read (``await resp.text()`` completes).

        Converts network errors and non-2xx responses into a readable
        HTTPException (Requirement 9.2). The ``api-key`` header is never logged
        (Requirement 9.3).
        """
        # Log the exact outgoing request URL so users can see the real path in
        # `docker compose logs backend` (never log the api-key or headers).
        logger.info("Azure image request -> POST %s", url)
        try:
            async with aiohttp.ClientSession() as session:
                t0 = time.perf_counter()
                async with session.post(url, headers=headers, json=json_body, data=data) as resp:
                    # Response headers / first byte received -> TTFB.
                    t_headers = time.perf_counter()
                    text = await resp.text()
                    # Body fully read -> total request time.
                    t1 = time.perf_counter()
                    ttfb_ms = round((t_headers - t0) * 1000)
                    total_ms = round((t1 - t0) * 1000)
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
                        return json.loads(text), ttfb_ms, total_ms
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
    # Generation (async queue/job model)
    # ------------------------------------------------------------------
    async def enqueue_generation(
        self,
        db: aiosqlite.Connection,
        request: ImageGenerationRequest,
        reference_image: ReferenceImage = None,
    ) -> dict:
        """Enqueue an image generation job and return the pending record.

        This runs entirely in the request handler and MUST NOT call Azure. It
        validates the instance, normalizes params, persists any reference image
        to disk (so the background worker can read it later), inserts a
        ``pending`` metadata row, enqueues the job id, and returns the record
        dict (same shape as the detail endpoint).
        """
        # 1) Validate the target instance exists (raises 404 if not).
        await self._load_instance(db, request.instance_id)

        # 2) Normalize / clamp parameters (Requirement 4.7 / Property 7).
        params = ImageParams(
            size=request.params.size,
            quality=request.params.quality,
            output_format=request.params.output_format,
            compression=self._clamp_compression(request.params.compression),
            n=max(1, int(request.params.n)),
        )

        generation_id = uuid.uuid4().hex

        # 3) If a reference image is provided, persist it to disk now so the
        #    worker (running on its own connection, after the request returns)
        #    can read it back. We detect the real image type from the bytes.
        has_reference = False
        reference = await self._read_reference_bytes(reference_image)
        if reference is not None:
            reference_bytes, upload_content_type, filename = reference
            _content_type, ref_filename = self._detect_image_type(
                reference_bytes, upload_content_type, filename
            )
            ext = ref_filename.rsplit(".", 1)[-1] if "." in ref_filename else "png"
            gen_dir = IMAGES_DIR / generation_id
            gen_dir.mkdir(parents=True, exist_ok=True)
            (gen_dir / f"_reference.{ext}").write_bytes(reference_bytes)
            has_reference = True

        # 4) Insert the pending row. Timing columns / error_message stay NULL.
        created_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        params_json = json.dumps(params.model_dump())
        await db.execute(
            """
            INSERT INTO image_generations (
                id, instance_id, session_id, prompt, params, size, quality,
                output_format, compression, n, has_reference,
                input_tokens, output_tokens, image_paths, status, error_message,
                created_at, started_at, ended_at, duration_ms, ttfb_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                0,
                0,
                "[]",
                "pending",
                None,
                created_at,
                None,
                None,
                None,
                None,
            ),
        )
        await db.commit()

        # 5) Enqueue the job for a background worker (lazy import avoids a
        #    circular import between this module and the queue module).
        from app.services.image_queue import enqueue_job

        enqueue_job(generation_id)

        # 6) Return the freshly-inserted pending record (detail-shaped dict).
        return await self.get_generation(db, generation_id)

    async def process_job(self, generation_id: str) -> None:
        """Process a queued generation job (called by background workers).

        Opens its OWN database connection (resolving ``app.database.DB_PATH`` at
        call time so test fixtures pointing at a temp DB are respected — mirrors
        ``app/api/chat.py``). Calls Azure, writes files, and updates the row to
        ``completed`` or ``failed``. NEVER re-raises: any failure is captured on
        the row so the worker keeps serving subsequent jobs.
        """
        import app.database as db_mod

        db = await aiosqlite.connect(db_mod.DB_PATH)
        db.row_factory = aiosqlite.Row
        try:
            await db.execute("PRAGMA foreign_keys = ON")

            # 1) Load the row; skip if missing or already in a terminal state.
            cursor = await db.execute(
                "SELECT * FROM image_generations WHERE id = ?", (generation_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return
            if row["status"] not in ("pending", "processing"):
                return

            instance_id = row["instance_id"]
            prompt = row["prompt"]
            has_reference = bool(row["has_reference"])
            try:
                params_dict = json.loads(row["params"] or "{}")
            except (json.JSONDecodeError, TypeError):
                params_dict = {}
            params = ImageParams(**params_dict)

            # 2) Mark processing + record the wall-clock start time.
            started_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            await db.execute(
                "UPDATE image_generations SET status = 'processing', started_at = ? WHERE id = ?",
                (started_at, generation_id),
            )
            await db.commit()

            gen_dir = IMAGES_DIR / generation_id

            try:
                # 3) Load instance credentials (mark failed if the instance is gone).
                endpoint, api_key, deployment = await self._load_instance(db, instance_id)

                # 4) Call Azure: edits when a reference image was saved, else generations.
                if has_reference:
                    reference_bytes = self._read_saved_reference(gen_dir)
                    if reference_bytes is None:
                        raise HTTPException(
                            status_code=500,
                            detail="Reference image file is missing for this generation",
                        )
                    payload, ttfb_ms, total_ms = await self._call_edits(
                        endpoint,
                        api_key,
                        deployment,
                        prompt,
                        params,
                        reference_bytes,
                    )
                else:
                    payload, ttfb_ms, total_ms = await self._call_generations(
                        endpoint, api_key, deployment, prompt, params
                    )

                # 5) Extract + decode image variations, then write files.
                data_items = payload.get("data") or []
                if not data_items:
                    raise HTTPException(
                        status_code=502,
                        detail="Azure image API returned no image data",
                    )

                usage = payload.get("usage") or {}
                input_tokens = int(usage.get("input_tokens", 0) or 0)
                output_tokens = int(usage.get("output_tokens", 0) or 0)

                ext = (params.output_format or "png").lower()
                gen_dir.mkdir(parents=True, exist_ok=True)
                relative_paths: list[str] = []
                for index, item in enumerate(data_items):
                    b64 = item.get("b64_json")
                    if not b64:
                        raise ValueError(f"missing b64_json for image index {index}")
                    try:
                        raw = base64.b64decode(b64)
                    except (binascii.Error, ValueError) as exc:
                        raise ValueError(f"invalid base64 image data at index {index}") from exc
                    (gen_dir / f"{index}.{ext}").write_bytes(raw)
                    relative_paths.append(f"{generation_id}/{index}.{ext}")

                ended_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                await db.execute(
                    """
                    UPDATE image_generations
                    SET status = 'completed', image_paths = ?, input_tokens = ?,
                        output_tokens = ?, ended_at = ?, duration_ms = ?, ttfb_ms = ?,
                        error_message = NULL
                    WHERE id = ?
                    """,
                    (
                        json.dumps(relative_paths),
                        input_tokens,
                        output_tokens,
                        ended_at,
                        total_ms,
                        ttfb_ms,
                        generation_id,
                    ),
                )
                await db.commit()
                self._cleanup_reference(gen_dir)
            except Exception as exc:
                # Capture the failure on the row; never re-raise / crash the worker.
                detail = getattr(exc, "detail", None)
                message = str(detail if detail is not None else exc)[:500]
                # api-key is never part of these messages; log without headers.
                logger.error("Image generation %s failed: %s", generation_id, message)
                ended_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                try:
                    await db.execute(
                        """
                        UPDATE image_generations
                        SET status = 'failed', error_message = ?, ended_at = ?
                        WHERE id = ?
                        """,
                        (message, ended_at, generation_id),
                    )
                    await db.commit()
                except Exception:  # pragma: no cover - defensive
                    logger.exception(
                        "Failed to persist failure status for generation %s", generation_id
                    )
                self._cleanup_reference(gen_dir)
        finally:
            await db.close()

    @staticmethod
    def _read_saved_reference(gen_dir: Path) -> bytes | None:
        """Read the saved ``_reference.*`` bytes from a generation dir, or None."""
        if not gen_dir.exists():
            return None
        matches = sorted(gen_dir.glob("_reference.*"))
        for match in matches:
            if match.is_file():
                return match.read_bytes()
        return None

    @staticmethod
    def _cleanup_reference(gen_dir: Path) -> None:
        """Best-effort delete of the saved ``_reference.*`` file(s)."""
        try:
            if not gen_dir.exists():
                return
            for match in gen_dir.glob("_reference.*"):
                match.unlink(missing_ok=True)
        except Exception:  # pragma: no cover - best effort
            logger.debug("Failed to clean up reference file under %s", gen_dir)

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
        # Expose both ``id`` and ``generation_id`` (equal) so the frontend can
        # use either interchangeably across enqueue/detail/list responses.
        data["generation_id"] = data["id"]
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
