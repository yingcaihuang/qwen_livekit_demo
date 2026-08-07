"""Integration smoke tests for the Image REST API (/api/images).

Azure is never contacted: ``aiohttp.ClientSession`` is patched with a fake that
returns a preset JSON payload containing base64 image data. Image files are
written under a temp ``IMAGES_DIR`` (monkeypatched on the service module) so the
generation, file-serving (with path-traversal guard), history, detail, delete,
and instance-deletion cleanup paths can be verified end-to-end.
"""

import base64
import json
import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Set temp DB path before importing the app.
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")

import app.database as db_mod  # noqa: E402
import app.services.image_service as image_svc  # noqa: E402
from app.main import app  # noqa: E402

# A tiny valid-ish PNG-like payload (content is irrelevant; it is opaque bytes).
_FAKE_IMAGE_BYTES = b"\x89PNG\r\n\x1a\nFAKE-IMAGE-DATA"
_FAKE_IMAGE_B64 = base64.b64encode(_FAKE_IMAGE_BYTES).decode()


@pytest.fixture(autouse=True)
async def setup_db(tmp_path, monkeypatch):
    """Use a fresh temp database and a temp images directory for each test."""
    test_db = str(tmp_path / "test.db")
    db_mod.DB_PATH = test_db

    # Point the images root at a temp directory (config computes it at import).
    images_dir = tmp_path / "images"
    monkeypatch.setattr(image_svc, "IMAGES_DIR", images_dir)

    from app.database import init_db

    await init_db()
    yield
    if Path(test_db).exists():
        Path(test_db).unlink()


