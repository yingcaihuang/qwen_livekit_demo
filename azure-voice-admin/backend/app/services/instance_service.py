"""Service layer for Instance configuration management."""

import uuid
from datetime import UTC, datetime

import aiosqlite
from fastapi import HTTPException

from app.models.instance import (
    InstanceCreate,
    InstanceDetail,
    InstanceSummary,
    InstanceUpdate,
)


class InstanceService:
    """Business logic for managing Azure OpenAI Instance configurations."""

    @staticmethod
    def mask_api_key(api_key: str) -> str:
        """Mask an API key, preserving only the last 4 characters.

        If the key length is >= 4, replaces all but the last 4 characters with '*'.
        If the key length is < 4, returns '****'.
        """
        if len(api_key) >= 4:
            return "*" * (len(api_key) - 4) + api_key[-4:]
        return "****"

    async def create_instance(self, db: aiosqlite.Connection, data: InstanceCreate) -> dict:
        """Create a new Instance configuration.

        Validates:
        - endpoint and api_key are non-empty (not blank)
        - name is unique

        Returns the created instance as a dict.
        Raises HTTPException 422 for validation errors, 409 for name conflicts.
        """
        # Validate non-empty fields
        if not data.name or not data.name.strip():
            raise HTTPException(status_code=422, detail="Instance name cannot be empty")
        if not data.endpoint or not data.endpoint.strip():
            raise HTTPException(status_code=422, detail="Endpoint cannot be empty")
        if not data.api_key or not data.api_key.strip():
            raise HTTPException(status_code=422, detail="API key cannot be empty")
        if not data.deployment or not data.deployment.strip():
            raise HTTPException(status_code=422, detail="Deployment name cannot be empty")

        # Check name uniqueness
        cursor = await db.execute("SELECT id FROM instances WHERE name = ?", (data.name,))
        existing = await cursor.fetchone()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Instance with name '{data.name}' already exists",
            )

        # Generate ID and timestamps
        instance_id = uuid.uuid4().hex
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        await db.execute(
            """
            INSERT INTO instances (id, name, endpoint, api_key, deployment, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                instance_id,
                data.name,
                data.endpoint,
                data.api_key,
                data.deployment,
                data.description,
                now,
                now,
            ),
        )
        await db.commit()

        return {
            "id": instance_id,
            "name": data.name,
            "endpoint": data.endpoint,
            "deployment": data.deployment,
            "description": data.description,
            "created_at": now,
            "updated_at": now,
        }

    async def list_instances(self, db: aiosqlite.Connection) -> list[InstanceSummary]:
        """List all instances without exposing API keys."""
        cursor = await db.execute(
            "SELECT id, name, endpoint, deployment, description, created_at FROM instances ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [
            InstanceSummary(
                id=row[0],
                name=row[1],
                endpoint=row[2],
                deployment=row[3],
                description=row[4] or "",
                created_at=row[5],
            )
            for row in rows
        ]

    async def get_instance(self, db: aiosqlite.Connection, instance_id: str) -> InstanceDetail:
        """Get instance detail including masked API key and token usage statistics.

        Raises HTTPException 404 if not found.
        """
        cursor = await db.execute(
            "SELECT id, name, endpoint, api_key, deployment, description, created_at, updated_at FROM instances WHERE id = ?",
            (instance_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Instance not found")

        # Compute token statistics from sessions
        stats_cursor = await db.execute(
            """
            SELECT
                COUNT(*) as total_sessions,
                COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                COALESCE(SUM(output_tokens), 0) as total_output_tokens
            FROM sessions
            WHERE instance_id = ?
            """,
            (instance_id,),
        )
        stats_row = await stats_cursor.fetchone()

        return InstanceDetail(
            id=row[0],
            name=row[1],
            endpoint=row[2],
            api_key_masked=self.mask_api_key(row[3]),
            deployment=row[4],
            description=row[5] or "",
            created_at=row[6],
            updated_at=row[7],
            total_sessions=stats_row[0],
            total_input_tokens=stats_row[1],
            total_output_tokens=stats_row[2],
        )

    async def update_instance(
        self, db: aiosqlite.Connection, instance_id: str, data: InstanceUpdate
    ) -> dict:
        """Partially update an instance configuration.

        Only non-None fields in data are updated.
        Raises HTTPException 404 if not found, 422 for validation errors, 409 for name conflicts.
        """
        # Check instance exists
        cursor = await db.execute("SELECT id FROM instances WHERE id = ?", (instance_id,))
        existing = await cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Instance not found")

        # Build update fields
        updates: dict[str, str] = {}
        if data.name is not None:
            if not data.name.strip():
                raise HTTPException(status_code=422, detail="Instance name cannot be empty")
            # Check name uniqueness (exclude current instance)
            cursor = await db.execute(
                "SELECT id FROM instances WHERE name = ? AND id != ?",
                (data.name, instance_id),
            )
            if await cursor.fetchone():
                raise HTTPException(
                    status_code=409,
                    detail=f"Instance with name '{data.name}' already exists",
                )
            updates["name"] = data.name

        if data.endpoint is not None:
            if not data.endpoint.strip():
                raise HTTPException(status_code=422, detail="Endpoint cannot be empty")
            updates["endpoint"] = data.endpoint

        if data.api_key is not None:
            if not data.api_key.strip():
                raise HTTPException(status_code=422, detail="API key cannot be empty")
            updates["api_key"] = data.api_key

        if data.deployment is not None:
            if not data.deployment.strip():
                raise HTTPException(status_code=422, detail="Deployment name cannot be empty")
            updates["deployment"] = data.deployment

        if data.description is not None:
            updates["description"] = data.description

        if not updates:
            # Nothing to update, return current state
            cursor = await db.execute(
                "SELECT id, name, endpoint, deployment, description, created_at, updated_at FROM instances WHERE id = ?",
                (instance_id,),
            )
            row = await cursor.fetchone()
            return {
                "id": row[0],
                "name": row[1],
                "endpoint": row[2],
                "deployment": row[3],
                "description": row[4] or "",
                "created_at": row[5],
                "updated_at": row[6],
            }

        # Add updated_at timestamp
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        updates["updated_at"] = now

        # Build and execute UPDATE query
        set_clause = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [instance_id]

        await db.execute(
            f"UPDATE instances SET {set_clause} WHERE id = ?",
            values,
        )
        await db.commit()

        # Return updated instance
        cursor = await db.execute(
            "SELECT id, name, endpoint, deployment, description, created_at, updated_at FROM instances WHERE id = ?",
            (instance_id,),
        )
        row = await cursor.fetchone()
        return {
            "id": row[0],
            "name": row[1],
            "endpoint": row[2],
            "deployment": row[3],
            "description": row[4] or "",
            "created_at": row[5],
            "updated_at": row[6],
        }

    async def delete_instance(self, db: aiosqlite.Connection, instance_id: str) -> None:
        """Delete an instance configuration.

        Refuses deletion if the instance has active sessions (status IN ('connecting', 'connected')).
        Raises HTTPException 404 if not found, 409 if active sessions exist.
        """
        # Check instance exists
        cursor = await db.execute("SELECT id FROM instances WHERE id = ?", (instance_id,))
        existing = await cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Instance not found")

        # Check for active sessions
        cursor = await db.execute(
            "SELECT COUNT(*) FROM sessions WHERE instance_id = ? AND status IN ('connecting', 'connected')",
            (instance_id,),
        )
        active_count = (await cursor.fetchone())[0]
        if active_count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete instance: {active_count} active session(s) exist",
            )

        # Delete associated non-active sessions and their logs first (FK constraint)
        await db.execute(
            "DELETE FROM session_logs WHERE session_id IN (SELECT id FROM sessions WHERE instance_id = ?)",
            (instance_id,),
        )
        await db.execute("DELETE FROM sessions WHERE instance_id = ?", (instance_id,))
        await db.execute("DELETE FROM instances WHERE id = ?", (instance_id,))
        await db.commit()
