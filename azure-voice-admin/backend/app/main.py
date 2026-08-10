"""FastAPI application entry point for Azure Voice Testing Admin."""

import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

logger = logging.getLogger("azure_voice_admin")

SESSION_TIMEOUT_MINUTES = 5
CLEANUP_INTERVAL_SECONDS = 60


def _check_livekit_reachable(livekit_url: str, timeout: float = 3.0) -> bool:
    """Check if the LiveKit server is reachable via TCP connect.

    Parses the WebSocket URL to extract host/port and attempts a socket connection.
    Returns True if reachable, False otherwise.
    """
    try:
        parsed = urlparse(livekit_url)
        host = parsed.hostname or "localhost"
        # Default port: 7880 for ws, 7881 for wss
        port = parsed.port or (7881 if parsed.scheme == "wss" else 7880)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.warning(f"LiveKit reachability check error: {e}")
        return False


def _check_avx2_support() -> bool:
    """Check if livekit-agents native extensions are usable.

    The livekit SDK >= 1.0 includes Rust-compiled native extensions that may
    require AVX2 on x86_64. Rather than checking CPU flags (which is unreliable
    in Docker/VM environments), we directly attempt to import livekit.agents.
    If the import succeeds without segfault, realtime features are available.
    """
    import subprocess
    import sys

    try:
        # Run import in a subprocess to catch segfaults/core dumps
        result = subprocess.run(
            [sys.executable, "-c", "import livekit.agents"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


async def _session_cleanup_loop():
    """Background task: periodically mark stale sessions as cancelled."""
    import aiosqlite

    from app.database import DB_PATH

    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("PRAGMA foreign_keys = ON")

                # Find stale sessions (active for more than SESSION_TIMEOUT_MINUTES)
                cursor = await db.execute(
                    """
                    SELECT id FROM sessions
                    WHERE status IN ('connecting', 'connected')
                    AND start_time < datetime('now', ? || ' minutes')
                    """,
                    (f"-{SESSION_TIMEOUT_MINUTES}",),
                )
                stale_sessions = await cursor.fetchall()

                if stale_sessions:
                    for (session_id,) in stale_sessions:
                        await db.execute(
                            "UPDATE sessions SET status = 'cancelled', end_time = datetime('now') WHERE id = ?",
                            (session_id,),
                        )
                        logger.info(f"Auto-cancelled stale session: {session_id[:8]}...")

                    await db.commit()
                    logger.info(f"Cleaned up {len(stale_sessions)} stale session(s)")

                    # Also terminate any running agent processes
                    try:
                        from app.services.process_manager import process_manager

                        for (session_id,) in stale_sessions:
                            await process_manager.terminate_agent(session_id)
                    except Exception:
                        pass

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Session cleanup error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup: initialize database
    from app.database import init_db

    await init_db()
    logger.info("Database initialized successfully.")

    # Recover any image generation jobs left mid-flight by a previous run and
    # start the in-process worker pool. Wrap in try/except so a queue failure
    # never blocks application startup.
    try:
        from app.services.image_queue import recover_interrupted_jobs, start_workers

        await recover_interrupted_jobs()
        await start_workers()
        logger.info("Image generation workers started.")
    except Exception as e:
        logger.error(f"Failed to start image generation workers: {e}")

    # Check LiveKit server connectivity
    livekit_url = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
    livekit_reachable = _check_livekit_reachable(livekit_url)

    if livekit_reachable:
        logger.info(f"LiveKit server is reachable at {livekit_url}")
    else:
        logger.warning(
            f"LiveKit server is NOT reachable at {livekit_url}. "
            "Session creation will be disabled until LiveKit becomes available."
        )

    # Store connectivity status in app.state for other endpoints to check
    app.state.livekit_reachable = livekit_reachable
    app.state.livekit_url = livekit_url

    # Check AVX2 support (required for livekit-agents native extensions)
    avx2_supported = _check_avx2_support()
    app.state.avx2_supported = avx2_supported
    # realtime features (voice, translate, transcribe) require both LiveKit and AVX2
    app.state.realtime_available = livekit_reachable and avx2_supported

    if not avx2_supported:
        logger.warning(
            "CPU does not support AVX2 instructions. "
            "Realtime features (voice, translate, transcribe) will be DISABLED. "
            "Chat and image generation will work normally."
        )

    # Start session cleanup background task
    cleanup_task = asyncio.create_task(_session_cleanup_loop())

    yield

    # Shutdown: cancel cleanup task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # Stop image generation workers.
    try:
        from app.services.image_queue import stop_workers

        await stop_workers()
    except Exception as e:
        logger.error(f"Failed to stop image generation workers: {e}")

    logger.info("Application shutting down.")


app = FastAPI(
    title="Azure Voice Testing Admin",
    description="Azure OpenAI Realtime Voice Testing Management System",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware — configurable trusted origins, defaults to same-origin (no CORS needed)
_cors_origins_raw = os.environ.get("CORS_ALLOWED_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins if _cors_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static directory for frontend production build
static_dir = Path(__file__).parent.parent / "static"


# Register API routers
from app.api.instances import router as instances_router  # noqa: E402

app.include_router(instances_router)

# Conditionally import session and dashboard routers if they exist
try:
    from app.api.sessions import internal_router as sessions_internal_router
    from app.api.sessions import router as sessions_router

    app.include_router(sessions_router)
    app.include_router(sessions_internal_router)
except (ImportError, ModuleNotFoundError):
    pass

try:
    from app.api.dashboard import router as dashboard_router

    app.include_router(dashboard_router)
except (ImportError, ModuleNotFoundError):
    pass

try:
    from app.api.chat import router as chat_router

    app.include_router(chat_router)
except (ImportError, ModuleNotFoundError):
    pass

try:
    from app.api.images import router as images_router

    app.include_router(images_router)
except (ImportError, ModuleNotFoundError):
    pass

try:
    from app.api.history import router as history_router

    app.include_router(history_router)
except (ImportError, ModuleNotFoundError):
    pass

try:
    from app.api.translate_sessions import router as translate_sessions_router

    app.include_router(translate_sessions_router)
except (ImportError, ModuleNotFoundError):
    pass

try:
    from app.api.transcribe_sessions import router as transcribe_sessions_router

    app.include_router(transcribe_sessions_router)
except (ImportError, ModuleNotFoundError):
    pass

# Auth & admin routers
try:
    from app.api.auth import router as auth_router

    app.include_router(auth_router)
except (ImportError, ModuleNotFoundError):
    pass

try:
    from app.api.sso import router as sso_router

    app.include_router(sso_router)
except (ImportError, ModuleNotFoundError):
    pass

try:
    from app.api.admin_sso import router as admin_sso_router

    app.include_router(admin_sso_router)
except (ImportError, ModuleNotFoundError):
    pass

try:
    from app.api.admin_saml import router as admin_saml_router

    app.include_router(admin_saml_router)
except (ImportError, ModuleNotFoundError):
    pass

try:
    from app.api.saml import router as saml_router

    app.include_router(saml_router)
except (ImportError, ModuleNotFoundError):
    pass

try:
    from app.api.admin_roles import router as admin_roles_router

    app.include_router(admin_roles_router)
except (ImportError, ModuleNotFoundError):
    pass

try:
    from app.api.admin_users import router as admin_users_router

    app.include_router(admin_users_router)
except (ImportError, ModuleNotFoundError):
    pass

try:
    from app.api.scim import router as scim_router

    app.include_router(scim_router)
except (ImportError, ModuleNotFoundError):
    pass

# Register WebSocket endpoints if available
try:
    from app.api.websockets import ws_session_logs

    app.websocket("/ws/sessions/{session_id}/logs")(ws_session_logs)
except (ImportError, ModuleNotFoundError):
    pass


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    livekit_reachable = getattr(app.state, "livekit_reachable", False)
    avx2_supported = getattr(app.state, "avx2_supported", True)
    realtime_available = getattr(app.state, "realtime_available", True)
    return {
        "status": "ok",
        "livekit_connected": livekit_reachable,
        "avx2_supported": avx2_supported,
        "realtime_available": realtime_available,
    }


# SPA fallback: serve index.html for any path not matching /api/, /ws/, /internal/
# This enables client-side routing (React Router) to work on page refresh.
# Must be registered AFTER all API routes.
@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """Serve frontend SPA for all non-API routes."""
    # If the path matches a static file, serve it directly
    if static_dir.exists():
        file_path = static_dir / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))

    # Otherwise serve index.html for client-side routing
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))

    return {"error": "Frontend not built. Run 'pnpm build' in the frontend directory."}
