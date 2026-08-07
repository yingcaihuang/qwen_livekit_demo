"""Property-based tests for the Chat service (Task 4.4).

Covers the following correctness properties from the design doc:

- Property 5:  temperature 参数区间约束
    Validates: Requirements 2.5
- Property 6:  max_tokens 参数约束为正整数
    Validates: Requirements 2.6
- Property 8:  对话 Token 用量累加一致性
    Validates: Requirements 3.3, 3.6
- Property 9:  对话消息持久化完整性
    Validates: Requirements 3.2
- Property 10: 会话删除级联清理消息
    Validates: Requirements 3.5

Each property runs at least 100 Hypothesis examples. Properties 8/9/10 use a
real SQLite database created from the production schema (init_db against a temp
DB_PATH) plus a real chat instance + session, following the conventions in
test_instance_type.py / test_migration.py / test_chat_api.py.
"""

import math
import os
import tempfile
import uuid
from pathlib import Path

import aiosqlite
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Set a temp DB path before importing the database module (matches existing
# test conventions in test_instance_type.py / test_migration.py).
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")

import app.database as db_mod  # noqa: E402
from app.database import init_db  # noqa: E402
from app.models.instance import InstanceCreate  # noqa: E402
from app.services.chat_service import ChatService  # noqa: E402
from app.services.instance_service import InstanceService  # noqa: E402
from app.services.session_service import SessionService  # noqa: E402

# Common Hypothesis settings: >=100 examples, no deadline (DB IO varies), and
# allow reuse of the function-scoped DB fixture across examples.
_pbt_settings = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    """Use a fresh temp database (real schema) for each test function."""
    test_db = str(tmp_path / "test.db")
    db_mod.DB_PATH = test_db
    await init_db()
    yield
    for suffix in ("", "-wal", "-shm"):
        p = Path(test_db + suffix)
        if p.exists():
            p.unlink()


@pytest.fixture
async def db():
    """Provide a database connection bound to the current test DB."""
    async with aiosqlite.connect(db_mod.DB_PATH) as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn


@pytest.fixture
def chat_service():
    """Provide a ChatService instance."""
    return ChatService()


@pytest.fixture
def instance_service():
    """Provide an InstanceService instance."""
    return InstanceService()


@pytest.fixture
def session_service():
    """Provide a SessionService instance."""
    return SessionService()


def _unique_name(prefix: str) -> str:
    """A globally-unique instance name (the DB persists across examples)."""
    return f"{prefix}-{uuid.uuid4().hex}"


async def _create_chat_instance(instance_service: InstanceService, db) -> str:
    """Create a chat-type instance and return its id."""
    created = await instance_service.create_instance(
        db,
        InstanceCreate(
            name=_unique_name("chat"),
            endpoint="https://ep.openai.azure.com",
            api_key="sk-chat-key",
            deployment="gpt-5.5",
            type="chat",
        ),
    )
    return created["id"]


# ----------------------------------------------------------------------
# Property 5: temperature 参数区间约束 (Validates: Requirements 2.5)
# ----------------------------------------------------------------------
class TestProperty5TemperatureClamp:
    """Property 5: temperature 参数区间约束 (Validates: Requirements 2.5)."""

    @_pbt_settings
    @given(temp=st.floats(allow_nan=False, allow_infinity=False, min_value=-10.0, max_value=10.0))
    def test_property5_clamped_into_zero_two(self, temp):
        """Any real temperature is clamped into the closed range [0, 2]."""
        result = ChatService._clamp_temperature(temp)
        assert 0.0 <= result <= 2.0

    @_pbt_settings
    @given(temp=st.floats(allow_nan=False, allow_infinity=False, min_value=-10.0, max_value=10.0))
    def test_property5_boundaries_and_identity(self, temp):
        """Below 0 -> 0, above 2 -> 2, in-range values unchanged."""
        result = ChatService._clamp_temperature(temp)
        if temp < 0.0:
            assert result == 0.0
        elif temp > 2.0:
            assert result == 2.0
        else:
            # Identity within range.
            assert math.isclose(result, temp, rel_tol=0.0, abs_tol=0.0)


# ----------------------------------------------------------------------
# Property 6: max_tokens 参数约束为正整数 (Validates: Requirements 2.6)
# ----------------------------------------------------------------------
class TestProperty6MaxTokensPositiveInt:
    """Property 6: max_tokens 参数约束为正整数 (Validates: Requirements 2.6)."""

    def test_property6_none_passthrough(self):
        """A None max_tokens is passed through unchanged."""
        assert ChatService._sanitize_max_tokens(None) is None

    @_pbt_settings
    @given(value=st.integers(min_value=-10_000, max_value=10_000))
    def test_property6_any_int_becomes_positive(self, value):
        """Any integer maps to a positive integer (>= 1); values < 1 -> 1."""
        result = ChatService._sanitize_max_tokens(value)
        assert result is not None
        assert isinstance(result, int)
        assert result >= 1
        if value < 1:
            assert result == 1
        else:
            assert result == value


# ----------------------------------------------------------------------
# Property 8: 对话 Token 用量累加一致性 (Validates: Requirements 3.3, 3.6)
# ----------------------------------------------------------------------
class TestProperty8TokenAccumulation:
    """Property 8: 对话 Token 用量累加一致性 (Validates: Requirements 3.3, 3.6)."""

    @_pbt_settings
    @given(
        usages=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=100_000),
                st.integers(min_value=0, max_value=100_000),
            ),
            min_size=1,
            max_size=10,
        )
    )
    async def test_property8_session_totals_equal_sum_of_turns(
        self, db, chat_service, instance_service, session_service, usages
    ):
        """Repeated persist_turn calls accumulate token totals exactly.

        The session's persisted input_tokens/output_tokens equal the sum of the
        per-turn counts; turns with zero usage contribute zero.
        """
        instance_id = await _create_chat_instance(instance_service, db)
        session_id = await chat_service.new_conversation(db, instance_id)

        expected_input = 0
        expected_output = 0
        for i, (in_tok, out_tok) in enumerate(usages):
            await chat_service.persist_turn(
                db,
                session_id,
                f"user message {i}",
                f"assistant reply {i}",
                in_tok,
                out_tok,
            )
            expected_input += in_tok
            expected_output += out_tok

        detail = await session_service.get_session(db, session_id)
        assert detail.input_tokens == expected_input
        assert detail.output_tokens == expected_output


