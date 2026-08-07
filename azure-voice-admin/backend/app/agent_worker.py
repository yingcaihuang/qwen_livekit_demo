"""Agent Worker: standalone script spawned per Voice Session.

This script is executed as a subprocess by the Process Manager. It:
1. Reads Azure credentials and LiveKit room info from environment variables.
2. Connects to the specified LiveKit room using livekit-agents.
3. Uses Azure OpenAI Realtime API for voice interaction via the openai realtime plugin.
4. Outputs JSON lines to stdout for debug logging.
5. On session end, HTTP POSTs token usage to the management server.

Environment variables (all required):
    AZURE_ENDPOINT      - Azure OpenAI endpoint URL
    AZURE_API_KEY       - Azure OpenAI API key
    AZURE_DEPLOYMENT    - Azure OpenAI deployment name (e.g. gpt-realtime-2.1)
    LIVEKIT_URL         - LiveKit server WebSocket URL
    LIVEKIT_API_KEY     - LiveKit API key
    LIVEKIT_API_SECRET  - LiveKit API secret
    ROOM_NAME           - LiveKit room name to join
    SESSION_ID          - Session ID for usage reporting
    REPORT_URL          - URL to POST token usage
                          (e.g. http://localhost:8090/internal/sessions/{id}/usage)
"""

import json
import os
import sys
from datetime import datetime, timezone

import aiohttp
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import openai, silero


# ---------------------------------------------------------------------------
# Structured stdout logging helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def emit_event(
    event_type: str,
    direction: str = "internal",
    payload: str = "{}",
) -> None:
    """Write a structured JSON event line to stdout."""
    line = json.dumps(
        {
            "type": "event",
            "timestamp": _now_iso(),
            "direction": direction,
            "event_type": event_type,
            "payload": payload,
        },
        ensure_ascii=False,
    )
    print(line, flush=True)


def emit_error(message: str, details: str = "") -> None:
    """Write a structured error JSON line to stdout."""
    line = json.dumps(
        {
            "type": "error",
            "timestamp": _now_iso(),
            "message": message,
            "details": details,
        },
        ensure_ascii=False,
    )
    print(line, flush=True)


# ---------------------------------------------------------------------------
# Token usage tracking and reporting
# ---------------------------------------------------------------------------

_total_input_tokens: int = 0
_total_output_tokens: int = 0


async def report_usage() -> None:
    """POST accumulated token usage to the management server."""
    report_url = os.environ.get("REPORT_URL", "")
    if not report_url:
        emit_error("REPORT_URL not set, skipping usage report")
        return

    payload = {
        "input_tokens": _total_input_tokens,
        "output_tokens": _total_output_tokens,
    }

    emit_event(
        "usage.report",
        direction="outbound",
        payload=json.dumps(payload),
    )

    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                report_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    emit_error(
                        f"Usage report failed: HTTP {resp.status}",
                        details=body[:500],
                    )
                else:
                    emit_event("usage.reported", direction="outbound")
    except Exception as exc:
        emit_error("Usage report request failed", details=str(exc))


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------


class VoiceAssistant(Agent):
    """Voice assistant backed by Azure OpenAI Realtime."""

    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a helpful voice assistant. "
                "Answer concisely and naturally."
            )
        )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def entrypoint(ctx: JobContext) -> None:
    """Main entrypoint called by the livekit-agents framework."""
    global _total_input_tokens, _total_output_tokens

    # Read Azure configuration from environment
    azure_endpoint = os.environ.get("AZURE_ENDPOINT", "")
    azure_api_key = os.environ.get("AZURE_API_KEY", "")
    azure_deployment = os.environ.get("AZURE_DEPLOYMENT", "gpt-realtime-2.1")

    if not azure_endpoint or not azure_api_key:
        emit_error(
            "Missing Azure credentials",
            details="AZURE_ENDPOINT and AZURE_API_KEY must be set",
        )
        return

    emit_event("session.starting", payload=json.dumps({
        "room": ctx.room.name if ctx.room else "unknown",
        "azure_endpoint": azure_endpoint,
        "azure_deployment": azure_deployment,
    }))

    try:
        # Connect to the LiveKit room
        await ctx.connect()

        emit_event("room.connected", payload=json.dumps({
            "room_name": ctx.room.name,
        }))

        # Create the Azure OpenAI Realtime model
        realtime_llm = openai.realtime.RealtimeModel.with_azure(
            azure_deployment=azure_deployment,
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
            voice="alloy",
        )

        # Create the agent session with VAD for voice activity detection
        session = AgentSession(
            llm=realtime_llm,
            vad=silero.VAD.load(),
        )

        # Subscribe to session_usage_updated for token tracking
        @session.on("session_usage_updated")
        def _on_usage_updated(ev) -> None:
            """Capture cumulative token usage from session_usage_updated events."""
            global _total_input_tokens, _total_output_tokens

            # ev.usage is AgentSessionUsage with model_usage list
            total_in = 0
            total_out = 0
            for model_usage in ev.usage.model_usage:
                if hasattr(model_usage, "input_tokens"):
                    total_in += model_usage.input_tokens
                if hasattr(model_usage, "output_tokens"):
                    total_out += model_usage.output_tokens

            _total_input_tokens = total_in
            _total_output_tokens = total_out

            emit_event(
                "response.done",
                direction="inbound",
                payload=json.dumps({
                    "input_tokens": total_in,
                    "output_tokens": total_out,
                }),
            )

        # Subscribe to user and agent state changes for debug logging
        @session.on("user_state_changed")
        def _on_user_state(ev) -> None:
            emit_event(
                f"user.{ev.new_state}",
                direction="inbound",
                payload=json.dumps({
                    "old_state": ev.old_state,
                    "new_state": ev.new_state,
                }),
            )

        @session.on("agent_state_changed")
        def _on_agent_state(ev) -> None:
            emit_event(
                f"agent.{ev.new_state}",
                direction="internal",
                payload=json.dumps({
                    "old_state": ev.old_state,
                    "new_state": ev.new_state,
                }),
            )

        # Subscribe to errors
        @session.on("error")
        def _on_error(ev) -> None:
            emit_error(
                "Agent session error event",
                details=str(ev) if ev else "",
            )

        emit_event("session.started")

        # Start the agent session - this blocks until the session ends
        await session.start(agent=VoiceAssistant(), room=ctx.room)

        emit_event("agent.started", payload=json.dumps({
            "room_name": ctx.room.name,
        }))

    except Exception as exc:
        emit_error("Agent session error", details=str(exc))
    finally:
        # Report accumulated usage when the session ends
        await report_usage()
        emit_event("session.ended")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Validate required environment variables before starting
    required_vars = [
        "AZURE_ENDPOINT",
        "AZURE_API_KEY",
        "LIVEKIT_URL",
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "ROOM_NAME",
        "SESSION_ID",
    ]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        emit_error(
            "Missing required environment variables",
            details=f"Missing: {', '.join(missing)}",
        )
        sys.exit(1)

    # Run the agent using livekit-agents CLI framework
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