@pytest.fixture
async def client():
    """Provide an async HTTP client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def image_instance_id(client):
    """Create an image instance and return its ID."""
    resp = await client.post(
        "/api/instances",
        json={
            "name": "image-instance",
            "endpoint": "https://test.openai.azure.com",
            "api_key": "sk-test-key-12345",
            "deployment": "gpt-image-2",
            "type": "image",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class _FakeResponse:
    """Minimal async context manager mimicking an aiohttp response."""

    def __init__(self, status: int, body: str):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def text(self):
        return self._body


class _FakeSession:
    """Fake ``aiohttp.ClientSession`` returning a preset response."""

    def __init__(self, body: str, status: int = 200):
        self._body = body
        self._status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, *args, **kwargs):
        return _FakeResponse(self._status, self._body)


class _CapturingSession:
    """Fake ``aiohttp.ClientSession`` that records each POST's url/args.

    Used to assert *which* Azure endpoint (generations vs edits) was hit and
    whether the request used a JSON body or a multipart form (``data``).
    """

    def __init__(self, body: str, calls: list, status: int = 200):
        self._body = body
        self._status = status
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, *args, **kwargs):
        self._calls.append({"url": url, "json": kwargs.get("json"), "data": kwargs.get("data")})
        return _FakeResponse(self._status, self._body)


def _azure_payload(n: int = 1) -> str:
    """Build a fake Azure Images JSON payload with ``n`` base64 images."""
    return json.dumps(
        {
            "data": [{"b64_json": _FAKE_IMAGE_B64} for _ in range(n)],
            "usage": {"input_tokens": 11, "output_tokens": 22},
        }
    )


def _patch_azure(monkeypatch, body: str, status: int = 200):
    monkeypatch.setattr(
        image_svc.aiohttp,
        "ClientSession",
        lambda *a, **k: _FakeSession(body, status=status),
    )


async def _raw_get_status(raw_path: str) -> int:
    """Drive the ASGI app with a non-normalized GET path; return the status.

    ``httpx``/clients normalize ``..`` segments out of URLs before sending, which
    would prevent a traversal path from ever reaching the route. Calling the ASGI
    app directly preserves the raw path so the route's traversal guard is
    exercised at the HTTP layer.
    """
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": raw_path,
        "raw_path": raw_path.encode(),
        "query_string": b"",
        "headers": [],
        "scheme": "http",
        "server": ("test", 80),
        "client": ("test", 12345),
    }
    messages: list = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    return next(m["status"] for m in messages if m["type"] == "http.response.start")


def _patch_azure_capturing(monkeypatch, body: str, status: int = 200) -> list:
    """Patch ``ClientSession`` with a capturing fake; return the shared calls list."""
    calls: list = []
    monkeypatch.setattr(
        image_svc.aiohttp,
        "ClientSession",
        lambda *a, **k: _CapturingSession(body, calls, status=status),
    )
    return calls


class TestImageGeneration:
    """Tests for POST /api/images/generations and file serving."""

    async def test_generate_persists_and_serves_files(self, client, image_instance_id, monkeypatch):
        """A generation writes files, persists metadata, and serves the image."""
        _patch_azure(monkeypatch, _azure_payload(n=2))

        resp = await client.post(
            "/api/images/generations",
            data={
                "instance_id": image_instance_id,
                "prompt": "a red bicycle",
                "size": "1024x1024",
                "quality": "high",
                "output_format": "png",
                "compression": 100,
                "n": 2,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["instance_id"] == image_instance_id
        assert body["prompt"] == "a red bicycle"
        # Property 11: n variations -> n saved files / URLs.
        assert len(body["images"]) == 2
        assert body["input_tokens"] == 11
        assert body["output_tokens"] == 22
        gen_id = body["generation_id"]

        # The served file matches the bytes we "generated".
        file_resp = await client.get(f"/api/images/{gen_id}/0")
        assert file_resp.status_code == 200
        assert file_resp.headers["content-type"].startswith("image/png")
        assert file_resp.content == _FAKE_IMAGE_BYTES

    async def test_compression_is_clamped(self, client, image_instance_id, monkeypatch):
        """Out-of-range compression is clamped to [0, 100] (Req 4.7)."""
        _patch_azure(monkeypatch, _azure_payload())

        resp = await client.post(
            "/api/images/generations",
            data={
                "instance_id": image_instance_id,
                "prompt": "clamp me",
                "compression": 500,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["params"]["compression"] == 100

    async def test_file_route_rejects_missing(self, client, image_instance_id, monkeypatch):
        """A non-existent image returns 404, not a crash."""
        resp = await client.get("/api/images/does-not-exist/0")
        assert resp.status_code == 404

    async def test_path_traversal_guard(self):
        """A traversal generation_id resolves to None (Req 9.5 / Property 18).

        The file route serves via ``resolve_image_path``; a generation_id that
        escapes the images root must resolve to None so no file outside the root
        is served (the route surfaces that as 404).
        """
        service = image_svc.ImageService()
        assert service.resolve_image_path("../../etc", 0) is None
        assert service.resolve_image_path("..", 0) is None

    async def test_file_route_rejects_traversal(self, image_instance_id):
        """An API-level traversal generation_id is refused with 404 (Req 9.5).

        The file route resolves via ``resolve_image_path`` which returns None
        for a generation_id escaping the images root, so no file outside the
        root is served (surfaced as 404, never 200). The request is issued
        against the ASGI app with a raw path so URL normalization does not
        rewrite the traversal segment before it reaches the route.
        """
        status = await _raw_get_status("/api/images/../0")
        assert status == 404

    async def test_reference_image_triggers_edits_branch(
        self, client, image_instance_id, monkeypatch
    ):
        """Attaching a reference file takes the Azure *edits* path (Req 4.3).

        Asserts via the capturing mock that the ``images/edits`` URL was called
        with a multipart form (not a JSON body), and that the response marks the
        generation with ``has_reference == True``.
        """
        calls = _patch_azure_capturing(monkeypatch, _azure_payload())

        resp = await client.post(
            "/api/images/generations",
            data={
                "instance_id": image_instance_id,
                "prompt": "make it blue",
                "output_format": "png",
            },
            files={"file": ("reference.png", _FAKE_IMAGE_BYTES, "image/png")},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Req 4.3 / 5.2: edit path is recorded as a reference generation.
        assert body["has_reference"] is True

        # The Azure call went to the *edits* endpoint using multipart form-data.
        assert len(calls) == 1
        assert "/images/edits" in calls[0]["url"]
        assert calls[0]["data"] is not None  # multipart FormData
        assert calls[0]["json"] is None

        # Detail view also reflects the reference flag (persisted metadata).
        detail = await client.get(f"/api/images/{body['generation_id']}")
        assert detail.status_code == 200
        assert detail.json()["has_reference"] is True

    async def test_generations_branch_uses_json_body(self, client, image_instance_id, monkeypatch):
        """Without a reference file, the Azure *generations* JSON path is used.

        Complements the edits-branch test: confirms the no-reference request hits
        ``images/generations`` with a JSON body and ``has_reference == False``.
        """
        calls = _patch_azure_capturing(monkeypatch, _azure_payload())

        resp = await client.post(
            "/api/images/generations",
            data={"instance_id": image_instance_id, "prompt": "a plain prompt"},
        )
        assert resp.status_code == 200
        assert resp.json()["has_reference"] is False

        assert len(calls) == 1
        assert "/images/generations" in calls[0]["url"]
        assert calls[0]["json"] is not None
        assert calls[0]["data"] is None

    async def test_multiple_variations_return_n_urls(self, client, image_instance_id, monkeypatch):
        """n>1 yields exactly n served URLs and n files on disk (Req 4.6/5.1)."""
        _patch_azure(monkeypatch, _azure_payload(n=3))

        resp = await client.post(
            "/api/images/generations",
            data={"instance_id": image_instance_id, "prompt": "three variants", "n": 3},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["images"]) == 3
        gen_id = body["generation_id"]

        # Every advertised URL actually serves bytes (Req 5.1).
        for index in range(3):
            file_resp = await client.get(f"/api/images/{gen_id}/{index}")
            assert file_resp.status_code == 200
            assert file_resp.content == _FAKE_IMAGE_BYTES
        # A 4th index does not exist.
        assert (await client.get(f"/api/images/{gen_id}/3")).status_code == 404

    async def test_write_failure_persists_no_metadata(self, client, image_instance_id, monkeypatch):
        """If image bytes are unusable, the API errors and leaves no state (Req 5.5).

        Azure returns an empty ``b64_json`` so the file write step fails. The
        service must clean up the partial directory and NOT persist a metadata
        row (no dangling reference): the history list stays empty and no image
        directory remains on disk.
        """
        bad_payload = json.dumps(
            {
                "data": [{"b64_json": ""}],
                "usage": {"input_tokens": 5, "output_tokens": 0},
            }
        )
        _patch_azure(monkeypatch, bad_payload)

        resp = await client.post(
            "/api/images/generations",
            data={"instance_id": image_instance_id, "prompt": "will fail to write"},
        )
        assert resp.status_code == 500

        # No metadata row was persisted (Req 5.5: no reference to a missing file).
        list_resp = await client.get("/api/images")
        assert list_resp.status_code == 200
        assert list_resp.json() == []

        # No partial files/directories remain under the images root.
        if image_svc.IMAGES_DIR.exists():
            assert list(image_svc.IMAGES_DIR.iterdir()) == []


class TestImageHistory:
    """Tests for list/detail/delete history endpoints."""

    async def _generate(self, client, instance_id, monkeypatch, prompt="p"):
        _patch_azure(monkeypatch, _azure_payload())
        resp = await client.post(
            "/api/images/generations",
            data={"instance_id": instance_id, "prompt": prompt},
        )
        assert resp.status_code == 200
        return resp.json()["generation_id"]

    async def test_list_and_detail(self, client, image_instance_id, monkeypatch):
        """The list endpoint returns history and detail returns one record."""
        gen_id = await self._generate(client, image_instance_id, monkeypatch)

        list_resp = await client.get("/api/images")
        assert list_resp.status_code == 200
        items = list_resp.json()
        assert any(item["id"] == gen_id for item in items)

        detail_resp = await client.get(f"/api/images/{gen_id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["id"] == gen_id

        missing = await client.get("/api/images/nope")
        assert missing.status_code == 404

    async def test_delete_removes_files_and_row(self, client, image_instance_id, monkeypatch):
        """Deleting a generation removes the DB row and on-disk files (Req 5.4)."""
        gen_id = await self._generate(client, image_instance_id, monkeypatch)
        gen_dir = image_svc.IMAGES_DIR / gen_id
        assert gen_dir.exists()

        del_resp = await client.delete(f"/api/images/{gen_id}")
        assert del_resp.status_code == 204
        assert not gen_dir.exists()

        assert (await client.get(f"/api/images/{gen_id}")).status_code == 404

        del_again = await client.delete(f"/api/images/{gen_id}")
        assert del_again.status_code == 404

    async def test_instance_delete_cleans_up_images(self, client, image_instance_id, monkeypatch):
        """Deleting an instance removes its image files and metadata (Req 9.5/5.4)."""
        gen_id = await self._generate(client, image_instance_id, monkeypatch)
        gen_dir = image_svc.IMAGES_DIR / gen_id
        assert gen_dir.exists()

        del_resp = await client.delete(f"/api/instances/{image_instance_id}")
        assert del_resp.status_code == 204

        # Files gone and the generation row cascaded away.
        assert not gen_dir.exists()
        assert (await client.get(f"/api/images/{gen_id}")).status_code == 404
