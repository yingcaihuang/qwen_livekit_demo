"""REST API routes for the Unified History across voice / chat / image tests.

Implements the unified-history path described in ``design.md`` (section
"Unified History API"): a single ``GET /api/history`` endpoint that merges

- ``sessions`` rows (``voice`` AND ``chat`` — the concrete type is derived by
  joining ``sessions.instance_id`` to ``instances.type``), and
- ``image_generations`` rows (always ``image``),

into one paginated list ordered by start time, most recent first (Requirement
6.1). Filtering by ``type`` (voice|chat|image) and by ``instance_id`` is
supported (Requirements 6.3, 6.4), and existing voice sessions remain
accessible without data loss (Requirement 6.6).

Implementation approach:
The two sources are projected onto a common column set
``(id, type, instance_id, instance_name, title, start_time, input_tokens,
output_tokens, status)`` and combined with ``UNION ALL``. An outer query applies
``ORDER BY start_time DESC`` plus ``LIMIT``/``OFFSET`` for pagination, and a
sibling ``COUNT(*)`` over the same union computes the total across both sources
for the active filters. Image rows use ``created_at`` as their ``start_time`` so
the two sources sort on a shared timeline.
"""

import aiosqlite
from fastapi import APIRouter, Depends

from app.database import get_db
from app.models.history import HistoryItem, PaginatedHistory

router = APIRouter(prefix="/api/history", tags=["history"])

# Maximum characters kept for a derived title before it is truncated with an
# ellipsis. Titles come from free-form user prompts / messages, so we cap them
# for a consistent list view.
_TITLE_MAX_LEN = 120

# Fallback titles when the source value is empty (Requirement 6.5 detail views
# still resolve the full record; the list just needs a readable label).
_TITLE_FALLBACKS = {
    "voice": "Voice session",
    "chat": "Chat conversation",
    "image": "Image generation",
}

# Sessions source: voice/chat rows. The concrete type is derived from the joined
# instance. For chat rows the title is the first user message; for voice rows it
# is the room name.
_SESSIONS_SOURCE = """
    SELECT
        s.id AS id,
        i.type AS type,
        s.instance_id AS instance_id,
        i.name AS instance_name,
        CASE
            WHEN i.type = 'chat' THEN COALESCE(
                (
                    SELECT sm.content FROM session_messages sm
                    WHERE sm.session_id = s.id AND sm.role = 'user'
                    ORDER BY sm.id ASC LIMIT 1
                ),
                ''
            )
            ELSE s.room_name
        END AS title,
        s.start_time AS start_time,
        s.input_tokens AS input_tokens,
        s.output_tokens AS output_tokens,
        s.status AS status
    FROM sessions s
    JOIN instances i ON i.id = s.instance_id
"""

# Image source: image_generations rows, always type 'image'. created_at is the
# shared "start_time" so both sources sort on the same timeline.
_IMAGE_SOURCE = """
    SELECT
        g.id AS id,
        'image' AS type,
        g.instance_id AS instance_id,
        i.name AS instance_name,
        g.prompt AS title,
        g.created_at AS start_time,
        g.input_tokens AS input_tokens,
        g.output_tokens AS output_tokens,
        g.status AS status
    FROM image_generations g
    JOIN instances i ON i.id = g.instance_id
"""


def _build_union(type_filter: str | None, instance_id: str | None) -> tuple[str, list]:
    """Build the ``UNION ALL`` body (no ORDER/LIMIT) and its bound parameters.

    Which sources participate depends on ``type_filter``:
    - ``image`` -> image source only
    - ``voice`` / ``chat`` -> sessions source only (restricted to that type)
    - ``None`` -> both sources merged
    ``instance_id`` filters every participating source.
    """
    parts: list[str] = []
    params: list = []

    include_sessions = type_filter in (None, "voice", "chat")
    include_image = type_filter in (None, "image")

    if include_sessions:
        clauses: list[str] = []
        if type_filter in ("voice", "chat"):
            clauses.append("i.type = ?")
            params.append(type_filter)
        if instance_id is not None:
            clauses.append("s.instance_id = ?")
            params.append(instance_id)
        sql = _SESSIONS_SOURCE
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        parts.append(sql)

    if include_image:
        clauses = []
        if instance_id is not None:
            clauses.append("g.instance_id = ?")
            params.append(instance_id)
        sql = _IMAGE_SOURCE
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        parts.append(sql)

    union_sql = " UNION ALL ".join(f"SELECT * FROM ({p})" for p in parts)
    return union_sql, params


def _derive_title(raw: str | None, item_type: str) -> str:
    """Return a readable, length-capped title, falling back per type when empty."""
    title = (raw or "").strip()
    if not title:
        return _TITLE_FALLBACKS.get(item_type, "Untitled")
    if len(title) > _TITLE_MAX_LEN:
        return title[:_TITLE_MAX_LEN].rstrip() + "…"
    return title


@router.get("", response_model=PaginatedHistory)
async def list_history(
    type: str | None = None,
    instance_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: aiosqlite.Connection = Depends(get_db),
) -> PaginatedHistory:
    """Return a paginated, merged history across voice / chat / image tests.

    Merges ``sessions`` (voice/chat) and ``image_generations`` (image) ordered
    by ``start_time`` descending (Requirement 6.1). Supports ``type`` and
    ``instance_id`` filters (Requirements 6.3, 6.4). Existing voice sessions are
    always included so no data is lost after the upgrade (Requirement 6.6).

    An unrecognized ``type`` value yields an empty result set rather than an
    error (defensive: keeps the view stable, Requirement 9.2 spirit).
    """
    page = max(1, int(page))
    page_size = max(1, int(page_size))
    offset = (page - 1) * page_size

    # Guard against unrecognized type filters: return an empty page instead of
    # constructing a query with no sources (which would be invalid SQL).
    if type is not None and type not in ("voice", "chat", "image"):
        return PaginatedHistory(items=[], total=0, page=page, page_size=page_size)

    union_sql, base_params = _build_union(type, instance_id)

    # Total across both sources for the active filters.
    count_sql = f"SELECT COUNT(*) FROM ({union_sql})"
    cursor = await db.execute(count_sql, tuple(base_params))
    total = (await cursor.fetchone())[0]

    # Ordered, paginated page of the merged set. id is a tiebreaker for stable
    # ordering when two rows share a start_time.
    page_sql = f"SELECT * FROM ({union_sql}) ORDER BY start_time DESC, id DESC LIMIT ? OFFSET ?"
    cursor = await db.execute(page_sql, (*base_params, page_size, offset))
    rows = await cursor.fetchall()

    items = [
        HistoryItem(
            id=row["id"],
            type=row["type"],
            instance_id=row["instance_id"],
            instance_name=row["instance_name"],
            title=_derive_title(row["title"], row["type"]),
            start_time=row["start_time"],
            input_tokens=row["input_tokens"] or 0,
            output_tokens=row["output_tokens"] or 0,
            status=row["status"],
        )
        for row in rows
    ]

    return PaginatedHistory(items=items, total=total, page=page, page_size=page_size)
