"""Property-based tests for the Image service layer (Task 5.4).

Covers the following correctness properties from the design doc
(``.kiro/specs/azure-openai-testing-platform/design.md``):

- Property 7:  compression 参数区间约束
    Validates: Requirements 4.7
- Property 11: 请求的变体数量与返回图片数量一致
    Validates: Requirements 4.6, 5.1
- Property 12: 图像元数据完整性与无悬空引用
    Validates: Requirements 5.2, 5.5
- Property 13: 图像删除清理数据库与文件
    Validates: Requirements 5.4
- Property 18: 图片文件服务的路径穿越防护
    Validates: Requirements 9.5

Azure is never contacted: ``aiohttp.ClientSession`` (as seen from the service
module) is patched with a fake that returns a preset JSON payload containing
base64 image data (mirrors the fake-aiohttp pattern in ``test_images_api.py``).
A real temp SQLite DB (``init_db``) is used, and the images root
(``app.services.image_service.IMAGES_DIR``) is monkeypatched to a temp dir.

Tests that touch file IO / mocked network use a smaller ``max_examples`` (30-50)
but remain property-style with randomized inputs; pure functions run >=100.
"""

import base64
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import aiosqlite
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Set a temp DB path before importing the database module (matches existing
# test conventions in test_images_api.py / test_instance_type.py).
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")

import app.database as db_mod  # noqa: E402
import app.services.image_service as image_svc  # noqa: E402
from app.database import init_db  # noqa: E402
from app.models.image import (  # noqa: E402
    ImageGenerationRequest,
    ImageParams,
)
from app.services.image_service import ImageService  # noqa: E402

# A tiny opaque payload standing in for image bytes (content is irrelevant).
_FAKE_IMAGE_BYTES = b"\x89PNG\r\n\x1a\nFAKE-IMAGE-DATA"
_FAKE_IMAGE_B64 = base64.b64encode(_FAKE_IMAGE_BYTES).decode()

# A base64 string that ALWAYS fails to decode: its length mod 4 == 1, which
# base64.b64decode rejects with binascii.Error regardless of content. Used to
# simulate a write failure (invalid image data) for Property 12.
_INVALID_B64 = "ABCDE"


# Shared PBT settings for file-IO / mocked-network tests: property-style random
# inputs at a modest example count (file writes + DB commits per example), no
# deadline, and reuse of the function-scoped DB fixture across examples.
_io_settings = settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------
@pytest.fixture(autouse=True)
async def setup_db(tmp_path, monkeypatch):
    """Fresh temp DB (real schema) and temp images root for each test function."""
    test_db = str(tmp_path / "test.db")
    db_mod.DB_PATH = test_db

    # Point the images root at a temp directory (config computes it at import).
    images_dir = tmp_path / "images"
    monkeypatch.setattr(image_svc, "IMAGES_DIR", images_dir)

    await init_db()
    yield
    for suffix in ("", "-wal", "-shm"):
        p = Path(test_db + suffix)
        if p.exists():
            p.unlink()


@pytest.fixture
async def db():
    """Provide a database connection bound to the current test DB."""
    async with aiosqlite.connect(db_mod.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn


@pytest.fixture
def service():
    """Provide an ImageService instance."""
    return ImageService()


# ----------------------------------------------------------------------------
# Fake aiohttp plumbing (never hits real Azure)
# ----------------------------------------------------------------------------
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


def _azure_payload(n: int = 1, *, b64: str = _FAKE_IMAGE_B64) -> str:
    """Build a fake Azure Images JSON payload with ``n`` base64 images."""
    return json.dumps(
        {
            "data": [{"b64_json": b64} for _ in range(n)],
            "usage": {"input_tokens": 11, "output_tokens": 22},
        }
    )


def _patch_azure(monkeypatch, body: str, status: int = 200):
    """Patch the ClientSession referenced by the image service module."""
    monkeypatch.setattr(
        image_svc.aiohttp,
        "ClientSession",
        lambda *a, **k: _FakeSession(body, status=status),
    )


async def _insert_instance(db: aiosqlite.Connection) -> str:
    """Insert an image instance directly and return its id (unique per call)."""
    instance_id = uuid.uuid4().hex
    await db.execute(
        """
        INSERT INTO instances (id, name, endpoint, api_key, deployment, type)
        VALUES (?, ?, ?, ?, ?, 'image')
        """,
        (
            instance_id,
            f"img-{instance_id}",
            "https://test.openai.azure.com",
            "sk-test-key-12345",
            "gpt-image-1",
        ),
    )
    await db.commit()
    return instance_id


async def _reset(db: aiosqlite.Connection) -> None:
    """Clear DB rows and the images root so each Hypothesis example is isolated."""
    await db.execute("DELETE FROM image_generations")
    await db.execute("DELETE FROM instances")
    await db.commit()
    shutil.rmtree(image_svc.IMAGES_DIR, ignore_errors=True)


# ----------------------------------------------------------------------------
# Property 7: compression 参数区间约束 (Validates: Requirements 4.7)
# ----------------------------------------------------------------------------
class TestProperty7CompressionClamp:
    """Property 7: compression 参数区间约束 (Validates: Requirements 4.7)."""

    @settings(max_examples=300, deadline=None)
    @given(value=st.integers(min_value=-10_000, max_value=10_000))
    def test_property7_clamped_into_closed_range(self, value):
        """For any int, _clamp_compression stays within the closed [0, 100]."""
        clamped = ImageService._clamp_compression(value)
        assert 0 <= clamped <= 100

    @settings(max_examples=101, deadline=None)
    @given(value=st.integers(min_value=0, max_value=100))
    def test_property7_identity_within_range(self, value):
        """Values already in [0, 100] are returned unchanged (identity)."""
        assert ImageService._clamp_compression(value) == value

    @settings(max_examples=100, deadline=None)
    @given(value=st.integers())
    def test_property7_saturates_at_bounds(self, value):
        """Below 0 saturates to 0; above 100 saturates to 100."""
        clamped = ImageService._clamp_compression(value)
        if value < 0:
            assert clamped == 0
        elif value > 100:
            assert clamped == 100
        else:
            assert clamped == value


# ----------------------------------------------------------------------------
# Property 11: 请求变体数量 == 返回图片数量 (Validates: Requirements 4.6, 5.1)
# ----------------------------------------------------------------------------
class TestProperty11VariationCount:
    """Property 11: 请求的变体数量与返回图片数量一致 (Req 4.6, 5.1)."""

    @_io_settings
    @given(n=st.integers(min_value=1, max_value=6))
    async def test_property11_n_variations_yield_n_files_and_urls(
        self, db, service, monkeypatch, n
    ):
        """Requesting n variations writes exactly n files and returns n URLs."""
        await _reset(db)
        instance_id = await _insert_instance(db)
        # Azure returns exactly n base64 images for this generation.
        _patch_azure(monkeypatch, _azure_payload(n=n))

        request = ImageGenerationRequest(
            instance_id=instance_id,
            prompt="a red bicycle",
            params=ImageParams(n=n),
        )
        # Async model: enqueue returns a pending record, then a worker step
        # (process_job) performs the Azure call and writes the files.
        record = await service.enqueue_generation(db, request)
        await service.process_job(record["generation_id"])

        # Persisted image_paths contains exactly n entries, each on disk, and
        # the record exposes exactly one accessible URL per requested variation.
        row = await service.get_generation(db, record["generation_id"])
        assert row is not None
        assert row["status"] == "completed"
        assert len(row["images"]) == n
        assert len(row["image_paths"]) == n
        for rel in row["image_paths"]:
            assert (image_svc.IMAGES_DIR / rel).is_file()


# ----------------------------------------------------------------------------
# Property 12: 图像元数据完整性与无悬空引用 (Validates: Requirements 5.2, 5.5)
# ----------------------------------------------------------------------------
class TestProperty12MetadataIntegrity:
    """Property 12: 图像元数据完整性与无悬空引用 (Req 5.2, 5.5)."""

    @_io_settings
    @given(
        n=st.integers(min_value=1, max_value=4),
        prompt=st.text(
            alphabet=st.characters(min_codepoint=33, max_codepoint=126),
            min_size=1,
            max_size=40,
        ),
        compression=st.integers(min_value=0, max_value=100),
    )
    async def test_property12_success_persists_complete_non_dangling_metadata(
        self, db, service, monkeypatch, n, prompt, compression
    ):
        """On success: metadata row is complete and every path exists on disk."""
        await _reset(db)
        instance_id = await _insert_instance(db)
        _patch_azure(monkeypatch, _azure_payload(n=n))

        request = ImageGenerationRequest(
            instance_id=instance_id,
            prompt=prompt,
            params=ImageParams(n=n, compression=compression),
        )
        record = await service.enqueue_generation(db, request)
        await service.process_job(record["generation_id"])

        row = await service.get_generation(db, record["generation_id"])
        assert row is not None
        assert row["status"] == "completed"
        # Metadata completeness (Req 5.2): prompt, params, usage, instance_id.
        assert row["prompt"] == prompt
        assert row["instance_id"] == instance_id
        assert row["params"]  # non-empty parsed params dict
        assert row["input_tokens"] == 11
        assert row["output_tokens"] == 22
        # Non-empty image_paths with NO dangling references (Req 5.5).
        assert len(row["image_paths"]) == n
        for rel in row["image_paths"]:
            assert (image_svc.IMAGES_DIR / rel).is_file()

        # Performance timing is captured and persisted (numeric, non-negative,
        # with non-empty wall-clock start/end stamps).
        assert isinstance(row["duration_ms"], int) and row["duration_ms"] >= 0
        assert isinstance(row["ttfb_ms"], int) and row["ttfb_ms"] >= 0
        assert row["started_at"]
        assert row["ended_at"]

    @_io_settings
    @given(n=st.integers(min_value=1, max_value=4))
    async def test_property12_write_failure_marks_failed_no_dangling_refs(
        self, db, service, monkeypatch, n
    ):
        """On write failure: the row is marked 'failed' with NO dangling refs.

        In the async model the pending row always exists (enqueue persists it).
        When processing fails, the worker must capture the failure on the row
        (status='failed', error_message set) WITHOUT persisting any image_paths
        that would reference non-existent files (Req 5.5). The worker must never
        raise (it keeps serving subsequent jobs).
        """
        await _reset(db)
        instance_id = await _insert_instance(db)
        # Azure returns invalid base64 -> decoding fails during the file write.
        _patch_azure(monkeypatch, _azure_payload(n=n, b64=_INVALID_B64))

        request = ImageGenerationRequest(
            instance_id=instance_id,
            prompt="will fail",
            params=ImageParams(n=n),
        )
        record = await service.enqueue_generation(db, request)
        gen_id = record["generation_id"]
        # process_job must NOT raise even though decoding fails.
        await service.process_job(gen_id)

        row = await service.get_generation(db, gen_id)
        assert row is not None
        # The failure is captured on the row (Req 9.2-style surfacing).
        assert row["status"] == "failed"
        assert row["error_message"]
        # No dangling references: image_paths stays empty (no files were written).
        assert row["image_paths"] == []
        assert row["images"] == []


# ----------------------------------------------------------------------------
# Property 13: 图像删除清理数据库与文件 (Validates: Requirements 5.4)
# ----------------------------------------------------------------------------
class TestProperty13DeleteCleansUp:
    """Property 13: 图像删除清理数据库与文件 (Validates: Requirements 5.4)."""

    @_io_settings
    @given(n=st.integers(min_value=1, max_value=4))
    async def test_property13_delete_removes_row_and_directory(self, db, service, monkeypatch, n):
        """After generate, delete_generation removes both the DB row and files."""
        await _reset(db)
        instance_id = await _insert_instance(db)
        _patch_azure(monkeypatch, _azure_payload(n=n))

        request = ImageGenerationRequest(
            instance_id=instance_id,
            prompt="to be deleted",
            params=ImageParams(n=n),
        )
        record = await service.enqueue_generation(db, request)
        gen_id = record["generation_id"]
        await service.process_job(gen_id)
        gen_dir = image_svc.IMAGES_DIR / gen_id

        # Preconditions: row + on-disk directory both exist.
        assert gen_dir.is_dir()
        assert await service.get_generation(db, gen_id) is not None

        await service.delete_generation(db, gen_id)

        # The DB row is gone and the directory (and its files) removed.
        assert await service.get_generation(db, gen_id) is None
        assert not gen_dir.exists()


# ----------------------------------------------------------------------------
# Property 18: 图片文件服务路径穿越防护 (Validates: Requirements 9.5)
# ----------------------------------------------------------------------------
# Traversal-ish generation_id fragments combined into malicious identifiers.
_traversal_token = st.sampled_from(
    [
        "..",
        "../",
        "../..",
        "../../etc",
        "/etc/passwd",
        "/",
        "//",
        "\\",
        "..\\..\\windows",
        "%2e%2e",
        "....//",
        "/absolute/path",
        "a/../../b",
    ]
)


class TestProperty18PathTraversalGuard:
    """Property 18: 图片文件服务的路径穿越防护 (Validates: Requirements 9.5)."""

    @settings(
        max_examples=150,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        gen_id=st.lists(_traversal_token, min_size=1, max_size=4).map("".join),
        index=st.integers(min_value=-5, max_value=10),
    )
    def test_property18_traversal_ids_never_escape_root(self, service, gen_id, index):
        """A traversal-ish generation_id never resolves outside the images root.

        The resolver must either reject the input (return None) or return a path
        that is provably within the images root — never a path escaping it.
        """
        root = image_svc.IMAGES_DIR.resolve()
        result = service.resolve_image_path(gen_id, index)

        if result is None:
            return  # Rejected outright — the desired guard behaviour.

        resolved_path, _media_type = result
        # If (defensively) a path is returned, it MUST stay inside the root.
        assert resolved_path.resolve().is_relative_to(root)

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(gen_id=st.sampled_from(["..", "../..", "../../etc", "/etc"]))
    def test_property18_known_traversal_ids_are_rejected(self, service, gen_id):
        """Well-known traversal identifiers resolve to None (no file served)."""
        assert service.resolve_image_path(gen_id, 0) is None
