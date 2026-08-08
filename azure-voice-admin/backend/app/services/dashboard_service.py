"""Aggregation service for the unified dashboard.

Provides reusable, filterable aggregation helpers that compute usage across
BOTH the ``sessions`` table (``voice`` / ``chat`` tests, whose type is derived
from ``instances.type``) and the ``image_generations`` table (``image`` tests).

These functions are intentionally decoupled from the API layer so the dashboard
routes (task 8.2) can call them directly. Empty result sets yield zero values
rather than errors (Requirement 7.5).
"""

import aiosqlite

from app.models.dashboard import DashboardStats, InstanceUsage, TypeUsage
from app.models.instance import InstanceType

# Test types backed by the ``sessions`` table (type derived via instances.type).
_SESSION_TYPES = ("voice", "chat")
_ACTIVE_STATUSES = ("connecting", "connected")


async def compute_stats(
    db: aiosqlite.Connection,
    *,
    type_filter: InstanceType | None = None,
    instance_id: str | None = None,
    owner_id: str | None = None,
) -> DashboardStats:
    """Compute overall totals across sessions and image generations.

    Args:
        db: Open database connection.
        type_filter: When set, restrict aggregation to a single test type.
        instance_id: When set, restrict aggregation to a single instance.
        owner_id: When set, restrict aggregation to resources owned by this user.

    Returns:
        DashboardStats with combined counts and token totals. An empty match
        set yields zero values.
    """
    # ---- instance count (respects type/instance/owner filters) ----
    inst_conditions: list[str] = []
    inst_params: list = []
    if type_filter is not None:
        inst_conditions.append("type = ?")
        inst_params.append(type_filter)
    if instance_id is not None:
        inst_conditions.append("id = ?")
        inst_params.append(instance_id)
    if owner_id is not None:
        inst_conditions.append("created_by = ?")
        inst_params.append(owner_id)
    inst_where = ("WHERE " + " AND ".join(inst_conditions)) if inst_conditions else ""
    cursor = await db.execute(f"SELECT COUNT(*) FROM instances {inst_where}", inst_params)
    total_instances = (await cursor.fetchone())[0]

    # ---- session side (voice / chat) ----
    session_count = 0
    active_sessions = 0
    session_input = 0
    session_output = 0
    if type_filter is None or type_filter in _SESSION_TYPES:
        conditions: list[str] = []
        params: list = []
        if type_filter in _SESSION_TYPES:
            conditions.append("i.type = ?")
            params.append(type_filter)
        if instance_id is not None:
            conditions.append("s.instance_id = ?")
            params.append(instance_id)
        if owner_id is not None:
            conditions.append("s.created_by = ?")
            params.append(owner_id)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        placeholders = ", ".join("?" for _ in _ACTIVE_STATUSES)
        cursor = await db.execute(
            f"""
            SELECT
                COUNT(*),
                COALESCE(SUM(s.input_tokens), 0),
                COALESCE(SUM(s.output_tokens), 0),
                COALESCE(SUM(CASE WHEN s.status IN ({placeholders}) THEN 1 ELSE 0 END), 0)
            FROM sessions s
            JOIN instances i ON s.instance_id = i.id
            {where}
            """,
            # Active-status placeholders (in the CASE expression) appear BEFORE
            # the WHERE filter placeholders in the SQL text, so they must be
            # bound first.
            list(_ACTIVE_STATUSES) + params,
        )
        row = await cursor.fetchone()
        session_count, session_input, session_output, active_sessions = (
            row[0],
            row[1],
            row[2],
            row[3],
        )

    # ---- image side ----
    image_count = 0
    image_input = 0
    image_output = 0
    if type_filter is None or type_filter == "image":
        conditions = []
        params = []
        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)
        if owner_id is not None:
            conditions.append("created_by = ?")
            params.append(owner_id)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        cursor = await db.execute(
            f"""
            SELECT
                COUNT(*),
                COALESCE(SUM(input_tokens), 0),
                COALESCE(SUM(output_tokens), 0)
            FROM image_generations
            {where}
            """,
            params,
        )
        row = await cursor.fetchone()
        image_count, image_input, image_output = row[0], row[1], row[2]

    return DashboardStats(
        total_instances=total_instances,
        total_sessions=session_count,
        total_tests=session_count + image_count,
        active_sessions=active_sessions,
        total_input_tokens=session_input + image_input,
        total_output_tokens=session_output + image_output,
    )


