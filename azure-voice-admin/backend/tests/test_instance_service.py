"""Unit tests for InstanceService."""

import os
import tempfile
from pathlib import Path

import aiosqlite
import pytest
from fastapi import HTTPException

# Set temp DB path before imports
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")

import app.database as db_mod  # noqa: E402
from app.database import init_db  # noqa: E402
from app.models.instance import InstanceCreate, InstanceUpdate  # noqa: E402
from app.services.instance_service import InstanceService  # noqa: E402


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    """Use a fresh temp database for each test."""
    test_db = str(tmp_path / "test.db")
    db_mod.DB_PATH = test_db
    await init_db()
    yield
    if Path(test_db).exists():
        Path(test_db).unlink()


@pytest.fixture
async def db(tmp_path):
    """Provide a database connection for tests."""
    async with aiosqlite.connect(db_mod.DB_PATH) as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn


@pytest.fixture
def service():
    """Provide an InstanceService instance."""
    return InstanceService()


class TestMaskApiKey:
    """Tests for InstanceService.mask_api_key static method."""

    def test_key_with_length_ge_4(self):
        """Keys >= 4 chars preserve last 4 and mask the rest."""
        result = InstanceService.mask_api_key("abcdefgh")
        assert result == "****efgh"
        assert len(result) == 8

    def test_key_exactly_4_chars(self):
        """Keys of exactly 4 chars return all 4 (no masking prefix)."""
        result = InstanceService.mask_api_key("abcd")
        assert result == "abcd"

    def test_key_less_than_4_chars(self):
        """Keys < 4 chars return '****'."""
        assert InstanceService.mask_api_key("abc") == "****"
        assert InstanceService.mask_api_key("a") == "****"
        assert InstanceService.mask_api_key("") == "****"

    def test_key_with_5_chars(self):
        """5-char key masks first char."""
        result = InstanceService.mask_api_key("12345")
        assert result == "*2345"

    def test_preserves_length_for_long_keys(self):
        """Masked result has same length as original for keys >= 4."""
        key = "sk-abc123def456ghi789"
        result = InstanceService.mask_api_key(key)
        assert len(result) == len(key)
        assert result[-4:] == key[-4:]
        assert all(c == "*" for c in result[:-4])


