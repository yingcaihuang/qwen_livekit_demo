"""Bug condition exploration test: Local User Force Password Change Bypass.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

Property 1: Bug Condition — Local User Force Password Change Bypass

CRITICAL: This test MUST FAIL on unfixed code — failure confirms the bug exists.
DO NOT fix the test or the code when it fails.

Goal: Surface counterexamples that demonstrate:
- /api/auth/me returns must_change_password=false for user with DB value true
- /api/auth/me has no auth_source field in response
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient

# Set temp DB path before imports
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")
os.environ["LIVEKIT_API_KEY"] = "devkey"
os.environ["LIVEKIT_API_SECRET"] = "secret-that-is-at-least-32-chars-long!"
os.environ["LIVEKIT_URL"] = "ws://localhost:7880"

import app.database as db_mod  # noqa: E402
from app.main import app  # noqa: E402
from app.services import auth_service  # noqa: E402


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
    """Provide an async HTTP client for the FastAPI app with TESTING disabled."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def local_user_must_change(tmp_path):
    """Create a local user with must_change_password=true and return (user_id, session_token)."""
    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        user_id = "test-local-user-001"
        password_hash = auth_service.hash_password("OldPassword123!")
        # Insert user with must_change_password=1 and auth_source='local'
        await db.execute(
            "INSERT INTO users (id, username, auth_source, password_hash, is_active, must_change_password) "
            "VALUES (?, ?, 'local', ?, 1, 1)",
            (user_id, "force_change_user", password_hash),
        )
        # Assign a role
        await db.execute(
            "INSERT INTO user_roles (user_id, role) VALUES (?, 'operator')",
            (user_id,),
        )
        # Create a session for this user
        session_token, csrf_token = await auth_service.create_session(db, user_id)
        await db.commit()
        return user_id, session_token


class TestBugConditionMeEndpoint:
    """Tests that /api/auth/me fails to return correct must_change_password and auth_source.

    These tests demonstrate the bug exists on unfixed code.
    """

    async def test_me_returns_must_change_password_true(self, client, local_user_must_change):
        """EXPECTED TO FAIL: /api/auth/me should return must_change_password=true for user with DB flag set.

        Bug: MeResponse has must_change_password default=False, and me() does not pass the
        actual DB value, so it always returns false.
        """
        user_id, session_token = local_user_must_change

        # Disable TESTING bypass so real auth flow is exercised
        with patch.dict(os.environ, {"TESTING": "0"}):
            response = await client.get(
                "/api/auth/me",
                cookies={auth_service.SESSION_COOKIE_NAME: session_token},
            )

        assert response.status_code == 200
        data = response.json()
        # This assertion will FAIL on unfixed code because me() returns
        # must_change_password=False (MeResponse default) regardless of DB value
        assert data["must_change_password"] is True, (
            f"COUNTEREXAMPLE: /api/auth/me returns must_change_password={data.get('must_change_password')} "
            f"for user with DB must_change_password=true. "
            f"Root cause: MeResponse default value is False, me() never queries/passes the real value."
        )

    async def test_me_returns_auth_source_field(self, client, local_user_must_change):
        """EXPECTED TO FAIL: /api/auth/me should include auth_source field in response.

        Bug: MeResponse model and me() endpoint do not include auth_source at all.
        """
        user_id, session_token = local_user_must_change

        with patch.dict(os.environ, {"TESTING": "0"}):
            response = await client.get(
                "/api/auth/me",
                cookies={auth_service.SESSION_COOKIE_NAME: session_token},
            )

        assert response.status_code == 200
        data = response.json()
        # This assertion will FAIL because auth_source is not in MeResponse
        assert "auth_source" in data, (
            f"COUNTEREXAMPLE: /api/auth/me response fields are {list(data.keys())}. "
            f"'auth_source' field is missing. "
            f"Root cause: MeResponse model has no auth_source field, me() does not return it."
        )

    async def test_me_auth_source_is_local(self, client, local_user_must_change):
        """EXPECTED TO FAIL: /api/auth/me should return auth_source='local' for local users.

        Bug: auth_source field does not exist in response.
        """
        user_id, session_token = local_user_must_change

        with patch.dict(os.environ, {"TESTING": "0"}):
            response = await client.get(
                "/api/auth/me",
                cookies={auth_service.SESSION_COOKIE_NAME: session_token},
            )

        assert response.status_code == 200
        data = response.json()
        # This will FAIL because auth_source is not in the response at all
        assert data.get("auth_source") == "local", (
            f"COUNTEREXAMPLE: /api/auth/me returns auth_source={data.get('auth_source', '<MISSING>')} "
            f"for local user. Expected 'local'. "
            f"Root cause: CurrentUser dataclass lacks auth_source, get_current_user() doesn't query it."
        )
