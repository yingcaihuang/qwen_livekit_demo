"""FastAPI application entry point for Azure Voice Testing Admin."""

import logging
import os
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger("azure_voice_admin")


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup: initialize database
    from app.database import init_db

    await init_db()
    logger.info("Database initialized successfully.")

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

    yield

    # Shutdown
    logger.info("Application shutting down.")


app = FastAPI(
    title="Azure Voice Testing Admin",
    description="Azure OpenAI Realtime Voice Testing Management System",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware - allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static directory for frontend production build
static_dir = Path(__file__).parent.parent / "static"


# Register API routers
from app.api.instances import router as instances_router

app.include_router(instances_router)

# Conditionally import session and dashboard routers if they exist
try:
    from app.api.sessions import router as sessions_router
    from app.api.sessions import internal_router as sessions_internal_router

    app.include_router(sessions_router)
    app.include_router(sessions_internal_router)
except (ImportError, ModuleNotFoundError):
    pass

try:
    from app.api.dashboard import router as dashboard_router

    app.include_router(dashboard_router)
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
    return {
        "status": "ok",
        "livekit_connected": livekit_reachable,
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
