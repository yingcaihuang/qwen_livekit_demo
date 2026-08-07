#!/usr/bin/env python3
"""Single entry point to start the Azure Voice Testing Management System.

Usage:
    python start.py

This script:
1. Loads environment variables from backend/.env
2. Initializes the SQLite database
3. Checks LiveKit server reachability (warns if unreachable but continues)
4. Starts uvicorn to serve the FastAPI app on the configured PORT (default 8090)
"""

import asyncio
import logging
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

# Ensure the backend package is importable
BACKEND_DIR = Path(__file__).parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Load .env file from backend/.env
try:
    from dotenv import load_dotenv

    env_file = BACKEND_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✓ Loaded environment from {env_file}")
    else:
        print(f"⚠ No .env file found at {env_file}, using system environment variables")
except ImportError:
    print("⚠ python-dotenv not installed, using system environment variables")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("azure_voice_admin.start")


def check_livekit_reachable(livekit_url: str, timeout: float = 3.0) -> bool:
    """Check if the LiveKit server is reachable via TCP connect."""
    try:
        parsed = urlparse(livekit_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (7881 if parsed.scheme == "wss" else 7880)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.warning(f"LiveKit reachability check error: {e}")
        return False


async def init_database():
    """Initialize the SQLite database."""
    from app.database import init_db

    await init_db()
    logger.info("Database initialized successfully.")


def main():
    """Main entry point: initialize DB, check LiveKit, start uvicorn."""
    import uvicorn

    port = int(os.environ.get("PORT", "8090"))
    livekit_url = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")

    print()
    print("=" * 60)
    print("  Azure Voice Testing Management System")
    print("=" * 60)
    print()

    # Step 1: Initialize database
    print("→ Initializing database...")
    asyncio.run(init_database())
    print("  ✓ Database ready")
    print()

    # Step 2: Check LiveKit server reachability
    print(f"→ Checking LiveKit server at {livekit_url}...")
    if check_livekit_reachable(livekit_url):
        print("  ✓ LiveKit server is reachable")
    else:
        print("  ⚠ LiveKit server is NOT reachable")
        print("    Session creation will be disabled until LiveKit becomes available.")
        print("    Make sure LiveKit is running at the configured URL.")
    print()

    # Step 3: Start uvicorn
    print(f"→ Starting server on http://localhost:{port}")
    print()
    print("-" * 60)
    print("  Endpoints:")
    print(f"    Web UI:     http://localhost:{port}")
    print(f"    API:        http://localhost:{port}/api")
    print(f"    Health:     http://localhost:{port}/api/health")
    print(f"    WebSocket:  ws://localhost:{port}/ws/sessions/{{id}}/logs")
    print("-" * 60)
    print()
    print("  Press Ctrl+C to stop the server")
    print()

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
        app_dir=str(BACKEND_DIR),
    )


if __name__ == "__main__":
    main()
