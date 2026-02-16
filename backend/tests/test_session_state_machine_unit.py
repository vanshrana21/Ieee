"""
Unit Tests for Session State Machine

Tests the strict state machine logic, transition rules, and concurrency safety.
"""
import pytest
import pytest_asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from typing import AsyncGenerator

from backend.orm.base import Base
from backend.orm.classroom_session import ClassroomSession, SessionState
from backend.orm.session_state_transition import SessionStateTransition
from backend.orm.classroom_session_state_log import ClassroomSessionStateLog
from backend.orm.user import User, UserRole
from backend.services.session_state_service import (
    transition_session_state,
    get_allowed_transition,
    get_allowed_transitions_from_state,
    can_transition,
    StateTransitionError,
    ConcurrentModificationError,
    PreconditionError,
    VALID_STATES
)

# Test database setup
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with async_session() as session:
        yield session
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture
async def faculty_user(db_session: AsyncSession) -> User:
    """Create a test faculty user."""
    user = User(
        email="faculty@test.com",
        full_name="Test Faculty",
        hashed_password="hashed",
        role=UserRole.teacher,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def student_user(db_session: AsyncSession) -> User:
    """Create a test student user."""
    user = User(
        email="student@test.com",
        full_name="Test Student",
        hashed_password="hashed",
        role=UserRole.student,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def classroom_session(db_session: AsyncSession, faculty_user: User) -> ClassroomSession:
    """Create a test classroom session."""
    session = ClassroomSession(
        session_code="JURIS-TEST01",
        teacher_id=faculty_user.id,
        case_id=1,
        topic="Test Session",
        category="constitutional",
        current_state="CREATED",
        is_active=True
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest_asyncio.fixture
async def seeded_transitions(db_session: AsyncSession) -> None:
    """Seed the session_state_transitions table with test data."""
    transitions = [
        SessionStateTransition(from_state="CREATED", to_state="PREPARING", trigger_type="faculty_action", requires_faculty=True),
        SessionStateTransition(from_state="PREPARING", to_state="ARGUING_PETITIONER", trigger_type="faculty_action", requires_faculty=True),
        SessionStateTransition(from_state="ARGUING_PETITIONER", to_state="ARGUING_RESPONDENT", trigger_type="round_completed"),
        SessionStateTransition(from_state="ARGUING_RESPONDENT", to_state="REBUTTAL", trigger_type="round_completed"),
        SessionStateTransition(from_state="REBUTTAL", to_state="JUDGING", trigger_type="faculty_action", requires_faculty=True),
        SessionStateTransition(from_state="JUDGING", to_state="COMPLETED", trigger_type="all_evaluations_complete", requires_all_rounds_complete=True, requires_faculty=True),
        SessionStateTransition(from_state="CREATED", to_state="CANCELLED", trigger_type="faculty_action", requires_faculty=True),
    ]
    
    for transition in transitions:
        db_session.add(transition)
    
    await db_session.commit()


# ==========================================
# Tests for get_allowed_transition
# ==========================================

@pytest.mark.asyncio
async def test_get_allowed_transition_success(db_session: AsyncSession, seeded_transitions):
    """Test getting an allowed transition."""
    transition = await get_allowed_transition(db_session, "CREATED", "PREPARING")
    
    assert transition is not None
    assert transition.from_state == "CREATED"
    assert transition.to_state == "PREPARING"
    assert transition.requires_faculty is True


@pytest.mark.asyncio
async def test_get_allowed_transition_not_found(db_session: AsyncSession, seeded_transitions):
    """Test getting a transition that doesn't exist."""
    transition = await get_allowed_transition(db_session, "CREATED", "COMPLETED")
    
    assert transition is None


@pytest.mark.asyncio
async def test_get_allowed_transition_case_insensitive(db_session: AsyncSession, seeded_transitions):
    """Test that state names are case insensitive."""
    transition = await get_allowed_transition(db_session, "created", "preparing")
    
    assert transition is not None
    assert transition.from_state == "CREATED"


# ==========================================
# Tests for get_allowed_transitions_from_state
# ==========================================

@pytest.mark.asyncio
async def test_get_allowed_transitions_from_state(db_session: AsyncSession, seeded_transitions):
    """Test getting all allowed transitions from a state."""
    transitions = await get_allowed_transitions_from_state(db_session, "CREATED")
    
    assert len(transitions) == 2  # CREATED -> PREPARING, CREATED -> CANCELLED
    to_states = [t.to_state for t in transitions]
    assert "PREPARING" in to_states
    assert "CANCELLED" in to_states


@pytest.mark.asyncio
async def test_get_allowed_transitions_empty(db_session: AsyncSession, seeded_transitions):
    """Test getting transitions from a state with no allowed transitions."""
    transitions = await get_allowed_transitions_from_state(db_session, "COMPLETED")
    
    assert len(transitions) == 0


# ==========================================
# Tests for can_transition
# ==========================================

@pytest.mark.asyncio
async def test_can_transition_allowed(db_session: AsyncSession, seeded_transitions, classroom_session):
    """Test checking if an allowed transition is possible."""
    is_allowed, message = await can_transition(
        classroom_session, "PREPARING", db_session, is_faculty=True
    )
    
    assert is_allowed is True
    assert "allowed" in message.lower() or "already" in message.lower()


@pytest.mark.asyncio
async def test_can_transition_not_allowed(db_session: AsyncSession, seeded_transitions, classroom_session):
    """Test checking if a disallowed transition is blocked."""
    is_allowed, message = await can_transition(
        classroom_session, "COMPLETED", db_session, is_faculty=True
    )
    
    assert is_allowed is False
    assert "Cannot transition" in message


@pytest.mark.asyncio
async def test_can_transition_faculty_required(db_session: AsyncSession, seeded_transitions, classroom_session):
    """Test that faculty-required transitions are blocked for non-faculty."""
    is_allowed, message = await can_transition(
        classroom_session, "PREPARING", db_session, is_faculty=False
    )
    
    assert is_allowed is False
    assert "faculty" in message.lower()


@pytest.mark.asyncio
async def test_can_transition_idempotency(db_session: AsyncSession, seeded_transitions, classroom_session):
    """Test that transitioning to the same state is allowed (idempotency)."""
    is_allowed, message = await can_transition(
        classroom_session, "CREATED", db_session, is_faculty=False
    )
    
    assert is_allowed is True
    assert "already" in message.lower()


@pytest.mark.asyncio
async def test_can_transition_invalid_state(db_session: AsyncSession, seeded_transitions, classroom_session):
    """Test that invalid target states are rejected."""
    is_allowed, message = await can_transition(
        classroom_session, "INVALID_STATE", db_session, is_faculty=True
    )
    
    assert is_allowed is False
    assert "Invalid" in message


# ==========================================
# Tests for transition_session_state
# ==========================================

@pytest.mark.asyncio
async def test_transition_session_state_success(
    db_session: AsyncSession, seeded_transitions, classroom_session, faculty_user
):
    """Test a successful state transition."""
    session = await transition_session_state(
        session_id=classroom_session.id,
        to_state="PREPARING",
        acting_user_id=faculty_user.id,
        db=db_session,
        is_faculty=True,
        reason="Starting preparation phase"
    )
    
    assert session.current_state == "PREPARING"
    assert session.state_updated_at is not None


@pytest.mark.asyncio
async def test_transition_session_state_not_allowed(
    db_session: AsyncSession, seeded_transitions, classroom_session, faculty_user
):
    """Test that disallowed transitions raise StateTransitionError."""
    with pytest.raises(StateTransitionError) as exc_info:
        await transition_session_state(
            session_id=classroom_session.id,
            to_state="COMPLETED",
            acting_user_id=faculty_user.id,
            db=db_session,
            is_faculty=True
        )
    
    assert "Cannot transition" in str(exc_info.value)
    assert exc_info.value.from_state == "CREATED"
    assert exc_info.value.to_state == "COMPLETED"


@pytest.mark.asyncio
async def test_transition_session_state_faculty_required(
    db_session: AsyncSession, seeded_transitions, classroom_session, student_user
):
    """Test that faculty-required transitions are blocked for students."""
    with pytest.raises(StateTransitionError) as exc_info:
        await transition_session_state(
            session_id=classroom_session.id,
            to_state="PREPARING",
            acting_user_id=student_user.id,
            db=db_session,
            is_faculty=False  # Student trying to do faculty action
        )
    
    assert "faculty" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_transition_session_state_idempotency(
    db_session: AsyncSession, seeded_transitions, classroom_session, faculty_user
):
    """Test that transitioning to the same state is a no-op."""
    initial_state = classroom_session.current_state
    
    session = await transition_session_state(
        session_id=classroom_session.id,
        to_state=initial_state,  # Same state
        acting_user_id=faculty_user.id,
        db=db_session,
        is_faculty=True,
        reason="Idempotency test"
    )
    
    assert session.current_state == initial_state


@pytest.mark.asyncio
async def test_transition_session_state_logs_audit(
    db_session: AsyncSession, seeded_transitions, classroom_session, faculty_user
):
    """Test that transitions are logged to the audit table."""
    await transition_session_state(
        session_id=classroom_session.id,
        to_state="PREPARING",
        acting_user_id=faculty_user.id,
        db=db_session,
        is_faculty=True,
        reason="Audit log test"
    )
    
    # Check audit log
    from sqlalchemy import select
    result = await db_session.execute(
        select(ClassroomSessionStateLog).where(
            ClassroomSessionStateLog.session_id == classroom_session.id
        )
    )
    logs = result.scalars().all()
    
    assert len(logs) >= 1
    assert logs[0].from_state == "CREATED"
    assert logs[0].to_state == "PREPARING"
    assert logs[0].is_successful is True


@pytest.mark.asyncio
async def test_transition_session_state_not_found(
    db_session: AsyncSession, seeded_transitions, faculty_user
):
    """Test that transitioning a non-existent session raises an error."""
    with pytest.raises(StateTransitionError) as exc_info:
        await transition_session_state(
            session_id=99999,  # Non-existent
            to_state="PREPARING",
            acting_user_id=faculty_user.id,
            db=db_session,
            is_faculty=True
        )
    
    assert "not found" in str(exc_info.value).lower()


# ==========================================
# Tests for VALID_STATES constant
# ==========================================

def test_valid_states_constant():
    """Test that VALID_STATES contains all expected states."""
    expected_states = {
        "CREATED",
        "PREPARING",
        "ARGUING_PETITIONER",
        "ARGUING_RESPONDENT",
        "REBUTTAL",
        "JUDGING",
        "COMPLETED",
        "CANCELLED"
    }
    
    assert VALID_STATES == expected_states