# ----------------------------------------------------------------------
# Property 9: 对话消息持久化完整性 (Validates: Requirements 3.2)
# ----------------------------------------------------------------------
class TestProperty9MessagePersistence:
    """Property 9: 对话消息持久化完整性 (Validates: Requirements 3.2)."""

    @_pbt_settings
    @given(
        turns=st.lists(
            st.tuples(
                # user content: None (no user message) or a text string.
                st.one_of(st.none(), st.text(min_size=1, max_size=60)),
                # assistant content: always present.
                st.text(min_size=1, max_size=60),
            ),
            min_size=1,
            max_size=6,
        )
    )
    async def test_property9_user_and_assistant_persisted_in_order(
        self, db, chat_service, instance_service, turns
    ):
        """Each turn persists the user (when provided) + assistant message.

        Verifies correct role, content, and insertion order in session_messages.
        """
        instance_id = await _create_chat_instance(instance_service, db)
        session_id = await chat_service.new_conversation(db, instance_id)

        # Build the expected ordered (role, content) sequence.
        expected: list[tuple[str, str]] = []
        for user_content, assistant_content in turns:
            await chat_service.persist_turn(
                db,
                session_id,
                user_content,
                assistant_content,
                0,
                0,
            )
            if user_content is not None:
                expected.append(("user", user_content))
            expected.append(("assistant", assistant_content))

        cursor = await db.execute(
            """
            SELECT role, content, timestamp
            FROM session_messages
            WHERE session_id = ?
            ORDER BY id
            """,
            (session_id,),
        )
        rows = await cursor.fetchall()

        # Same number of rows and identical ordered (role, content) sequence.
        assert len(rows) == len(expected)
        for row, (exp_role, exp_content) in zip(rows, expected, strict=False):
            role, content, timestamp = row[0], row[1], row[2]
            assert role in ("user", "assistant")
            assert role == exp_role
            assert content == exp_content
            # A non-empty timestamp is always recorded.
            assert timestamp


# ----------------------------------------------------------------------
# Property 10: 会话删除级联清理消息 (Validates: Requirements 3.5)
# ----------------------------------------------------------------------
class TestProperty10DeleteCascade:
    """Property 10: 会话删除级联清理消息 (Validates: Requirements 3.5)."""

    @_pbt_settings
    @given(
        turns=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=40),
                st.text(min_size=1, max_size=40),
            ),
            min_size=1,
            max_size=6,
        )
    )
    async def test_property10_delete_session_removes_all_messages(
        self, db, chat_service, instance_service, session_service, turns
    ):
        """Deleting a chat session removes the session and its messages."""
        instance_id = await _create_chat_instance(instance_service, db)
        session_id = await chat_service.new_conversation(db, instance_id)

        for user_content, assistant_content in turns:
            await chat_service.persist_turn(db, session_id, user_content, assistant_content, 1, 1)

        # Messages exist before deletion (user + assistant per turn).
        cursor = await db.execute(
            "SELECT COUNT(*) FROM session_messages WHERE session_id = ?",
            (session_id,),
        )
        assert (await cursor.fetchone())[0] == len(turns) * 2

        await session_service.delete_session(db, session_id)

        # Session row is gone.
        cursor = await db.execute("SELECT COUNT(*) FROM sessions WHERE id = ?", (session_id,))
        assert (await cursor.fetchone())[0] == 0

        # No orphaned messages remain.
        cursor = await db.execute(
            "SELECT COUNT(*) FROM session_messages WHERE session_id = ?",
            (session_id,),
        )
        assert (await cursor.fetchone())[0] == 0
