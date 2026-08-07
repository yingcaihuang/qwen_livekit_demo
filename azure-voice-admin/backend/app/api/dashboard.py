"""REST API routes for dashboard statistics."""

from fastapi import APIRouter, Depends

import aiosqlite

from app.database import get_db
from app.models.dashboard import DashboardStats, InstanceUsage

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: aiosqlite.Connection = Depends(get_db)):
    """Return overall system statistics.

    - total_instances: count of all instances
    - total_sessions: count of all sessions
    - active_sessions: count of sessions with status IN ('connecting', 'connected')
    - total_input_tokens: sum of input_tokens across all sessions
    - total_output_tokens: sum of output_tokens across all sessions
    """
    cursor = await db.execute("SELECT COUNT(*) FROM instances")
    row = await cursor.fetchone()
    total_instances = row[0]

    cursor = await db.execute("SELECT COUNT(*) FROM sessions")
    row = await cursor.fetchone()
    total_sessions = row[0]

    cursor = await db.execute(
        "SELECT COUNT(*) FROM sessions WHERE status IN ('connecting', 'connected')"
    )
    row = await cursor.fetchone()
    active_sessions = row[0]

    cursor = await db.execute(
        "SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0) FROM sessions"
    )
    row = await cursor.fetchone()
    total_input_tokens = row[0]
    total_output_tokens = row[1]

    return DashboardStats(
        total_instances=total_instances,
        total_sessions=total_sessions,
        active_sessions=active_sessions,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
    )


@router.get("/usage-by-instance", response_model=list[InstanceUsage])
async def get_usage_by_instance(db: aiosqlite.Connection = Depends(get_db)):
    """Return per-instance aggregation of session count and token usage."""
    cursor = await db.execute(
        """
        SELECT
            i.id AS instance_id,
            i.name AS instance_name,
            COUNT(s.id) AS session_count,
            COALESCE(SUM(s.input_tokens), 0) AS total_input_tokens,
            COALESCE(SUM(s.output_tokens), 0) AS total_output_tokens
        FROM instances i
        LEFT JOIN sessions s ON s.instance_id = i.id
        GROUP BY i.id, i.name
        ORDER BY i.name
        """
    )
    rows = await cursor.fetchall()
    return [
        InstanceUsage(
            instance_id=row[0],
            instance_name=row[1],
            session_count=row[2],
            total_input_tokens=row[3],
            total_output_tokens=row[4],
        )
        for row in rows
    ]
