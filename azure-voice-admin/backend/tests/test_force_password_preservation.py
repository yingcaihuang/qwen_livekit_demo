"""Preservation property tests: Non-Force-Change Users Behavior Unchanged.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

Property 2: Preservation — Non-Force-Change Users Behavior Unchanged

These tests verify that users NOT meeting the bug condition
(auth_source='local' AND must_change_password=true) have consistent
behavior on /api/auth/me. They MUST PASS on unfixed code to establish a
baseline that the fix must preserve.

Observation-first methodology:
- Local user with must_change_password=false → normal /api/auth/me response
- SSO user → normal /api/auth/me response
- Unauthenticated request → 401
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Set temp DB path before imports
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")
os.environ["LIVEKIT_API_KEY"] = "devkey"
os.environ["LIVEKIT_API_SECRET"] = "secret-that-is-at-least-32-chars-long!"
os.environ["LIVEKIT_URL"] = "ws://localhost:7880"

import app.database as db_mod  # noqa: E402
from app.main import app  # noqa: E402
from app.services import auth_service  # noqa: E402

# PBT settings: lightweight DB tests with minimal examples
_pbt_settings = settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


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
async def local_user_normal():
    """Create a local user with must_change_password=false and return (user_id, session_token)."""
    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        user_id = "test-local-normal-001"
        password_hash = auth_service.hash_password("NormalPassword123!")
        await db.execute(
            "INSERT INTO users (id, username, auth_source, password_hash, is_active, must_change_password) "
            "VALUES (?, ?, 'local', ?, 1, 0)",
            (user_id, "normal_local_user", password_hash),
        )
        await db.execute(
            "INSERT INTO user_roles (user_id, role) VALUES (?, 'operator')",
            (user_id,),
        )
        session_token, csrf_token = await auth_service.create_session(db, user_id)
        await db.commit()
        return user_id, session_token


@pytest.fixture
async def sso_user():
    """Create an SSO user and return (user_id, session_token)."""
    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        user_id = "test-sso-user-001"
        await db.execute(
            "INSERT INTO users (id, username, auth_source, password_hash, is_active, must_change_password) "
            "VALUES (?, ?, 'sso', '', 1, 0)",
            (user_id, "sso_user"),
        )
        await db.execute(
            "INSERT INTO user_roles (user_id, role) VALUES (?, 'operator')",
            (user_id,),
        )
        session_token, csrf_token = await auth_service.create_session(db, user_id)
        await db.commit()
        return user_id, session_token


class TestPreservationLocalUserNormal:
    """Preservation: local user with must_change_password=false behaves normally.

    Validates: Requirements 3.1, 3.4
    """

    async def test_me_returns_200_for_normal_local_user(self, client, local_user_normal):
        """Local user with must_change_password=false gets normal 200 response from /api/auth/me."""
        user_id, session_token = local_user_normal

        with patch.dict(os.environ, {"TESTING": "0"}):
            response = await client.get(
                "/api/auth/me",
                cookies={auth_service.SESSION_COOKIE_NAME: session_token},
            )

        assert response.status_code == 200

    async def test_me_returns_correct_user_info_for_normal_local_user(
        self, client, local_user_normal
    ):
        """Local user with must_change_password=false gets correct id, username, roles, capabilities."""
        user_id, session_token = local_user_normal

        with patch.dict(os.environ, {"TESTING": "0"}):
            response = await client.get(
                "/api/auth/me",
                cookies={auth_service.SESSION_COOKIE_NAME: session_token},
            )

        data = response.json()
        assert data["id"] == user_id
        assert data["username"] == "normal_local_user"
        assert "roles" in data
        assert "operator" in data["roles"]
        assert "capabilities" in data
        assert isinstance(data["capabilities"], list)

    async def test_me_returns_must_change_password_false_for_normal_local_user(
        self, client, local_user_normal
    ):
        """Local user with must_change_password=false: the me endpoint returns must_change_password=false.

        On unfixed code, MeResponse defaults must_change_password to False (happens to be correct
        for this user). This behavior must be preserved after the fix.
        """
        user_id, session_token = local_user_normal

        with patch.dict(os.environ, {"TESTING": "0"}):
            response = await client.get(
                "/api/auth/me",
                cookies={auth_service.SESSION_COOKIE_NAME: session_token},
            )

        data = response.json()
        assert data["must_change_password"] is False


class TestPreservationSSOUser:
    """Preservation: SSO user behaves normally.

    Validates: Requirements 3.2
    """

    async def test_me_returns_200_for_sso_user(self, client, sso_user):
        """SSO user gets normal 200 response from /api/auth/me."""
        user_id, session_token = sso_user

        with patch.dict(os.environ, {"TESTING": "0"}):
            response = await client.get(
                "/api/auth/me",
                cookies={auth_service.SESSION_COOKIE_NAME: session_token},
            )

        assert response.status_code == 200

    async def test_me_returns_correct_user_info_for_sso_user(self, client, sso_user):
        """SSO user gets correct id, username, roles, capabilities."""
        user_id, session_token = sso_user

        with patch.dict(os.environ, {"TESTING": "0"}):
            response = await client.get(
                "/api/auth/me",
                cookies={auth_service.SESSION_COOKIE_NAME: session_token},
            )

        data = response.json()
        assert data["id"] == user_id
        assert data["username"] == "sso_user"
        assert "roles" in data
        assert "operator" in data["roles"]
        assert "capabilities" in data
        assert isinstance(data["capabilities"], list)

    async def test_me_returns_must_change_password_false_for_sso_user(self, client, sso_user):
        """SSO user: the me endpoint returns must_change_password=false.

        On unfixed code, this defaults to False (correct for SSO users).
        This must be preserved.
        """
        user_id, session_token = sso_user

        with patch.dict(os.environ, {"TESTING": "0"}):
            response = await client.get(
                "/api/auth/me",
                cookies={auth_service.SESSION_COOKIE_NAME: session_token},
            )

        data = response.json()
        assert data["must_change_password"] is False


class TestPreservationUnauthenticated:
    """Preservation: unauthenticated requests get 401.

    Validates: Requirements 3.5
    """

    async def test_me_returns_401_without_cookie(self, client):
        """Unauthenticated request (no session cookie) returns 401."""
        with patch.dict(os.environ, {"TESTING": "0"}):
            response = await client.get("/api/auth/me")

        assert response.status_code == 401

    async def test_me_returns_401_with_invalid_cookie(self, client):
        """Request with invalid session cookie returns 401."""
        with patch.dict(os.environ, {"TESTING": "0"}):
            response = await client.get(
                "/api/auth/me",
                cookies={auth_service.SESSION_COOKIE_NAME: "invalid-session-token"},
            )

        assert response.status_code == 401


class TestPreservationPropertyBased:
    """Property-based preservation test: for all non-bug-condition users,
    /api/auth/me response contains consistent fields.

    **Validates: Requirements 3.1, 3.2, 3.5**

    Property: For any user where NOT (auth_source='local' AND must_change_password=true),
    the /api/auth/me response fields (id, username, roles, capabilities) are returned correctly.
    """

    @_pbt_settings
    @given(
        auth_source=st.sampled_from(["local", "sso"]),
        must_change_password=st.just(False),  # Only non-bug-condition: must_change_password=false
        role=st.sampled_from(["operator", "super_admin", "readonly"]),
    )
    async def test_me_fields_preserved_for_non_bug_condition_users(
        self, client, auth_source, must_change_password, role
    ):
        """For all users NOT meeting bug condition, /api/auth/me returns consistent core fields.

        Generates users with different auth_source and roles but always
        must_change_password=false (non-bug-condition).
        """
        # Create a user with the generated parameters
        import uuid

        user_id = f"pbt-user-{uuid.uuid4().hex[:12]}"
        username = f"pbt_{auth_source}_{role}_{uuid.uuid4().hex[:6]}"

        async with aiosqlite.connect(db_mod.DB_PATH) as db:
            password_hash = (
                auth_service.hash_password("TestPass123!") if auth_source == "local" else ""
            )
            await db.execute(
                "INSERT INTO users (id, username, auth_source, password_hash, is_active, must_change_password) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (user_id, username, auth_source, password_hash, int(must_change_password)),
            )
            await db.execute(
                "INSERT INTO user_roles (user_id, role) VALUES (?, ?)",
                (user_id, role),
            )
            session_token, _ = await auth_service.create_session(db, user_id)
            await db.commit()

        with patch.dict(os.environ, {"TESTING": "0"}):
            response = await client.get(
                "/api/auth/me",
                cookies={auth_service.SESSION_COOKIE_NAME: session_token},
            )

        assert response.status_code == 200
        data = response.json()

        # Core fields must be present and correct
        assert data["id"] == user_id
        assert data["username"] == username
        assert isinstance(data["roles"], list)
        assert role in data["roles"]
        assert isinstance(data["capabilities"], list)
        # must_change_password should be false for non-bug-condition users
        assert data["must_change_password"] is False
