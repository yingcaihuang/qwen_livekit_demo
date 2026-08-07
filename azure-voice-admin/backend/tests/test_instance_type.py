"""Property-based tests for instance type management (Task 3.4).

Covers the following correctness properties from the design doc:

- Property 1:  实例类型往返一致性
    Validates: Requirements 1.1
- Property 2:  非法或缺失类型被拒绝
    Validates: Requirements 1.2
- Property 3:  实例类型创建后不可变
    Validates: Requirements 1.7
- Property 4:  按类型筛选正确性
    Validates: Requirements 1.8, 6.3, 7.2
- Property 17: API Key 脱敏保留末尾字符
    Validates: Requirements 9.3

Each property runs at least 100 Hypothesis examples. Tests use a real SQLite
database created from the production schema (init_db against a temp DB_PATH),
following the conventions in test_instance_service.py / test_migration.py.
"""

import os
import tempfile
import uuid
from pathlib import Path

import aiosqlite
import pytest
from fastapi import HTTPException
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

# Set a temp DB path before importing the database module (matches existing
# test conventions in test_instance_service.py / test_migration.py).
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")

import app.database as db_mod  # noqa: E402
from app.database import init_db  # noqa: E402
from app.models.instance import InstanceCreate, InstanceUpdate  # noqa: E402
from app.services.instance_service import InstanceService  # noqa: E402

VALID_TYPES = ("voice", "chat", "image")

# Non-blank, NUL-free text usable for endpoint/api_key/deployment/description.
# Codepoints 33..126 exclude the space character (32), so values are never blank
# after .strip() and always pass the service's non-empty validation.
_safe_text = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=1,
    max_size=24,
)

_valid_type = st.sampled_from(VALID_TYPES)

# Common Hypothesis settings: >=100 examples, no deadline (DB IO varies), and
# allow reuse of the function-scoped DB fixture across examples.
_pbt_settings = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    """Use a fresh temp database (real schema) for each test function."""
    test_db = str(tmp_path / "test.db")
    db_mod.DB_PATH = test_db
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
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn


@pytest.fixture
def service():
    """Provide an InstanceService instance."""
    return InstanceService()


def _unique_name(prefix: str) -> str:
    """A globally-unique instance name (the DB persists across examples)."""
    return f"{prefix}-{uuid.uuid4().hex}"


class TestProperty1TypeRoundtrip:
    """Property 1: 实例类型往返一致性 (Validates: Requirements 1.1)."""

    @_pbt_settings
    @given(instance_type=_valid_type)
    async def test_property1_created_type_is_returned_unchanged(self, db, service, instance_type):
        """Creating an instance with a valid type returns the same type on read."""
        data = InstanceCreate(
            name=_unique_name("p1"),
            endpoint="https://ep.openai.azure.com",
            api_key="sk-roundtrip-key",
            deployment="deployment-x",
            type=instance_type,
        )

        created = await service.create_instance(db, data)
        assert created["type"] == instance_type

        detail = await service.get_instance(db, created["id"])
        assert detail.type == instance_type


class TestProperty2InvalidTypeRejected:
    """Property 2: 非法或缺失类型被拒绝 (Validates: Requirements 1.2)."""

    @_pbt_settings
    @given(bad_type=st.text(max_size=16).filter(lambda s: s not in VALID_TYPES))
    def test_property2_pydantic_rejects_invalid_type(self, bad_type):
        """InstanceCreate rejects any type outside {voice, chat, image}."""
        with pytest.raises(ValidationError):
            InstanceCreate(
                name="pydantic-check",
                endpoint="https://ep.openai.azure.com",
                api_key="sk-key",
                deployment="dep",
                type=bad_type,
            )

    def test_property2_pydantic_rejects_missing_type(self):
        """InstanceCreate requires the type field (missing type is rejected)."""
        with pytest.raises(ValidationError):
            InstanceCreate(
                name="missing-type",
                endpoint="https://ep.openai.azure.com",
                api_key="sk-key",
                deployment="dep",
            )

    @_pbt_settings
    @given(bad_type=st.text(max_size=16).filter(lambda s: s not in VALID_TYPES))
    async def test_property2_service_defensively_rejects_invalid_type(self, db, service, bad_type):
        """create_instance defensively rejects an invalid type with HTTP 422.

        The model is built with a valid type then mutated to bypass Pydantic's
        Literal validation (Pydantic does not re-validate on assignment by
        default), exercising the service-layer defensive check.
        """
        data = InstanceCreate(
            name=_unique_name("p2"),
            endpoint="https://ep.openai.azure.com",
            api_key="sk-key",
            deployment="dep",
            type="voice",
        )
        data.type = bad_type  # bypasses Literal validation

        with pytest.raises(HTTPException) as exc_info:
            await service.create_instance(db, data)
        assert exc_info.value.status_code == 422


