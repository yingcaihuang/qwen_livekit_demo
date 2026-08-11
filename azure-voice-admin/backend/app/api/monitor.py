"""System monitoring API — LiveKit rooms, network status, WebRTC stats."""

import os
import socket
import time

import aiosqlite
from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, require_permission
from app.database import get_db

router = APIRouter(prefix="/api/admin/monitor", tags=["monitor"])


def _get_livekit_api_url():
    return (
        os.environ.get("LIVEKIT_URL", "ws://livekit:7880")
        .replace("ws://", "http://")
        .replace("wss://", "https://")
    )


def _get_livekit_credentials():
    """Get LiveKit API key and secret for generating access tokens."""
    return (
        os.environ.get("LIVEKIT_API_KEY", ""),
        os.environ.get("LIVEKIT_API_SECRET", ""),
    )


@router.get("/overview")
async def monitor_overview(
    user: CurrentUser = Depends(require_permission("audit:read")),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Get system monitoring overview."""
    # 1. LiveKit server info
    livekit_url = _get_livekit_api_url()
    livekit_status = {"reachable": False, "url": livekit_url}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        from urllib.parse import urlparse

        parsed = urlparse(livekit_url)
        host = parsed.hostname or "livekit"
        port = parsed.port or 7880
        result = s.connect_ex((host, port))
        s.close()
        livekit_status["reachable"] = result == 0
    except Exception:
        pass

    # 2. Active sessions count
    cursor = await db.execute(
        "SELECT COUNT(*) FROM sessions WHERE status IN ('connecting', 'connected', 'active')"
    )
    active_sessions = (await cursor.fetchone())[0]

    # 3. Active worker processes
    try:
        from app.services.process_manager import process_manager

        active_workers = list(process_manager._processes.keys())
    except Exception:
        active_workers = []

    # 4. Server network ports
    ports_status = []
    check_ports = [
        ("LiveKit WebSocket", "livekit", 7880, "tcp"),
        ("LiveKit TCP (WebRTC)", "0.0.0.0", 7881, "tcp"),
        ("Backend API", "0.0.0.0", 8090, "tcp"),
    ]
    for label, host_check, port_check, proto in check_ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            reachable = s.connect_ex((host_check, port_check)) == 0
            s.close()
        except Exception:
            reachable = False
        ports_status.append(
            {
                "label": label,
                "host": host_check,
                "port": port_check,
                "protocol": proto,
                "reachable": reachable,
            }
        )

    # 5. Environment info
    node_ip = os.environ.get("LIVEKIT_NODE_IP", "not set")
    public_url = os.environ.get("LIVEKIT_PUBLIC_URL", "not set")

    # 6. Recent session connection stats (last 10 completed sessions with timing)
    cursor = await db.execute("""
        SELECT s.id, s.room_name, s.status, s.start_time, s.end_time,
               s.input_tokens, s.output_tokens, i.name as instance_name, i.type
        FROM sessions s
        LEFT JOIN instances i ON s.instance_id = i.id
        WHERE s.status IN ('completed', 'cancelled', 'error', 'active', 'connecting', 'connected')
        ORDER BY s.start_time DESC LIMIT 10
    """)
    recent_sessions = []
    for row in await cursor.fetchall():
        duration = None
        if row[3] and row[4]:
            try:
                from datetime import datetime

                start = datetime.fromisoformat(row[3])
                end = datetime.fromisoformat(row[4])
                duration = int((end - start).total_seconds())
            except Exception:
                pass
        recent_sessions.append(
            {
                "id": row[0],
                "room_name": row[1],
                "status": row[2],
                "start_time": row[3],
                "end_time": row[4],
                "input_tokens": row[5],
                "output_tokens": row[6],
                "instance_name": row[7],
                "type": row[8],
                "duration_seconds": duration,
            }
        )

    return {
        "livekit": livekit_status,
        "active_sessions": active_sessions,
        "active_workers": active_workers,
        "ports": ports_status,
        "environment": {
            "node_ip": node_ip,
            "public_url": public_url,
            "livekit_url": os.environ.get("LIVEKIT_URL", "not set"),
        },
        "recent_sessions": recent_sessions,
    }


@router.get("/rooms")
async def list_rooms(
    user: CurrentUser = Depends(require_permission("audit:read")),
):
    """List active LiveKit rooms via LiveKit API."""
    api_key, api_secret = _get_livekit_credentials()
    if not api_key or not api_secret:
        return {"rooms": [], "error": "LiveKit credentials not configured"}

    try:
        from livekit.api import LiveKitAPI

        lk = LiveKitAPI(
            url=os.environ.get("LIVEKIT_URL", "ws://livekit:7880"),
            api_key=api_key,
            api_secret=api_secret,
        )
        rooms_response = await lk.room.list_rooms()
        await lk.aclose()

        rooms = []
        for room in rooms_response.rooms:
            rooms.append(
                {
                    "name": room.name,
                    "sid": room.sid,
                    "num_participants": room.num_participants,
                    "num_publishers": room.num_publishers,
                    "creation_time": room.creation_time,
                    "active_recording": room.active_recording,
                }
            )
        return {"rooms": rooms}
    except Exception as e:
        return {"rooms": [], "error": str(e)}


@router.get("/network-test")
async def network_test(
    user: CurrentUser = Depends(require_permission("audit:read")),
):
    """Run basic network connectivity tests."""
    results = []

    # Test DNS resolution
    tests = [
        ("DNS: livekit (internal)", "livekit"),
        ("DNS: Azure endpoint", "jiuyunai1-1.services.ai.azure.com"),
    ]
    for label, hostname in tests:
        try:
            start = time.time()
            ip = socket.gethostbyname(hostname)
            latency = int((time.time() - start) * 1000)
            results.append({"test": label, "status": "ok", "result": ip, "latency_ms": latency})
        except Exception as e:
            results.append({"test": label, "status": "error", "result": str(e), "latency_ms": None})

    # Test TCP connectivity to Azure
    try:
        start = time.time()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(("jiuyunai1-1.services.ai.azure.com", 443))
        latency = int((time.time() - start) * 1000)
        s.close()
        results.append(
            {
                "test": "TCP: Azure HTTPS (443)",
                "status": "ok",
                "result": "connected",
                "latency_ms": latency,
            }
        )
    except Exception as e:
        results.append(
            {
                "test": "TCP: Azure HTTPS (443)",
                "status": "error",
                "result": str(e),
                "latency_ms": None,
            }
        )

    return {"tests": results, "timestamp": time.time()}
