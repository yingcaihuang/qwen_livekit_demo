"""In-process async job queue for image generation.

Image generation can take a long time. Instead of running it synchronously in
the request handler (which aborts if the user leaves the page), the API enqueues
a job here and returns immediately with a ``pending`` record. A small pool of
background worker tasks drains the queue, calling
:meth:`ImageService.process_job` for each job id, which does the Azure call,
writes files, and updates the DB row status to ``completed`` / ``failed``.

Design notes:
- This is a *local* single-process tool, so an in-memory ``asyncio.Queue`` is
  sufficient — there is no external broker.
- The queue holds only generation *ids* (strings); the worker reloads all state
  from the database, so no request-scoped objects leak across tasks.
- On startup :func:`recover_interrupted_jobs` flips any rows left in
  ``pending`` / ``processing`` (from a previous run that was killed mid-flight)
  to ``failed`` so they do not hang forever waiting for an in-memory job that no
  longer exists.
- Imports of :class:`ImageService` are done lazily inside functions to avoid a
  circular import (``image_service`` imports this module for ``enqueue_job``).
"""

import asyncio
import logging

logger = logging.getLogger("azure_openai_admin")

# Lazily-created module-level queue of generation ids awaiting processing.
_queue: asyncio.Queue[str] | None = None

# Background worker tasks draining ``_queue``.
_workers: list[asyncio.Task] = []


def _get_queue() -> asyncio.Queue[str]:
    """Return the module-level queue, creating it lazily on first use."""
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


def enqueue_job(generation_id: str) -> None:
    """Enqueue a generation id for background processing (non-blocking)."""
    _get_queue().put_nowait(generation_id)


async def _worker_loop(worker_id: int) -> None:
    """Drain the queue forever, processing one generation id at a time.

    Each job is fully isolated: a failure in one job is logged and never
    propagates out of the loop, so the worker keeps serving subsequent jobs.
    """
    from app.services.image_service import ImageService

    queue = _get_queue()
    service = ImageService()
    logger.info("Image worker %d started", worker_id)
    while True:
        gid = await queue.get()
        try:
            await service.process_job(gid)
        except Exception:  # pragma: no cover - defensive; process_job swallows its own
            logger.exception("Image worker %d failed processing job %s", worker_id, gid)
        finally:
            queue.task_done()


async def start_workers(n: int = 2) -> None:
    """Start ``n`` background worker tasks (idempotent).

    Calling this again while workers are already running is a no-op.
    """
    global _workers
    # Drop any tasks that already finished (e.g. were cancelled previously).
    _workers = [t for t in _workers if not t.done()]
    if _workers:
        return
    _get_queue()
    _workers = [asyncio.create_task(_worker_loop(i)) for i in range(n)]
    logger.info("Started %d image worker(s)", n)


async def stop_workers() -> None:
    """Cancel all worker tasks and await their cancellation."""
    global _workers
    if not _workers:
        return
    for task in _workers:
        task.cancel()
    await asyncio.gather(*_workers, return_exceptions=True)
    _workers = []
    logger.info("Stopped image workers")


async def recover_interrupted_jobs() -> None:
    """Mark any ``pending``/``processing`` rows as ``failed`` at startup.

    In-memory queued jobs do not survive a process restart, so rows left in a
    non-terminal state by a previous run would otherwise hang forever. Flip them
    to ``failed`` with a clear message so the user knows to retry.
    """
    import aiosqlite

    import app.database as db_mod

    db = await aiosqlite.connect(db_mod.DB_PATH)
    try:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            UPDATE image_generations
            SET status = 'failed',
                error_message = '服务重启导致生成任务中断，请重新发起',
                ended_at = datetime('now')
            WHERE status IN ('pending', 'processing')
            """
        )
        await db.commit()
    finally:
        await db.close()
