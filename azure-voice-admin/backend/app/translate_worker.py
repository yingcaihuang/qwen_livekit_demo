"""Translate Worker: standalone script spawned per Translate Session.

This script is executed as a subprocess by the Process Manager. It:
1. Reads Azure credentials and LiveKit room info from environment variables.
2. Connects to the specified LiveKit room using livekit-agents.
3. Uses Azure OpenAI Realtime API for real-time audio translation.
4. Outputs translated audio to the room and emits text transcript events.
5. On session end, HTTP POSTs token usage to the management server.

Environment variables (all required unless noted):
    AZURE_ENDPOINT      - Azure OpenAI endpoint URL
    AZURE_API_KEY       - Azure OpenAI API key
    AZURE_DEPLOYMENT    - Azure OpenAI deployment name (e.g. gpt-realtime-translate)
    LIVEKIT_URL         - LiveKit server WebSocket URL
    LIVEKIT_API_KEY     - LiveKit API key
    LIVEKIT_API_SECRET  - LiveKit API secret
    ROOM_NAME           - LiveKit room name to join
    SESSION_ID          - Session ID for usage reporting
    REPORT_URL          - URL to POST token usage
    TARGET_LANGUAGE     - ISO 639-1 target language code (default: en)
"""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime

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
# Structured stderr logging helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def emit_event(
    event_type: str,
    direction: str = "internal",
    payload: str = "{}",
) -> None:
    """Write a structured JSON event line to stderr."""
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
    print(line, file=sys.stderr, flush=True)


def emit_error(message: str, details: str = "") -> None:
    """Write a structured error JSON line to stderr."""
    line = json.dumps(
        {
            "type": "error",
            "timestamp": _now_iso(),
            "message": message,
            "details": details,
        },
        ensure_ascii=False,
    )
    print(line, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Token usage tracking and reporting
# ---------------------------------------------------------------------------

_total_input_tokens: int = 0
_total_output_tokens: int = 0


async def report_usage() -> None:
    """POST accumulated token usage to the management server (safety net)."""
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


async def _report_usage_delta(input_tokens: int, output_tokens: int) -> None:
    """POST incremental token usage to the management server."""
    report_url = os.environ.get("REPORT_URL", "")
    if not report_url:
        return
    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                report_url,
                json={"input_tokens": input_tokens, "output_tokens": output_tokens},
                timeout=aiohttp.ClientTimeout(total=5),
            ):
                pass  # Fire and forget
    except Exception:
        pass  # Non-critical, don't crash the agent


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------


class TranslateAssistant(Agent):
    """Real-time translation agent — relays translated audio and text."""

    def __init__(self, target_language: str) -> None:
        super().__init__(
            instructions=(
                f"You are a real-time translator. Translate all spoken audio input into {target_language}. "
                f"Output only the translation, do not add explanations or commentary."
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
    azure_deployment = os.environ.get("AZURE_DEPLOYMENT", "gpt-realtime-translate")
    target_language = os.environ.get("TARGET_LANGUAGE", "en")

    if not azure_endpoint or not azure_api_key:
        emit_error(
            "Missing Azure credentials",
            details="AZURE_ENDPOINT and AZURE_API_KEY must be set",
        )
        return

    emit_event(
        "session.starting",
        payload=json.dumps(
            {
                "room": ctx.room.name if ctx.room else "unknown",
                "azure_endpoint": azure_endpoint,
                "azure_deployment": azure_deployment,
                "target_language": target_language,
            }
        ),
    )

    try:
        # Connect to the LiveKit room
        await ctx.connect()

        emit_event(
            "room.connected",
            payload=json.dumps(
                {
                    "room_name": ctx.room.name,
                }
            ),
        )

        # Create the Azure OpenAI Realtime model (no voice param — let Azure pick)
        realtime_llm = openai.realtime.RealtimeModel.with_azure(
            azure_deployment=azure_deployment,
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
        )

        # Create the agent session with VAD for voice activity detection
        session = AgentSession(
            llm=realtime_llm,
            vad=silero.VAD.load(),
        )

        # Subscribe to session_usage_updated for token tracking
        @session.on("session_usage_updated")
        def _on_usage_updated(ev) -> None:
            """Report token usage on each update (incremental)."""
            global _total_input_tokens, _total_output_tokens

            new_input = 0
            new_output = 0
            for model_usage in ev.usage.model_usage:
                if hasattr(model_usage, "input_tokens"):
                    new_input += model_usage.input_tokens
                if hasattr(model_usage, "output_tokens"):
                    new_output += model_usage.output_tokens

            # Calculate delta (new tokens since last report)
            delta_input = new_input - _total_input_tokens
            delta_output = new_output - _total_output_tokens

            _total_input_tokens = new_input
            _total_output_tokens = new_output

            # Report delta immediately (non-blocking)
            if delta_input > 0 or delta_output > 0:
                asyncio.get_event_loop().create_task(_report_usage_delta(delta_input, delta_output))

            emit_event(
                "response.done",
                direction="inbound",
                payload=json.dumps(
                    {
                        "input_tokens": new_input,
                        "output_tokens": new_output,
                    }
                ),
            )

        # Subscribe to conversation items for transcript logging
        @session.on("conversation_item_added")
        def _on_conversation_item(ev) -> None:
            """Capture conversation transcripts (user input and translated output)."""
            item = getattr(ev, "item", None)
            role = getattr(item, "role", None) if item else None
            text = getattr(item, "text_content", None) if item else None
            if role and text:
                emit_event(
                    "message.added",
                    direction="inbound" if role == "user" else "outbound",
                    payload=json.dumps({"role": role, "text": text}),
                )

        # Subscribe to errors
        @session.on("error")
        def _on_error(ev) -> None:
            emit_error(
                "Translate session error event",
                details=str(ev) if ev else "",
            )

        emit_event("session.started")

        # Start the agent session - this blocks until the session ends
        await session.start(agent=TranslateAssistant(target_language), room=ctx.room)

        emit_event(
            "agent.started",
            payload=json.dumps(
                {
                    "room_name": ctx.room.name,
                    "target_language": target_language,
                }
            ),
        )

    except Exception as exc:
        emit_error("Translate session error", details=str(exc))
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