class TestProperty3TypeImmutable:
    """Property 3: 实例类型创建后不可变 (Validates: Requirements 1.7)."""

    @_pbt_settings
    @given(
        instance_type=_valid_type,
        new_endpoint=_safe_text,
        new_api_key=_safe_text,
        new_deployment=_safe_text,
        new_description=st.text(max_size=40),
    )
    async def test_property3_type_unchanged_after_update(
        self,
        db,
        service,
        instance_type,
        new_endpoint,
        new_api_key,
        new_deployment,
        new_description,
    ):
        """Updating any allowed field never changes the instance type."""
        created = await service.create_instance(
            db,
            InstanceCreate(
                name=_unique_name("p3"),
                endpoint="https://ep.openai.azure.com",
                api_key="sk-original",
                deployment="dep-original",
                type=instance_type,
            ),
        )

        update = InstanceUpdate(
            name=_unique_name("p3-upd"),
            endpoint=new_endpoint,
            api_key=new_api_key,
            deployment=new_deployment,
            description=new_description,
        )
        # InstanceUpdate has no `type` field, so a type change cannot even be
        # requested; assert the persisted type is still the original.
        assert not hasattr(update, "type")

        updated = await service.update_instance(db, created["id"], update)
        assert updated["type"] == instance_type

        detail = await service.get_instance(db, created["id"])
        assert detail.type == instance_type


class TestProperty4FilterByType:
    """Property 4: 按类型筛选正确性 (Validates: Requirements 1.8, 6.3, 7.2)."""

    @_pbt_settings
    @given(types=st.lists(_valid_type, min_size=0, max_size=12))
    async def test_property4_list_filter_returns_exactly_matching_type(self, db, service, types):
        """list_instances(type_filter=T) returns exactly the instances of type T."""
        # The DB fixture persists across Hypothesis examples; isolate each
        # example by clearing the table first.
        await db.execute("DELETE FROM instances")
        await db.commit()

        expected: dict[str, set[str]] = {t: set() for t in VALID_TYPES}
        for i, t in enumerate(types):
            created = await service.create_instance(
                db,
                InstanceCreate(
                    name=_unique_name(f"p4-{i}"),
                    endpoint="https://ep.openai.azure.com",
                    api_key="sk-key",
                    deployment="dep",
                    type=t,
                ),
            )
            expected[t].add(created["id"])

        for t in VALID_TYPES:
            filtered = await service.list_instances(db, type_filter=t)
            # Every returned instance has the requested type.
            assert all(item.type == t for item in filtered)
            # The returned id set matches exactly what was created for type t.
            assert {item.id for item in filtered} == expected[t]

        # No filter returns everything created in this example.
        all_items = await service.list_instances(db)
        assert len(all_items) == len(types)


class TestProperty17MaskApiKey:
    """Property 17: API Key 脱敏保留末尾字符 (Validates: Requirements 9.3)."""

    @_pbt_settings
    @given(api_key=st.text(max_size=64))
    def test_property17_mask_preserves_only_last_four(self, api_key):
        """mask_api_key keeps only the last 4 chars ('****' for len < 4)."""
        masked = InstanceService.mask_api_key(api_key)

        if len(api_key) < 4:
            assert masked == "****"
        else:
            # Same length as the original.
            assert len(masked) == len(api_key)
            # Last 4 characters preserved exactly.
            assert masked[-4:] == api_key[-4:]
            # Everything before the last 4 is masked — the middle is never
            # exposed.
            assert masked[:-4] == "*" * (len(api_key) - 4)
