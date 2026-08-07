"""Tests for ProcessManager service."""

import asyncio
import sys
from unittest.mock import patch

import pytest

from app.services.process_manager import ProcessManager


@pytest.fixture
def pm():
    """Create a fresh ProcessManager instance (reset singleton)."""
    # Reset singleton for isolation
    ProcessManager._instance = None
    manager = ProcessManager()
    yield manager
    # Cleanup: terminate any leftover processes
    for sid in list(manager._processes.keys()):
        proc = manager._processes[sid]
        if proc.returncode is None:
            proc.kill()
    ProcessManager._instance = None


class TestProcessManagerSingleton:
    """Test singleton behavior."""

    def test_singleton_returns_same_instance(self):
        ProcessManager._instance = None
        a = ProcessManager()
        b = ProcessManager()
        assert a is b
        ProcessManager._instance = None


class TestIsAgentRunning:
    """Test is_agent_running method."""

    def test_returns_false_for_unknown_session(self, pm):
        assert pm.is_agent_running("nonexistent") is False

    @pytest.mark.asyncio
    async def test_returns_true_for_running_process(self, pm):
        # Spawn a simple long-running subprocess
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        pm._processes["test-session"] = proc
        assert pm.is_agent_running("test-session") is True
        proc.kill()
        await proc.wait()

    @pytest.mark.asyncio
    async def test_returns_false_for_exited_process(self, pm):
        # Spawn a subprocess that exits immediately
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "pass",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        pm._processes["exited-session"] = proc
        assert pm.is_agent_running("exited-session") is False


class TestGetActiveSessions:
    """Test get_active_sessions method."""

    def test_empty_when_no_processes(self, pm):
        assert pm.get_active_sessions() == []

    @pytest.mark.asyncio
    async def test_returns_only_running_sessions(self, pm):
        # One running
        running_proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # One exited
        exited_proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "pass",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await exited_proc.wait()

        pm._processes["running"] = running_proc
        pm._processes["exited"] = exited_proc

        active = pm.get_active_sessions()
        assert "running" in active
        assert "exited" not in active

        running_proc.kill()
        await running_proc.wait()


class TestTerminateAgent:
    """Test terminate_agent method."""

    @pytest.mark.asyncio
    async def test_terminate_nonexistent_session(self, pm):
        # Should not raise
        await pm.terminate_agent("no-such-session")

    @pytest.mark.asyncio
    async def test_terminate_already_exited(self, pm):
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "pass",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        pm._processes["done-session"] = proc

        await pm.terminate_agent("done-session")
        assert "done-session" not in pm._processes

    @pytest.mark.asyncio
    async def test_terminate_running_process_gracefully(self, pm):
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        pm._processes["active-session"] = proc

        await pm.terminate_agent("active-session")
        assert "active-session" not in pm._processes
        assert proc.returncode is not None


class TestSpawnAgent:
    """Test spawn_agent method."""

    @pytest.mark.asyncio
    async def test_spawn_creates_process(self, pm):
        """Test that spawn_agent creates a subprocess entry in _processes."""
        instance_config = {
            "endpoint": "https://test.openai.azure.com",
            "api_key": "test-key-123",
            "deployment": "gpt-realtime-2.1",
        }

        # We'll patch create_subprocess_exec to avoid actually running agent_worker.py
        mock_proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await pm.spawn_agent("spawn-test", instance_config, "room-12345")

        assert "spawn-test" in pm._processes
        assert pm.is_agent_running("spawn-test") is True

        # Cleanup
        mock_proc.kill()
        await mock_proc.wait()

    @pytest.mark.asyncio
    async def test_spawn_does_not_duplicate_running_agent(self, pm):
        """If an agent is already running for a session, spawn should not create a new one."""
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        pm._processes["dup-session"] = proc

        instance_config = {
            "endpoint": "https://test.openai.azure.com",
            "api_key": "test-key",
            "deployment": "gpt-realtime-2.1",
        }

        await pm.spawn_agent("dup-session", instance_config, "room-dup")

        # Should still be the same process
        assert pm._processes["dup-session"] is proc

        proc.kill()
        await proc.wait()


class TestGetStdoutReader:
    """Test get_stdout_reader method."""

    def test_returns_none_for_unknown_session(self, pm):
        assert pm.get_stdout_reader("unknown") is None

    @pytest.mark.asyncio
    async def test_returns_stderr_for_running_process(self, pm):
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        pm._processes["stdout-session"] = proc

        reader = pm.get_stdout_reader("stdout-session")
        assert reader is not None
        assert reader is proc.stderr

        proc.kill()
        await proc.wait()
