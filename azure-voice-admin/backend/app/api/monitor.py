"""System monitoring API — LiveKit rooms, network status, WebRTC stats."""

import asyncio
import os
import re
import socket
import time
from datetime import UTC, datetime

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
        ("LiveKit TCP (WebRTC)", "livekit", 7881, "tcp"),
        ("Backend API", "127.0.0.1", 8090, "tcp"),
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
        from livekit.api import ListRoomsRequest

        rooms_response = await lk.room.list_rooms(ListRoomsRequest())
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


# ---------------------------------------------------------------------------
# UDP Port Status
# ---------------------------------------------------------------------------

UDP_PORT_START = 50000
UDP_PORT_END = 50020


def _parse_ss_output(output: str) -> dict[int, dict]:
    """Parse `ss -unap` output and return a dict of port -> info for ports in range."""
    ports_info: dict[int, dict] = {}
    lines = output.strip().split("\n")

    for line in lines:
        # Skip header line
        if line.startswith("State") or line.startswith("Netid"):
            continue

        # ss -unap output format:
        # State  Recv-Q  Send-Q  Local Address:Port  Peer Address:Port  Process
        # UNCONN 0       0       0.0.0.0:50000       0.0.0.0:*          users:(("livekit-server",pid=123,fd=4))
        parts = line.split()
        if len(parts) < 5:
            continue

        try:
            recv_queue = int(parts[1])
            send_queue = int(parts[2])
        except (ValueError, IndexError):
            continue

        # Extract local address:port
        local_addr = parts[3]
        # Handle IPv6 format like [::]:port or regular ip:port
        if "]:" in local_addr:
            port_str = local_addr.rsplit(":", 1)[-1]
        else:
            port_str = local_addr.rsplit(":", 1)[-1]

        try:
            port = int(port_str)
        except ValueError:
            continue

        if port < UDP_PORT_START or port > UDP_PORT_END:
            continue

        # Extract process name from users:((...)) if present
        process_name = None
        process_match = re.search(r'users:\(\("([^"]+)"', line)
        if process_match:
            process_name = process_match.group(1)

        ports_info[port] = {
            "port": port,
            "bound": True,
            "recv_queue": recv_queue,
            "send_queue": send_queue,
            "recv_packets": None,  # ss doesn't provide packet counts directly
            "send_packets": None,
            "process": process_name,
        }

    return ports_info


def _parse_proc_net_udp(content: str) -> dict[int, dict]:
    """Parse /proc/net/udp content and return a dict of port -> info for ports in range."""
    ports_info: dict[int, dict] = {}
    lines = content.strip().split("\n")

    for line in lines:
        # Skip header
        if "local_address" in line:
            continue

        parts = line.split()
        if len(parts) < 5:
            continue

        # Format: sl local_address rem_address st tx_queue:rx_queue ...
        # local_address is hex_ip:hex_port
        try:
            local_addr = parts[1]
            _, port_hex = local_addr.split(":")
            port = int(port_hex, 16)
        except (ValueError, IndexError):
            continue

        if port < UDP_PORT_START or port > UDP_PORT_END:
            continue

        # tx_queue:rx_queue is in parts[4]
        try:
            tx_rx = parts[4]
            tx_queue_hex, rx_queue_hex = tx_rx.split(":")
            send_queue = int(tx_queue_hex, 16)
            recv_queue = int(rx_queue_hex, 16)
        except (ValueError, IndexError):
            send_queue = 0
            recv_queue = 0

        ports_info[port] = {
            "port": port,
            "bound": True,
            "recv_queue": recv_queue,
            "send_queue": send_queue,
            "recv_packets": None,
            "send_packets": None,
            "process": None,  # /proc/net/udp doesn't include process info
        }

    return ports_info