class TestCreateInstance:
    """Tests for InstanceService.create_instance."""

    async def test_create_valid_instance(self, db, service):
        """Successfully creates an instance with valid data."""
        data = InstanceCreate(
            name="test-instance",
            endpoint="https://test.openai.azure.com",
            api_key="sk-test-key-123",
            deployment="gpt-4o-realtime",
            type="voice",
        )
        result = await service.create_instance(db, data)
        assert result["name"] == "test-instance"
        assert result["endpoint"] == "https://test.openai.azure.com"
        assert result["deployment"] == "gpt-4o-realtime"
        assert "id" in result
        assert "created_at" in result

    async def test_create_with_description(self, db, service):
        """Creates an instance with optional description."""
        data = InstanceCreate(
            name="my-instance",
            endpoint="https://test.openai.azure.com",
            api_key="sk-key",
            deployment="gpt-4o",
            type="voice",
            description="Test description",
        )
        result = await service.create_instance(db, data)
        assert result["description"] == "Test description"

    async def test_reject_empty_endpoint(self, db, service):
        """Rejects instance creation with empty endpoint."""
        data = InstanceCreate(
            name="test", endpoint="", api_key="key", deployment="dep", type="voice"
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.create_instance(db, data)
        assert exc_info.value.status_code == 422

    async def test_reject_whitespace_endpoint(self, db, service):
        """Rejects instance creation with whitespace-only endpoint."""
        data = InstanceCreate(
            name="test", endpoint="   ", api_key="key", deployment="dep", type="voice"
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.create_instance(db, data)
        assert exc_info.value.status_code == 422

    async def test_reject_empty_api_key(self, db, service):
        """Rejects instance creation with empty API key."""
        data = InstanceCreate(
            name="test", endpoint="https://ep.com", api_key="", deployment="dep", type="voice"
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.create_instance(db, data)
        assert exc_info.value.status_code == 422

    async def test_reject_empty_name(self, db, service):
        """Rejects instance creation with empty name."""
        data = InstanceCreate(
            name="", endpoint="https://ep.com", api_key="key", deployment="dep", type="voice"
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.create_instance(db, data)
        assert exc_info.value.status_code == 422

    async def test_reject_duplicate_name(self, db, service):
        """Rejects creating an instance with a duplicate name."""
        data = InstanceCreate(
            name="unique-name",
            endpoint="https://ep.com",
            api_key="key",
            deployment="dep",
            type="voice",
        )
        await service.create_instance(db, data)

        # Try to create another with same name
        data2 = InstanceCreate(
            name="unique-name",
            endpoint="https://ep2.com",
            api_key="key2",
            deployment="dep2",
            type="voice",
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.create_instance(db, data2)
        assert exc_info.value.status_code == 409


class TestListInstances:
    """Tests for InstanceService.list_instances."""

    async def test_empty_list(self, db, service):
        """Returns empty list when no instances exist."""
        result = await service.list_instances(db)
        assert result == []

    async def test_lists_all_instances(self, db, service):
        """Returns all created instances."""
        for i in range(3):
            data = InstanceCreate(
                name=f"instance-{i}",
                endpoint=f"https://ep{i}.com",
                api_key=f"key-{i}",
                deployment=f"dep-{i}",
                type="voice",
            )
            await service.create_instance(db, data)

        result = await service.list_instances(db)
        assert len(result) == 3

    async def test_does_not_expose_api_key(self, db, service):
        """InstanceSummary does not include api_key field."""
        data = InstanceCreate(
            name="test",
            endpoint="https://ep.com",
            api_key="secret-key-12345",
            deployment="dep",
            type="voice",
        )
        await service.create_instance(db, data)

        result = await service.list_instances(db)
        summary = result[0]
        # InstanceSummary model doesn't have api_key field
        assert not hasattr(summary, "api_key")
        assert not hasattr(summary, "api_key_masked")


class TestGetInstance:
    """Tests for InstanceService.get_instance."""

    async def test_get_existing_instance(self, db, service):
        """Returns detail for an existing instance."""
        data = InstanceCreate(
            name="detail-test",
            endpoint="https://ep.com",
            api_key="sk-abcdef123456",
            deployment="gpt-4o",
            type="voice",
        )
        created = await service.create_instance(db, data)

        result = await service.get_instance(db, created["id"])
        assert result.name == "detail-test"
        # "sk-abcdef123456" is 15 chars → 11 stars + last 4
        assert result.api_key_masked == "***********3456"
        assert result.total_sessions == 0
        assert result.total_input_tokens == 0
        assert result.total_output_tokens == 0

    async def test_get_nonexistent_instance(self, db, service):
        """Raises 404 for non-existent instance."""
        with pytest.raises(HTTPException) as exc_info:
            await service.get_instance(db, "nonexistent-id")
        assert exc_info.value.status_code == 404

    async def test_includes_token_statistics(self, db, service):
        """Includes aggregated token stats from sessions."""
        data = InstanceCreate(
            name="stats-test",
            endpoint="https://ep.com",
            api_key="sk-key123",
            deployment="dep",
            type="voice",
        )
        created = await service.create_instance(db, data)

        # Insert some sessions with token data
        await db.execute(
            """
            INSERT INTO sessions (id, instance_id, room_name, status, start_time, input_tokens, output_tokens)
            VALUES (?, ?, ?, ?, datetime('now'), ?, ?)
            """,
            ("s1", created["id"], "room-1", "completed", 100, 200),
        )
        await db.execute(
            """
            INSERT INTO sessions (id, instance_id, room_name, status, start_time, input_tokens, output_tokens)
            VALUES (?, ?, ?, ?, datetime('now'), ?, ?)
            """,
            ("s2", created["id"], "room-2", "completed", 50, 75),
        )
        await db.commit()

        result = await service.get_instance(db, created["id"])
        assert result.total_sessions == 2
        assert result.total_input_tokens == 150
        assert result.total_output_tokens == 275


class TestUpdateInstance:
    """Tests for InstanceService.update_instance."""

    async def test_update_name(self, db, service):
        """Updates instance name."""
        data = InstanceCreate(
            name="old-name",
            endpoint="https://ep.com",
            api_key="key",
            deployment="dep",
            type="voice",
        )
        created = await service.create_instance(db, data)

        update = InstanceUpdate(name="new-name")
        result = await service.update_instance(db, created["id"], update)
        assert result["name"] == "new-name"

    async def test_update_nonexistent_raises_404(self, db, service):
        """Raises 404 when updating a non-existent instance."""
        update = InstanceUpdate(name="new")
        with pytest.raises(HTTPException) as exc_info:
            await service.update_instance(db, "nonexistent", update)
        assert exc_info.value.status_code == 404

    async def test_update_with_duplicate_name_raises_409(self, db, service):
        """Raises 409 when updating to a name that already exists."""
        data1 = InstanceCreate(
            name="name-a",
            endpoint="https://ep.com",
            api_key="key",
            deployment="dep",
            type="voice",
        )
        data2 = InstanceCreate(
            name="name-b",
            endpoint="https://ep2.com",
            api_key="key2",
            deployment="dep2",
            type="voice",
        )
        await service.create_instance(db, data1)
        created2 = await service.create_instance(db, data2)

        update = InstanceUpdate(name="name-a")
        with pytest.raises(HTTPException) as exc_info:
            await service.update_instance(db, created2["id"], update)
        assert exc_info.value.status_code == 409

    async def test_update_empty_fields(self, db, service):
        """No-op update returns current state without errors."""
        data = InstanceCreate(
            name="test",
            endpoint="https://ep.com",
            api_key="key",
            deployment="dep",
            type="voice",
        )
        created = await service.create_instance(db, data)

        update = InstanceUpdate()  # All None
        result = await service.update_instance(db, created["id"], update)
        assert result["name"] == "test"


class TestDeleteInstance:
    """Tests for InstanceService.delete_instance."""

    async def test_delete_existing_instance(self, db, service):
        """Successfully deletes an instance with no active sessions."""
        data = InstanceCreate(
            name="to-delete",
            endpoint="https://ep.com",
            api_key="key",
            deployment="dep",
            type="voice",
        )
        created = await service.create_instance(db, data)

        await service.delete_instance(db, created["id"])

        # Verify deleted
        cursor = await db.execute("SELECT id FROM instances WHERE id = ?", (created["id"],))
        assert await cursor.fetchone() is None

    async def test_delete_nonexistent_raises_404(self, db, service):
        """Raises 404 when deleting a non-existent instance."""
        with pytest.raises(HTTPException) as exc_info:
            await service.delete_instance(db, "nonexistent")
        assert exc_info.value.status_code == 404

    async def test_delete_with_active_session_raises_409(self, db, service):
        """Raises 409 when instance has active sessions."""
        data = InstanceCreate(
            name="active-instance",
            endpoint="https://ep.com",
            api_key="key",
            deployment="dep",
            type="voice",
        )
        created = await service.create_instance(db, data)

        # Insert an active session
        await db.execute(
            """
            INSERT INTO sessions (id, instance_id, room_name, status, start_time)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            ("s1", created["id"], "room-1", "connected"),
        )
        await db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await service.delete_instance(db, created["id"])
        assert exc_info.value.status_code == 409

    async def test_delete_with_completed_session_succeeds(self, db, service):
        """Allows deletion when all sessions are completed (not active)."""
        data = InstanceCreate(
            name="completed-instance",
            endpoint="https://ep.com",
            api_key="key",
            deployment="dep",
            type="voice",
        )
        created = await service.create_instance(db, data)

        # Insert a completed session
        await db.execute(
            """
            INSERT INTO sessions (id, instance_id, room_name, status, start_time)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            ("s1", created["id"], "room-1", "completed"),
        )
        await db.commit()

        # Should succeed - completed sessions don't block deletion
        await service.delete_instance(db, created["id"])
