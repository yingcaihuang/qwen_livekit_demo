"""Integration smoke tests for the Chat SSE endpoint (POST /api/chat/completions).

Azure is not contacted: ``aiohttp.ClientSession.post`` is patched to return a
fake streaming response so the endpoint's wiring, SSE framing, lazy session
creation, and message/usage persistence can be verified end-to-end.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Set temp DB path before imports
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")

import app.database as db_mod  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    """Use a fresh temp database for each test."""
    test_db = str(tmp_path / "test.db")
    db_mod.DB_PATH = test_db
    from app.database import init_db

    await init_db()
    yield
    if Path(test_db).exists():
        Path(test_db).unlink()


@pytest.fixture
async def client():
    """Provide an async HTTP client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def chat_instance_id(client):
    """Create a chat instance and return its ID."""
    resp = await client.post(
        "/api/instances",
        json={
            "name": "chat-instance",
            "endpoint": "https://test.openai.azure.com",
            "api_key": "sk-test-key-12345",
            "deployment": "gpt-5.5",
            "type": "chat",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture
async def multi_deployment_instance_id(client):
    """Create a chat instance sharing one endpoint across several deployments."""
    resp = await client.post(
        "/api/instances",
        json={
            "name": "multi-chat-instance",
            "endpoint": "https://test.openai.azure.com",
            "api_key": "sk-test-key-12345",
            "deployment": "gpt-5.5, gpt-4o, gpt-4o-mini",
            "type": "chat",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class _FakeContent:
    """Async-iterable stand-in for ``aiohttp`` response ``.content``."""

    def __init__(self, lines: list[bytes]):
        self._lines = lines

    def __aiter__(self):
        async def gen():
            for line in self._lines:
                yield line

        return gen()


class _FakeResponse:
    """Minimal async context manager mimicking an aiohttp streaming response."""

    def __init__(self, status: int, lines: list[bytes]):
        self.status = status
        self.content = _FakeContent(lines)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def text(self):
        return "".join(line.decode() for line in self.content._lines)


class _FakeSession:
    """Fake ``aiohttp.ClientSession`` that yields a preset streaming response."""

    def __init__(self, lines: list[bytes], status: int = 200):
        self._lines = lines
        self._status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, *args, **kwargs):
        return _FakeResponse(self._status, self._lines)


class _CapturingSession(_FakeSession):
    """Fake session that records the outgoing request (url/json/headers).

    Used to assert exactly what the endpoint forwards to Azure without ever
    contacting the network. Captured calls are appended to ``self.calls``.
    """

    def __init__(self, lines: list[bytes], status: int = 200):
        super().__init__(lines, status)
        self.calls: list[dict] = []

    def post(self, *args, **kwargs):
        self.calls.append(
            {
                "url": args[0] if args else kwargs.get("url"),
                "json": kwargs.get("json"),
                "headers": kwargs.get("headers"),
            }
        )
        return _FakeResponse(self._status, self._lines)


def _capture(monkeypatch, session: _CapturingSession) -> _CapturingSession:
    """Patch ``aiohttp.ClientSession`` to return ``session`` and return it.

    A single shared instance is returned for every ``ClientSession(...)`` call
    so the recorded ``calls`` survive after the request completes.
    """
    import app.services.chat_service as chat_svc

    monkeypatch.setattr(chat_svc.aiohttp, "ClientSession", lambda *a, **k: session)
    return session


def _sse_chunks() -> list[bytes]:
    """Two Responses text deltas, a completed event with usage, then [DONE]."""
    return [
        b'data: {"type":"response.output_text.delta","delta":"Hello"}\n',
        b'data: {"type":"response.output_text.delta","delta":" world"}\n',
        b'data: {"type":"response.completed","response":{"usage":'
        b'{"input_tokens":7,"output_tokens":3}}}\n',
        b"data: [DONE]\n",
    ]


def _sse_chunks_no_usage() -> list[bytes]:
    """Two Responses text deltas followed by [DONE] but no completed/usage (Req 3.6)."""
    return [
        b'data: {"type":"response.output_text.delta","delta":"Hi"}\n',
        b'data: {"type":"response.output_text.delta","delta":" there"}\n',
        b"data: [DONE]\n",
    ]


def _parse_sse(body: str) -> list[dict]:
    """Parse an SSE body into a list of decoded JSON event payloads."""
    events = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:") :].strip()))
    return events


class TestChatCompletions:
    """Tests for POST /api/chat/completions."""

    async def test_stream_creates_session_and_persists(self, client, chat_instance_id, monkeypatch):
        """Streaming a first turn emits session/delta/done and persists the turn."""
        import app.services.chat_service as chat_svc

        monkeypatch.setattr(
            chat_svc.aiohttp,
            "ClientSession",
            lambda *a, **k: _FakeSession(_sse_chunks()),
        )

        resp = await client.post(
            "/api/chat/completions",
            json={
                "instance_id": chat_instance_id,
                "messages": [{"role": "user", "content": "hi"}],
                "temperature": 0.7,
            },
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse(resp.text)
        types = [e["type"] for e in events]
        assert types[0] == "session"
        session_id = events[0]["session_id"]
        assert "delta" in types
        # Assembled assistant content from the two deltas.
        deltas = "".join(e["content"] for e in events if e["type"] == "delta")
        assert deltas == "Hello world"
        done = events[-1]
        assert done["type"] == "done"
        assert done["usage"] == {"input_tokens": 7, "output_tokens": 3}
        # The done event carries (non-persisted) performance timing.
        timing = done["timing"]
        assert isinstance(timing["total_ms"], int) and timing["total_ms"] >= 0
        # Two content deltas were streamed, so ttfb was recorded.
        assert isinstance(timing["ttfb_ms"], int) and timing["ttfb_ms"] >= 0
        assert timing["started_at"]
        assert timing["ended_at"]

        # Verify persistence: messages + cumulative usage on the session.
        msgs_resp = await client.get(f"/api/sessions/{session_id}/messages")
        assert msgs_resp.status_code == 200
        msgs = msgs_resp.json()
        roles = [m["role"] for m in msgs]
        assert roles == ["user", "assistant"]
        assert msgs[1]["content"] == "Hello world"

        detail = (await client.get(f"/api/sessions/{session_id}")).json()
        assert detail["input_tokens"] == 7
        assert detail["output_tokens"] == 3

    async def test_error_event_on_azure_failure(self, client, chat_instance_id, monkeypatch):
        """A non-200 Azure response is surfaced as an SSE error event."""
        import app.services.chat_service as chat_svc

        monkeypatch.setattr(
            chat_svc.aiohttp,
            "ClientSession",
            lambda *a, **k: _FakeSession([b"boom"], status=401),
        )

        resp = await client.post(
            "/api/chat/completions",
            json={
                "instance_id": chat_instance_id,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        # session event first (lazily created), then an error event.
        assert any(e["type"] == "error" for e in events)

    async def test_unknown_instance_emits_error(self, client, monkeypatch):
        """An unknown instance id yields an error event, not a crash."""
        resp = await client.post(
            "/api/chat/completions",
            json={
                "instance_id": "does-not-exist",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        assert events and events[0]["type"] == "error"

    async def test_delete_chat_session_removes_messages(
        self, client, chat_instance_id, monkeypatch
    ):
        """Deleting a chat session cascades to its persisted messages (Req 3.5)."""
        import aiosqlite

        import app.services.chat_service as chat_svc

        monkeypatch.setattr(
            chat_svc.aiohttp,
            "ClientSession",
            lambda *a, **k: _FakeSession(_sse_chunks()),
        )

        resp = await client.post(
            "/api/chat/completions",
            json={
                "instance_id": chat_instance_id,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        session_id = _parse_sse(resp.text)[0]["session_id"]

        # Messages exist before deletion.
        async with aiosqlite.connect(db_mod.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM session_messages WHERE session_id = ?",
                (session_id,),
            )
            assert (await cursor.fetchone())[0] == 2

        del_resp = await client.delete(f"/api/sessions/{session_id}")
        assert del_resp.status_code == 204

        # Messages are gone after deletion.
        async with aiosqlite.connect(db_mod.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM session_messages WHERE session_id = ?",
                (session_id,),
            )
            assert (await cursor.fetchone())[0] == 0


class TestChatRequestForwarding:
    """Assert what the endpoint forwards to Azure (request-body contract).

    These extend TestChatCompletions (which covers SSE framing / persistence /
    errors) with coverage of multi-turn context, system-prompt injection,
    session reuse, missing-usage handling, and parameter sanitization.
    Covers Requirements 2.1, 2.2, 3.1, 3.2, 3.3, 9.2, 10.3.
    """

    async def test_multi_turn_context_forwarded_with_system_prompt(
        self, client, chat_instance_id, monkeypatch
    ):
        """Accumulated history + system_prompt are forwarded to Azure (Req 2.1/2.2/3.3).

        The system prompt MUST travel in the Responses ``instructions`` field,
        and ``input`` MUST contain every prior turn in order.
        """
        session = _capture(monkeypatch, _CapturingSession(_sse_chunks()))

        history = [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "And times 3?"},
        ]
        resp = await client.post(
            "/api/chat/completions",
            json={
                "instance_id": chat_instance_id,
                "messages": history,
                "system_prompt": "You are a math tutor.",
            },
        )
        assert resp.status_code == 200

        assert len(session.calls) == 1
        body = session.calls[0]["json"]
        # System prompt travels in `instructions`, NOT as a message in `input`.
        assert body["instructions"] == "You are a math tutor."
        # Full multi-turn context preserved in order in `input` (no system msg).
        assert body["input"] == history
        # Streaming is requested; no chat-completions-only keys are present.
        assert body["stream"] is True
        assert "messages" not in body
        assert "stream_options" not in body
        # api-key travels in the header, never in the forwarded body.
        assert session.calls[0]["headers"]["api-key"] == "sk-test-key-12345"
        assert "api_key" not in body and "api-key" not in body

    async def test_no_system_prompt_means_no_system_message(
        self, client, chat_instance_id, monkeypatch
    ):
        """Without a system_prompt, no system message is injected."""
        session = _capture(monkeypatch, _CapturingSession(_sse_chunks()))

        resp = await client.post(
            "/api/chat/completions",
            json={
                "instance_id": chat_instance_id,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert resp.status_code == 200
        body = session.calls[0]["json"]
        # No system_prompt => `instructions` is absent and `input` is verbatim.
        assert "instructions" not in body
        assert body["input"] == [{"role": "user", "content": "hi"}]

    async def test_reuse_existing_session_appends_no_duplicate_session(
        self, client, chat_instance_id, monkeypatch
    ):
        """Reusing a session_id continues the same session (Req 3.1/3.2).

        A second turn passed with the existing session_id emits NO ``session``
        event and appends its messages to the same session rather than
        creating a new one.
        """
        # First turn: lazily creates the session.
        _capture(monkeypatch, _CapturingSession(_sse_chunks()))
        first = await client.post(
            "/api/chat/completions",
            json={
                "instance_id": chat_instance_id,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        first_events = _parse_sse(first.text)
        session_id = first_events[0]["session_id"]
        assert first_events[0]["type"] == "session"

        # Second turn: reuse the session_id explicitly.
        _capture(monkeypatch, _CapturingSession(_sse_chunks()))
        second = await client.post(
            "/api/chat/completions",
            json={
                "instance_id": chat_instance_id,
                "session_id": session_id,
                "messages": [
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "Hello world"},
                    {"role": "user", "content": "again"},
                ],
            },
        )
        second_events = _parse_sse(second.text)
        # No session event on reuse — the session already exists.
        assert all(e["type"] != "session" for e in second_events)

        # Both turns' messages accumulate under the same session (2 + 2 = 4).
        msgs = (await client.get(f"/api/sessions/{session_id}/messages")).json()
        assert [m["role"] for m in msgs] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]

        # Token usage accumulates across the two turns (7+7 / 3+3).
        detail = (await client.get(f"/api/sessions/{session_id}")).json()
        assert detail["input_tokens"] == 14
        assert detail["output_tokens"] == 6

    async def test_missing_usage_persists_zero_but_keeps_content(
        self, client, chat_instance_id, monkeypatch
    ):
        """No usage from Azure => usage 0 but assistant content still saved (Req 3.6)."""
        _capture(monkeypatch, _CapturingSession(_sse_chunks_no_usage()))

        resp = await client.post(
            "/api/chat/completions",
            json={
                "instance_id": chat_instance_id,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        done = events[-1]
        assert done["type"] == "done"
        assert done["usage"] == {"input_tokens": 0, "output_tokens": 0}

        session_id = events[0]["session_id"]
        msgs = (await client.get(f"/api/sessions/{session_id}/messages")).json()
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        # Content is preserved even though usage was absent.
        assert msgs[1]["content"] == "Hi there"

        detail = (await client.get(f"/api/sessions/{session_id}")).json()
        assert detail["input_tokens"] == 0
        assert detail["output_tokens"] == 0

    async def test_temperature_clamped_and_max_tokens_sanitized(
        self, client, chat_instance_id, monkeypatch
    ):
        """Out-of-range temperature is clamped and non-positive max_tokens coerced.

        temperature 5.0 -> 2.0 (clamped to [0,2]); max_tokens 0 -> 1 (positive
        integer). The sanitized values MUST appear in the forwarded body.
        """
        session = _capture(monkeypatch, _CapturingSession(_sse_chunks()))

        resp = await client.post(
            "/api/chat/completions",
            json={
                "instance_id": chat_instance_id,
                "messages": [{"role": "user", "content": "hi"}],
                "temperature": 5.0,
                "max_tokens": 0,
            },
        )
        assert resp.status_code == 200
        body = session.calls[0]["json"]
        assert body["temperature"] == 2.0
        # Responses uses `max_output_tokens`; chat-completions `max_tokens` is absent.
        assert body["max_output_tokens"] == 1
        assert "max_tokens" not in body

    async def test_temperature_below_range_clamped_to_zero(
        self, client, chat_instance_id, monkeypatch
    ):
        """A negative temperature is clamped up to 0.0."""
        session = _capture(monkeypatch, _CapturingSession(_sse_chunks()))

        resp = await client.post(
            "/api/chat/completions",
            json={
                "instance_id": chat_instance_id,
                "messages": [{"role": "user", "content": "hi"}],
                "temperature": -3.0,
            },
        )
        assert resp.status_code == 200
        body = session.calls[0]["json"]
        assert body["temperature"] == 0.0
        # max_tokens omitted from the request => no max_output_tokens in the body.
        assert "max_output_tokens" not in body
        assert "max_tokens" not in body


class TestChatModelSelection:
    """Per-request model selection from an instance's deployment list.

    A chat instance may list several deployments (comma-separated) sharing one
    endpoint + api key. The frontend sends ``model`` to pick one; only a model
    that belongs to THIS instance's list is honored, otherwise the first
    configured deployment is used. The model travels in the request body only
    (the URL never encodes the deployment).
    """

    async def test_selected_model_forwarded_when_in_list(
        self, client, multi_deployment_instance_id, monkeypatch
    ):
        """A valid model from the instance's list is forwarded in body['model']."""
        session = _capture(monkeypatch, _CapturingSession(_sse_chunks()))

        resp = await client.post(
            "/api/chat/completions",
            json={
                "instance_id": multi_deployment_instance_id,
                "messages": [{"role": "user", "content": "hi"}],
                "model": "gpt-4o",
            },
        )
        assert resp.status_code == 200
        assert session.calls[0]["json"]["model"] == "gpt-4o"

    async def test_no_model_uses_first_deployment(
        self, client, multi_deployment_instance_id, monkeypatch
    ):
        """With no model provided, the first deployment in the list is used."""
        session = _capture(monkeypatch, _CapturingSession(_sse_chunks()))

        resp = await client.post(
            "/api/chat/completions",
            json={
                "instance_id": multi_deployment_instance_id,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert resp.status_code == 200
        assert session.calls[0]["json"]["model"] == "gpt-5.5"

    async def test_invalid_model_falls_back_to_first(
        self, client, multi_deployment_instance_id, monkeypatch
    ):
        """A model not in the instance's list is rejected and falls back to the first.

        An arbitrary/unauthorized model value is never forwarded to Azure.
        """
        session = _capture(monkeypatch, _CapturingSession(_sse_chunks()))

        resp = await client.post(
            "/api/chat/completions",
            json={
                "instance_id": multi_deployment_instance_id,
                "messages": [{"role": "user", "content": "hi"}],
                "model": "evil-model",
            },
        )
        assert resp.status_code == 200
        assert session.calls[0]["json"]["model"] == "gpt-5.5"


class TestParseDeployments:
    """Unit tests for ChatService._parse_deployments."""

    def test_parse_deployments_strips_dedupes_and_drops_empties(self):
        from app.services.chat_service import ChatService

        assert ChatService._parse_deployments("gpt-5.5, gpt-4o ,, gpt-4o, gpt-4o-mini") == [
            "gpt-5.5",
            "gpt-4o",
            "gpt-4o-mini",
        ]

    def test_parse_deployments_single_value(self):
        from app.services.chat_service import ChatService

        assert ChatService._parse_deployments("gpt-5.5") == ["gpt-5.5"]

    def test_parse_deployments_empty_string(self):
        from app.services.chat_service import ChatService

        assert ChatService._parse_deployments("") == []