@router.get("/udp-ports")
async def udp_ports(
    user: CurrentUser = Depends(require_permission("audit:read")),
) -> dict:
    """Return UDP port binding status and packet counters for range 50000-50020."""
    error_msg = None
    ports_info: dict[int, dict] = {}

    # Try ss -unap first
    try:
        proc = await asyncio.create_subprocess_exec(
            "ss",
            "-unap",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0 and stdout:
            ports_info = _parse_ss_output(stdout.decode("utf-8", errors="replace"))
        else:
            raise OSError(
                f"ss command failed (exit {proc.returncode}): {stderr.decode('utf-8', errors='replace').strip()}"
            )

    except FileNotFoundError:
        # ss not available, fallback to /proc/net/udp
        try:
            with open("/proc/net/udp") as f:
                content = f.read()
            ports_info = _parse_proc_net_udp(content)
        except (FileNotFoundError, PermissionError, OSError) as e:
            error_msg = f"System inspection failed: ss command not found and /proc/net/udp not accessible ({e})"

    except OSError as e:
        # ss failed, try fallback
        try:
            with open("/proc/net/udp") as f:
                content = f.read()
            ports_info = _parse_proc_net_udp(content)
        except (FileNotFoundError, PermissionError, OSError) as fallback_err:
            error_msg = f"System inspection failed: {e}; fallback also failed: {fallback_err}"

    except Exception as e:
        error_msg = f"System inspection failed: {e}"

    # Build response for all ports in range
    ports_list = []
    for port in range(UDP_PORT_START, UDP_PORT_END + 1):
        if port in ports_info:
            ports_list.append(ports_info[port])
        else:
            ports_list.append(
                {
                    "port": port,
                    "bound": False,
                    "recv_queue": 0,
                    "send_queue": 0,
                    "recv_packets": None,
                    "send_packets": None,
                    "process": None,
                }
            )

    return {
        "ports": ports_list,
        "port_range": {"start": UDP_PORT_START, "end": UDP_PORT_END},
        "error": error_msg,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/turn-status")
async def turn_status(
    user: CurrentUser = Depends(require_permission("audit:read")),
):
    """Check TURN/STUN service reachability on TCP port 7881."""
    from urllib.parse import urlparse

    livekit_url = os.environ.get("LIVEKIT_URL", "ws://livekit:7880")
    parsed = urlparse(livekit_url)
    host = parsed.hostname or "livekit"
    port = 7881

    timestamp = datetime.now(UTC).isoformat()

    try:
        start = time.time()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=3.0,
        )
        latency_ms = int((time.time() - start) * 1000)
        writer.close()
        await writer.wait_closed()

        return {
            "reachable": True,
            "latency_ms": latency_ms,
            "timeout": False,
            "host": host,
            "port": port,
            "timestamp": timestamp,
        }
    except TimeoutError:
        return {
            "reachable": False,
            "latency_ms": None,
            "timeout": True,
            "host": host,
            "port": port,
            "timestamp": timestamp,
        }
    except (OSError, Exception):
        return {
            "reachable": False,
            "latency_ms": None,
            "timeout": False,
            "host": host,
            "port": port,
            "timestamp": timestamp,
        }


# ---------------------------------------------------------------------------
# WebRTC Stats
# ---------------------------------------------------------------------------


def _extract_track_stats(track_info) -> dict:
    """Extract track statistics from a LiveKit TrackInfo protobuf object.

    LiveKit's RoomService API exposes TrackInfo which includes track type,
    source, and codec/layer info. Full RTP stats (packet loss, RTT, jitter)
    are only available server-side or via client-side WebRTC getStats().
    We extract what's available and return defaults for unavailable metrics.
    """
    # Determine track type from protobuf enum: AUDIO=0, VIDEO=1, DATA=2
    track_type_map = {0: "audio", 1: "video", 2: "data"}
    track_type = track_type_map.get(track_info.type, "unknown")

    # Determine direction from source: CAMERA/MICROPHONE/SCREEN_SHARE are publish
    # TrackSource enum: UNKNOWN=0, CAMERA=1, MICROPHONE=2, SCREEN_SHARE=3, SCREEN_SHARE_AUDIO=4
    source_val = track_info.source if hasattr(track_info, "source") else 0
    direction = "publish" if source_val > 0 else "subscribe"

    # Extract bitrate from video layers if available
    bitrate_kbps = 0.0
    if hasattr(track_info, "codecs") and track_info.codecs:
        for codec in track_info.codecs:
            if hasattr(codec, "layers") and codec.layers:
                for layer in codec.layers:
                    if hasattr(layer, "bitrate") and layer.bitrate > 0:
                        bitrate_kbps = max(bitrate_kbps, layer.bitrate / 1000.0)

    return {
        "track_type": track_type,
        "direction": direction,
        "packet_loss_ratio": 0.0,
        "rtt_ms": 0.0,
        "jitter_ms": 0.0,
        "bitrate_kbps": bitrate_kbps,
    }


def _build_participant_stats(participant_info) -> dict:
    """Build participant stats dict from a LiveKit ParticipantInfo protobuf object.

    ICE candidate type and connection state are not exposed via the RoomService
    API (they are only available client-side). We report defaults.
    """
    tracks = []
    for track in participant_info.tracks:
        # Skip DATA tracks, only report audio/video
        if track.type == 2:
            continue
        tracks.append(_extract_track_stats(track))

    # ParticipantInfo.State enum: JOINING=0, JOINED=1, ACTIVE=2, DISCONNECTED=3
    state_map = {0: "joining", 1: "joined", 2: "active", 3: "disconnected"}
    state_val = participant_info.state if hasattr(participant_info, "state") else 0

    return {
        "identity": participant_info.identity,
        "ice_candidate_type": "host",
        "ice_connection_state": state_map.get(state_val, "unknown"),
        "tracks": tracks,
    }


@router.get("/webrtc-stats")
async def webrtc_stats(
    user: CurrentUser = Depends(require_permission("audit:read")),
) -> dict:
    """Return per-participant WebRTC track statistics grouped by room."""
    api_key, api_secret = _get_livekit_credentials()
    timestamp = datetime.now(UTC).isoformat()

    if not api_key or not api_secret:
        return {
            "rooms": [],
            "error": "LiveKit credentials not configured",
            "timestamp": timestamp,
        }

    try:
        from livekit.api import ListParticipantsRequest, ListRoomsRequest, LiveKitAPI

        lk = LiveKitAPI(
            url=os.environ.get("LIVEKIT_URL", "ws://livekit:7880"),
            api_key=api_key,
            api_secret=api_secret,
        )

        # Get all active rooms
        rooms_response = await lk.room.list_rooms(ListRoomsRequest())
        rooms_data = []

        for room in rooms_response.rooms:
            # Get participants for each room
            participants_response = await lk.room.list_participants(
                ListParticipantsRequest(room=room.name)
            )

            participants_data = []
            for participant in participants_response.participants:
                participants_data.append(_build_participant_stats(participant))

            rooms_data.append(
                {
                    "room_name": room.name,
                    "participants": participants_data,
                }
            )

        await lk.aclose()

        return {
            "rooms": rooms_data,
            "error": None,
            "timestamp": timestamp,
        }

    except Exception as e:
        return {
            "rooms": [],
            "error": f"LiveKit RoomService unavailable: {e}",
            "timestamp": timestamp,
        }
