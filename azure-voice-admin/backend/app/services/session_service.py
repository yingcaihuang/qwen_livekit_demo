"""Service layer for Voice Session lifecycle management."""

import logging
import os
import time
import uuid
from datetime import UTC, datetime

import aiosqlite
from fastapi import HTTPException
from livekit.api import AccessToken, VideoGrants

from app.models.session import (
    PaginatedSessions,
    SessionDetail,
    SessionResponse,
)


class SessionService:
    """Business logic for managing Voice Sessions."""

    @staticmethod
    def _generate_room_name() -> str:
        """Generate a unique room name based on current timestamp."""
        return f"room-{int(time.time() * 1000)}"

    @staticmethod
    def _generate_livekit_token(room_name: str, identity: str = "user") -> str:
        """Generate a LiveKit access token for the given room and identity.

        Reads LIVEKIT_API_KEY and LIVEKIT_API_SECRET from environment variables.
        """
        api_key = os.environ.get("LIVEKIT_API_KEY", "")
        api_secret = os.environ.get("LIVEKIT_API_SECRET", "")

        token = AccessToken(api_key, api_secret)
        token = token.with_identity(identity).with_grants(
            VideoGrants(
                room_join=True,
                room=room_name,
            )
        )
        return token.to_jwt()

    async def create_session(
        self, db: aiosqlite.Connection, instance_id: str, voice: str = "alloy"
    ) -> SessionResponse:
        """Create a new voice session.

        Validates that the instance exists, generates a unique room name and
        LiveKit token, creates the session record, and returns connection info.

        Raises HTTPException 404 if the instance does not exist.
        """
        # Verify instance exists
        cursor = await db.execute("SELECT id FROM instances WHERE id = ?", (instance_id,))
        instance = await cursor.fetchone()
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")

        # Generate room name and session ID
        session_id = uuid.uuid4().hex
        room_name = self._generate_room_name()
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        # Generate LiveKit token
        livekit_token = self._generate_livekit_token(room_name)
        # Use LIVEKIT_PUBLIC_URL for client-facing URL (e.g., wss://rtc.verycloud.cn)
        # Falls back to LIVEKIT_URL for local/dev environments
        livekit_url = os.environ.get(
            "LIVEKIT_PUBLIC_URL",
            os.environ.get("LIVEKIT_URL", "ws://localhost:7880"),
        )

        # Insert session record
        await db.execute(
            """
            INSERT INTO sessions (id, instance_id, room_name, status, start_time)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, instance_id, room_name, "connecting", now),
        )
        await db.commit()

        # Spawn Agent Worker
        try:
            import logging

            from app.services.process_manager import process_manager

            # Fetch instance credentials for the agent
            cred_cursor = await db.execute(
                "SELECT endpoint, api_key, deployment FROM instances WHERE id = ?",
                (instance_id,),
            )
            cred_row = await cred_cursor.fetchone()
            if cred_row:
                instance_config = {
                    "endpoint": cred_row[0],
                    "api_key": cred_row[1],
                    "deployment": cred_row[2],
                }
                await process_manager.spawn_agent(
                    session_id=session_id,
                    instance_config=instance_config,
                    room_name=room_name,
                    voice=voice,
                )

                # Start reading agent stdout for debug logging
                from app.services.log_broadcaster import get_log_broadcaster

                stdout_reader = process_manager.get_stdout_reader(session_id)
                if stdout_reader:
                    broadcaster = get_log_broadcaster()
                    await broadcaster.start_reading(session_id, stdout_reader)
        except Exception as e:
            logging.getLogger("session_service").error(
                f"Failed to spawn agent for session {session_id}: {e}"
            )

        return SessionResponse(
            session_id=session_id,
            room_name=room_name,
            livekit_token=livekit_token,
            livekit_url=livekit_url,
        )

    async def stop_session(self, db: aiosqlite.Connection, session_id: str) -> dict:
        """Stop an active session.

        Updates status to 'cancelled' and sets end_time.
        Terminates the Agent Worker process if running.
        Raises HTTPException 404 if the session does not exist.
        """
        # Check session exists
        cursor = await db.execute("SELECT id, status FROM sessions WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")

        # Terminate Agent Worker if ProcessManager is available
        try:
            from app.services.process_manager import process_manager

            await process_manager.terminate_agent(session_id)
        except (ImportError, Exception):
            # ProcessManager not yet implemented (task 3.4) — skip gracefully
            pass

        # Persist debug logs and conversation messages to database
        try:
            from app.services.log_broadcaster import get_log_broadcaster

            broadcaster = get_log_broadcaster()
            broadcaster.stop_reading(session_id)
            await broadcaster.persist_messages(session_id, db)
            await broadcaster.persist_logs(session_id, db)
        except Exception as e:
            logging.getLogger("session_service").error(
                f"Failed to persist logs for session {session_id}: {e}"
            )

        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            "UPDATE sessions SET status = ?, end_time = ? WHERE id = ?",
            ("cancelled", now, session_id),
        )
        await db.commit()

        return {"id": session_id, "status": "cancelled", "end_time": now}

    async def report_token_usage(
        self,
        db: aiosqlite.Connection,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> dict:
        """Report token usage for a session (cumulative add).

        Raises HTTPException 404 if the session does not exist.
        """
        # Check session exists
        cursor = await db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")

        # Cumulative add tokens
        await db.execute(
            """
            UPDATE sessions
            SET input_tokens = input_tokens + ?,
                output_tokens = output_tokens + ?
            WHERE id = ?
            """,
            (input_tokens, output_tokens, session_id),
        )
        await db.commit()

        return {"status": "ok", "session_id": session_id}

    async def list_sessions(
        self,
        db: aiosqlite.Connection,
        page: int = 1,
        page_size: int = 20,
        instance_id: str | None = None,
    ) -> PaginatedSessions:
        """List sessions with pagination and optional instance filter."""
        # Build WHERE clause
        conditions: list[str] = []
        params: list = []
        if instance_id:
            conditions.append("s.instance_id = ?")
            params.append(instance_id)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # Count total
        count_sql = f"SELECT COUNT(*) FROM sessions s {where_clause}"
        cursor = await db.execute(count_sql, params)
        total = (await cursor.fetchone())[0]

        # Fetch paginated results with instance name
        offset = (page - 1) * page_size
        query_sql = f"""
            SELECT s.id, s.instance_id, i.name as instance_name, s.room_name,
                   s.status, s.start_time, s.end_time, s.input_tokens,
                   s.output_tokens, s.error_message
            FROM sessions s
            JOIN instances i ON s.instance_id = i.id
            {where_clause}
            ORDER BY s.start_time DESC
            LIMIT ? OFFSET ?
        """
        query_params = params + [page_size, offset]
        cursor = await db.execute(query_sql, query_params)
        rows = await cursor.fetchall()

        items = [
            SessionDetail(
                id=row[0],
                instance_id=row[1],
                instance_name=row[2],
                room_name=row[3],
                status=row[4],
                start_time=row[5],
                end_time=row[6],
                input_tokens=row[7],
                output_tokens=row[8],
                error_message=row[9],
            )
            for row in rows
        ]

        return PaginatedSessions(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_session(self, db: aiosqlite.Connection, session_id: str) -> SessionDetail:
        """Get session detail by ID.

        Raises HTTPException 404 if not found.
        """
        cursor = await db.execute(
            """
            SELECT s.id, s.instance_id, i.name as instance_name, s.room_name,
                   s.status, s.start_time, s.end_time, s.input_tokens,
                   s.output_tokens, s.error_message
            FROM sessions s
            JOIN instances i ON s.instance_id = i.id
            WHERE s.id = ?
            """,
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")

        return SessionDetail(
            id=row[0],
            instance_id=row[1],
            instance_name=row[2],
            room_name=row[3],
            status=row[4],
            start_time=row[5],
            end_time=row[6],
            input_tokens=row[7],
            output_tokens=row[8],
            error_message=row[9],
        )

    async def delete_session(self, db: aiosqlite.Connection, session_id: str) -> None:
        """Delete a session record and its associated logs.

        Raises HTTPException 404 if the session does not exist.
        """
        # Check session exists
        cursor = await db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")

        # Delete associated logs and messages first, then the session. Both
        # child tables declare ON DELETE CASCADE, but we delete explicitly so
        # cleanup is robust even if foreign-key enforcement is not enabled on
        # the connection. This applies to both voice and chat sessions
        # (chat sessions store their transcript in session_messages).
        await db.execute("DELETE FROM session_logs WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM session_messages WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()