async def compute_usage_by_instance(
    db: aiosqlite.Connection,
    *,
    type_filter: InstanceType | None = None,
    owner_id: str | None = None,
) -> list[InstanceUsage]:
    """Compute per-instance test counts and token usage.

    Combines sessions and image generations per instance. Instances with no
    matching tests are still returned with zero values. Results are ordered by
    instance name.
    """
    conditions: list[str] = []
    params: list = []
    if type_filter is not None:
        conditions.append("i.type = ?")
        params.append(type_filter)
    if owner_id is not None:
        conditions.append("i.created_by = ?")
        params.append(owner_id)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # Build owner sub-filters for sessions and image_generations
    session_owner_clause = ""
    image_owner_clause = ""
    sub_params: list = []
    if owner_id is not None:
        session_owner_clause = " AND s.created_by = ?"
        sub_params.append(owner_id)
        image_owner_clause = " AND g.created_by = ?"
        sub_params.append(owner_id)

    cursor = await db.execute(
        f"""
        SELECT
            i.id,
            i.name,
            (SELECT COUNT(*) FROM sessions s WHERE s.instance_id = i.id{session_owner_clause})
                + (SELECT COUNT(*) FROM image_generations g WHERE g.instance_id = i.id{image_owner_clause})
                AS test_count,
            (SELECT COALESCE(SUM(s.input_tokens), 0) FROM sessions s WHERE s.instance_id = i.id{session_owner_clause})
                + (SELECT COALESCE(SUM(g.input_tokens), 0) FROM image_generations g
                   WHERE g.instance_id = i.id{image_owner_clause}) AS total_input_tokens,
            (SELECT COALESCE(SUM(s.output_tokens), 0) FROM sessions s WHERE s.instance_id = i.id{session_owner_clause})
                + (SELECT COALESCE(SUM(g.output_tokens), 0) FROM image_generations g
                   WHERE g.instance_id = i.id{image_owner_clause}) AS total_output_tokens
        FROM instances i
        {where}
        ORDER BY i.name
        """,
        sub_params + sub_params + sub_params + params,
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


async def compute_usage_by_type(
    db: aiosqlite.Connection,
    *,
    instance_id: str | None = None,
    owner_id: str | None = None,
) -> list[TypeUsage]:
    """Compute test count and token usage grouped by test type.

    Always returns one entry per type (``voice``, ``chat``, ``image``); a type
    with no matching records yields zero values rather than being omitted.
    """
    # Session-backed types (voice / chat) grouped by instances.type.
    conditions: list[str] = []
    params: list = []
    if instance_id is not None:
        conditions.append("s.instance_id = ?")
        params.append(instance_id)
    if owner_id is not None:
        conditions.append("s.created_by = ?")
        params.append(owner_id)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    cursor = await db.execute(
        f"""
        SELECT
            i.type,
            COUNT(*),
            COALESCE(SUM(s.input_tokens), 0),
            COALESCE(SUM(s.output_tokens), 0)
        FROM sessions s
        JOIN instances i ON s.instance_id = i.id
        {where}
        GROUP BY i.type
        """,
        params,
    )
    session_rows = {row[0]: (row[1], row[2], row[3]) for row in await cursor.fetchall()}

    # Image-backed type.
    conditions = []
    params = []
    if instance_id is not None:
        conditions.append("instance_id = ?")
        params.append(instance_id)
    if owner_id is not None:
        conditions.append("created_by = ?")
        params.append(owner_id)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    cursor = await db.execute(
        f"""
        SELECT
            COUNT(*),
            COALESCE(SUM(input_tokens), 0),
            COALESCE(SUM(output_tokens), 0)
        FROM image_generations
        {where}
        """,
        params,
    )
    image_row = await cursor.fetchone()

    def _session_usage(test_type: InstanceType) -> TypeUsage:
        count, input_tokens, output_tokens = session_rows.get(test_type, (0, 0, 0))
        return TypeUsage(
            type=test_type,
            test_count=count,
            total_input_tokens=input_tokens,
            total_output_tokens=output_tokens,
        )

    return [
        _session_usage("voice"),
        _session_usage("chat"),
        TypeUsage(
            type="image",
            test_count=image_row[0],
            total_input_tokens=image_row[1],
            total_output_tokens=image_row[2],
        ),
    ]
