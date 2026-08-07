"""Process Manager: manages Agent Worker subprocess lifecycle.

Responsible for spawning, monitoring, and terminating Agent Worker
subprocesses—one per active Voice Session.
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Resolve the path to agent_worker.py relative to the backend directory
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_AGENT_WORKER_PATH = Path(__file__).resolve().parent.parent / "agent_worker.py"


class ProcessManager:
    """Singleton manager for Agent Worker subprocesses.

    Maintains a mapping of session_id → asyncio.subprocess.Process and
    provides methods to spawn, terminate, and query running agents.
    """

    _instance: Optional["ProcessManager"] = None

    def __new__(cls) -> "ProcessManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._processes = {}
        return cls._instance

    def __init__(self) -> None:
        # Avoid re-initializing on subsequent calls
        if not hasattr(self, "_processes"):
            self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def spawn_agent(
        self,
        session_id: str,
        instance_config: dict,
        room_name: str,
    ) -> None:
        """Spawn an Agent Worker subprocess for the given session.

        Args:
            session_id: Unique identifier of the voice session.
            instance_config: Dict containing Azure credentials:
                - endpoint: Azure OpenAI endpoint URL
                - api_key: Azure OpenAI API key
                - deployment: Azure OpenAI deployment name
            room_name: The LiveKit room name for the agent to join.

        The subprocess inherits the current process environment enriched with
        session-specific variables (Azure creds, LiveKit config, room/session info).
        """
        if session_id in self._processes:
            existing = self._processes[session_id]
            if existing.returncode is None:
                logger.warning(
                    "Agent for session %s is already running (pid=%s)",
                    session_id,
                    existing.pid,
                )
                return

        # Build environment variables for the subprocess
        port = os.environ.get("PORT", "8090")
        env = os.environ.copy()
        env.update(
            {
                "AZURE_ENDPOINT": instance_config.get("endpoint", ""),
                "AZURE_API_KEY": instance_config.get("api_key", ""),
                "AZURE_DEPLOYMENT": instance_config.get("deployment", ""),
                "LIVEKIT_URL": os.environ.get("LIVEKIT_URL", "ws://localhost:7880"),
                "LIVEKIT_API_KEY": os.environ.get("LIVEKIT_API_KEY", ""),
                "LIVEKIT_API_SECRET": os.environ.get("LIVEKIT_API_SECRET", ""),
                "ROOM_NAME": room_name,
                "SESSION_ID": session_id,
                "REPORT_URL": f"http://localhost:{port}/internal/sessions/{session_id}/usage",
            }
        )

        # Resolve agent_worker.py path
        agent_script = str(_AGENT_WORKER_PATH)

        logger.info(
            "Spawning agent for session %s in room %s (script=%s)",
            session_id,
            room_name,
            agent_script,
        )

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            agent_script,
            "connect",
            "--room",
            room_name,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(_BACKEND_DIR),
        )

        self._processes[session_id] = process
        logger.info(
            "Agent spawned for session %s (pid=%s)", session_id, process.pid
        )

    async def terminate_agent(self, session_id: str) -> None:
        """Terminate the Agent Worker subprocess for the given session.

        Sends SIGTERM first, waits up to 5 seconds, then sends SIGKILL
        if the process has not exited. Removes the process from the internal map.

        Args:
            session_id: The session whose agent should be terminated.
        """
        process = self._processes.get(session_id)
        if process is None:
            logger.warning(
                "No agent process found for session %s", session_id
            )
            return

        if process.returncode is not None:
            # Already terminated
            logger.info(
                "Agent for session %s already exited (returncode=%s)",
                session_id,
                process.returncode,
            )
            self._processes.pop(session_id, None)
            return

        # Send SIGTERM
        logger.info(
            "Sending SIGTERM to agent for session %s (pid=%s)",
            session_id,
            process.pid,
        )
        try:
            process.terminate()
        except ProcessLookupError:
            self._processes.pop(session_id, None)
            return

        # Wait up to 5 seconds for graceful shutdown
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
            logger.info(
                "Agent for session %s terminated gracefully (returncode=%s)",
                session_id,
                process.returncode,
            )
        except asyncio.TimeoutError:
            # Force kill
            logger.warning(
                "Agent for session %s did not exit after SIGTERM, sending SIGKILL (pid=%s)",
                session_id,
                process.pid,
            )
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass

        self._processes.pop(session_id, None)

    def is_agent_running(self, session_id: str) -> bool:
        """Check whether the agent for the given session is still running.

        Returns True if the subprocess exists and has not exited (returncode is None).
        """
        process = self._processes.get(session_id)
        if process is None:
            return False
        return process.returncode is None

    def get_active_sessions(self) -> list[str]:
        """Return a list of session_ids whose agents are currently running."""
        return [
            sid
            for sid, proc in self._processes.items()
            if proc.returncode is None
        ]

    def get_stdout_reader(
        self, session_id: str
    ) -> Optional[asyncio.StreamReader]:
        """Return the stdout StreamReader of the agent process for log broadcasting.

        Returns None if no process exists for the session or if stdout is unavailable.
        """
        process = self._processes.get(session_id)
        if process is None:
            return None
        return process.stdout


# Module-level singleton instance
process_manager = ProcessManager()
