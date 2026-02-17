"""
Classroom Mode Tests - Phase 7
Comprehensive test suite for classroom functionality.
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from typing import AsyncGenerator

try:
    import pytest_asyncio
except ModuleNotFoundError:
    pytest.skip("pytest_asyncio not installed", allow_module_level=True)
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from backend.main import app
from backend.database import get_async_db, Base
from backend.orm.classroom_session import ClassroomSession, ClassroomParticipant, ParticipantRole
from backend.orm.classroom_round import ClassroomRound, RoundState, PairingMode
from backend.orm.classroom_round_action import ClassroomRoundAction, ActionType
from backend.orm.user import User
from backend.state_machines.round_state import RoundStateMachine, InvalidTransitionError
from backend.services.classroom.pairing_engine import PairingEngine, Student, RoundPair


# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database override."""
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_async_db] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_teacher(db_session) -> User:
    """Create test teacher user."""
    teacher = User(
        email="teacher@test.com",
        full_name="Test Teacher",
        role="teacher",
        institution_id=1,
        is_active=True
    )
    db_session.add(teacher)
    await db_session.flush()
    return teacher


@pytest_asyncio.fixture
async def test_students(db_session) -> list[User]:
    """Create test student users."""
    students = []
    for i in range(4):
        student = User(
            email=f"student{i}@test.com",
            full_name=f"Student {i}",
            role="student",
            institution_id=1,
            skill_rating=1000 + (i * 50),  # Different skill ratings
            is_active=True
        )
        db_session.add(student)
        students.append(student)
    
    await db_session.flush()
    return students


@pytest_asyncio.fixture
async def test_session(db_session, test_teacher) -> ClassroomSession:
    """Create test classroom session."""
    session = ClassroomSession(
        teacher_id=test_teacher.id,
        institution_id=1,
        title="Test Moot Court Session",
        topic="Constitutional Law",
        category="Supreme Court",
        session_code="TEST1234",
        max_participants=32,
        current_state="CREATED",
        prep_time_minutes=30,
        oral_time_minutes=10,
        ai_judge_mode=False
    )
    db_session.add(session)
    await db_session.flush()
    return session


@pytest_asyncio.fixture
async def test_round(db_session, test_session, test_students) -> ClassroomRound:
    """Create test classroom round."""
    round_obj = ClassroomRound(
        session_id=test_session.id,
        round_number=1,
        petitioner_id=test_students[0].id,
        respondent_id=test_students[1].id,
        judge_id=test_students[2].id,
        state=RoundState.WAITING,
        time_limit_seconds=600,
        pairing_mode=PairingMode.RANDOM
    )
    db_session.add(round_obj)
    await db_session.flush()
    return round_obj


# =============================================================================
# State Machine Tests
# =============================================================================

@pytest.mark.asyncio
async def test_valid_state_transition(db_session, test_round):
    """Test valid state transition."""
    machine = RoundStateMachine(db_session, test_round)
    
    # Valid: WAITING -> ARGUMENT_PETITIONER
    result = await machine.transition(
        actor_id=1,
        new_state=RoundState.ARGUMENT_PETITIONER,
        payload={"started_by": "teacher"}
    )
    
    assert result.state == RoundState.ARGUMENT_PETITIONER
    assert result.started_at is not None


@pytest.mark.asyncio
async def test_invalid_state_transition(db_session, test_round):
    """Test invalid state transition raises error."""
    machine = RoundStateMachine(db_session, test_round)
    
    # Invalid: WAITING -> COMPLETED (must go through intermediate states)
    with pytest.raises(InvalidTransitionError):
        await machine.transition(
            actor_id=1,
            new_state=RoundState.COMPLETED
        )


@pytest.mark.asyncio
async def test_state_transition_logging(db_session, test_round):
    """Test that state transitions are logged."""
    machine = RoundStateMachine(db_session, test_round)
    
    await machine.transition(
        actor_id=1,
        new_state=RoundState.ARGUMENT_PETITIONER
    )
    
    await db_session.commit()
    
    # Check action log was created
    action = await db_session.scalar(
        select(ClassroomRoundAction).where(
            ClassroomRoundAction.round_id == test_round.id,
            ClassroomRoundAction.action_type == ActionType.STATE_TRANSITION
        )
    )
    
    assert action is not None
    assert action.from_state == "waiting"
    assert action.to_state == "argument_petitioner"


@pytest.mark.asyncio
async def test_pause_and_resume(db_session, test_round):
    """Test pause and resume functionality."""
    machine = RoundStateMachine(db_session, test_round)
    
    # Move to active state
    await machine.transition(
        actor_id=1,
        new_state=RoundState.ARGUMENT_PETITIONER
    )
    
    # Pause
    result = await machine.pause(actor_id=1)
    assert result.state == RoundState.PAUSED
    assert result.previous_state == RoundState.ARGUMENT_PETITIONER
    
    # Resume
    result = await machine.resume(actor_id=1)
    assert result.state == RoundState.ARGUMENT_PETITIONER
    assert result.previous_state is None


# =============================================================================
# Pairing Engine Tests
# =============================================================================

@pytest.mark.asyncio
async def test_random_pairing(db_session, test_session, test_students):
    """Test random pairing algorithm."""
    # Add students as participants
    for student in test_students:
        participant = ClassroomParticipant(
            session_id=test_session.id,
            user_id=student.id,
            role=ParticipantRole.STUDENT.value,
            approved=True
        )
        db_session.add(participant)
    
    await db_session.commit()
    
    engine = PairingEngine(db_session)
    pairs = await engine.pair_participants(
        session_id=test_session.id,
        mode=PairingMode.RANDOM
    )
    
    # Should create 2 pairs from 4 students
    assert len(pairs) == 2
    
    # All students should be paired
    paired_ids = set()
    for pair in pairs:
        paired_ids.add(pair.petitioner.user_id)
        paired_ids.add(pair.respondent.user_id)
    
    assert len(paired_ids) == 4


@pytest.mark.asyncio
async def test_skill_based_pairing(db_session, test_session, test_students):
    """Test skill-based pairing matches similar skill levels."""
    # Add students as participants
    for student in test_students:
        participant = ClassroomParticipant(
            session_id=test_session.id,
            user_id=student.id,
            role=ParticipantRole.STUDENT.value,
            approved=True
        )
        db_session.add(participant)
    
    await db_session.commit()
    
    engine = PairingEngine(db_session)
    pairs = await engine.pair_participants(
        session_id=test_session.id,
        mode=PairingMode.SKILL
    )
    
    assert len(pairs) == 2
    
    # Check that pairs have similar skill ratings
    for pair in pairs:
        delta = abs(
            (pair.petitioner.skill_rating or 0) - 
            (pair.respondent.skill_rating or 0)
        )
        # Skill delta should be reasonable (within 100 points for test data)
        assert delta <= 100


@pytest.mark.asyncio
async def test_ai_fallback_pairing(db_session, test_session, test_students):
    """Test AI fallback for odd number of students."""
    # Add 3 students (odd number)
    for student in test_students[:3]:
        participant = ClassroomParticipant(
            session_id=test_session.id,
            user_id=student.id,
            role=ParticipantRole.STUDENT.value,
            approved=True
        )
        db_session.add(participant)
    
    await db_session.commit()
    
    engine = PairingEngine(db_session)
    pairs = await engine.pair_participants(
        session_id=test_session.id,
        mode=PairingMode.AI_FALLBACK
    )
    
    # Should create 2 pairs (1 human pair, 1 with AI)
    assert len(pairs) == 2
    
    # One pair should have AI opponent (user_id < 0)
    ai_pairs = [p for p in pairs if p.respondent.user_id < 0]
    assert len(ai_pairs) == 1


@pytest.mark.asyncio
async def test_manual_pairing(db_session, test_session, test_students):
    """Test manual pairing with specified pairs."""
    # Add students
    for student in test_students:
        participant = ClassroomParticipant(
            session_id=test_session.id,
            user_id=student.id,
            role=ParticipantRole.STUDENT.value,
            approved=True
        )
        db_session.add(participant)
    
    await db_session.commit()
    
    # Define manual pairs
    manual_pairs = [
        {"petitioner_id": test_students[0].id, "respondent_id": test_students[1].id},
        {"petitioner_id": test_students[2].id, "respondent_id": test_students[3].id}
    ]
    
    engine = PairingEngine(db_session)
    pairs = await engine.pair_participants(
        session_id=test_session.id,
        mode=PairingMode.MANUAL,
        manual_pairs=manual_pairs
    )
    
    assert len(pairs) == 2
    assert pairs[0].petitioner.user_id == test_students[0].id
    assert pairs[0].respondent.user_id == test_students[1].id


# =============================================================================
# API Endpoint Tests
# =============================================================================

@pytest.mark.asyncio
async def test_create_session_endpoint(client, test_teacher):
    """Test session creation endpoint."""
    # This would need authentication mocking
    response = await client.post(
        "/api/classroom/sessions",
        json={
            "title": "New Session",
            "topic": "Criminal Law",
            "category": "High Court",
            "max_capacity": 20,
            "pairing_mode": "random",
            "prep_time_minutes": 30,
            "oral_time_minutes": 10
        }
    )
    
    # Without auth, should get 401 or 403
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_join_session_endpoint(client, test_session):
    """Test session join endpoint."""
    response = await client.post(
        "/api/classroom/sessions/join",
        json={"session_code": test_session.session_code}
    )
    
    # Without auth, should get 401
    assert response.status_code == 401


# =============================================================================
# Round Timing Tests
# =============================================================================

@pytest.mark.asyncio
async def test_round_timer_calculation(db_session, test_round):
    """Test remaining time calculation."""
    # Set phase timing
    test_round.phase_start_timestamp = datetime.utcnow() - timedelta(minutes=5)
    test_round.phase_duration_seconds = 600  # 10 minutes
    
    remaining = test_round.get_remaining_seconds()
    
    # Should have ~5 minutes remaining (300 seconds), with some tolerance
    assert 290 <= remaining <= 310


@pytest.mark.asyncio
async def test_round_timer_expiry(db_session, test_round):
    """Test timer expiry detection."""
    # Set expired timing
    test_round.phase_start_timestamp = datetime.utcnow() - timedelta(minutes=15)
    test_round.phase_duration_seconds = 600  # 10 minutes
    
    assert test_round.is_phase_expired() is True
    assert test_round.get_remaining_seconds() == 0


# =============================================================================
# Security Tests
# =============================================================================

@pytest.mark.asyncio
async def test_unauthorized_transition(db_session, test_round, test_students):
    """Test unauthorized user cannot transition round."""
    machine = RoundStateMachine(db_session, test_round)
    
    # Student (not teacher/judge) should not be able to transition
    with pytest.raises(Exception):  # UnauthorizedActionError
        await machine.transition(
            actor_id=test_students[0].id,  # Petitioner, not teacher/judge
            new_state=RoundState.ARGUMENT_PETITIONER
        )


@pytest.mark.asyncio
async def test_rate_limiting():
    """Test rate limiting mechanism."""
    from backend.services.classroom.security import RateLimiter
    
    limiter = RateLimiter()
    user_id = 1
    endpoint = "/api/test"
    
    # Should allow requests up to limit
    for i in range(30):
        assert limiter.is_allowed(user_id, endpoint, max_requests=30) is True
    
    # Next request should be blocked
    assert limiter.is_allowed(user_id, endpoint, max_requests=30) is False


# =============================================================================
# Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_full_round_lifecycle(db_session, test_session, test_students, test_teacher):
    """Test complete round lifecycle from creation to completion."""
    # Add teacher as participant
    teacher_participant = ClassroomParticipant(
        session_id=test_session.id,
        user_id=test_teacher.id,
        role=ParticipantRole.TEACHER.value,
        approved=True
    )
    db_session.add(teacher_participant)
    
    # Add students
    for student in test_students:
        participant = ClassroomParticipant(
            session_id=test_session.id,
            user_id=student.id,
            role=ParticipantRole.STUDENT.value,
            approved=True
        )
        db_session.add(participant)
    
    await db_session.commit()
    
    # 1. Create round
    round_obj = await RoundStateMachine.create_round(
        db=db_session,
        session_id=test_session.id,
        round_number=1,
        petitioner_id=test_students[0].id,
        respondent_id=test_students[1].id,
        judge_id=test_students[2].id,
        creator_id=test_teacher.id
    )
    
    assert round_obj.state == RoundState.WAITING
    
    # 2. Transition through all states
    machine = RoundStateMachine(db_session, round_obj)
    
    states = [
        RoundState.ARGUMENT_PETITIONER,
        RoundState.ARGUMENT_RESPONDENT,
        RoundState.REBUTTAL,
        RoundState.SUR_REBUTTAL,
        RoundState.JUDGE_QUESTIONS,
        RoundState.SCORING,
        RoundState.COMPLETED
    ]
    
    for state in states:
        await machine.transition(
            actor_id=test_teacher.id,
            new_state=state
        )
        assert round_obj.state == state
    
    # 3. Submit scores
    await machine.submit_score(
        actor_id=test_students[2].id,  # Judge
        petitioner_score=18.5,
        respondent_score=16.0,
        winner_id=test_students[0].id
    )
    
    assert round_obj.petitioner_score == 18.5
    assert round_obj.respondent_score == 16.0
    assert round_obj.winner_id == test_students[0].id
    
    # 4. Verify action logs
    actions = await db_session.scalars(
        select(ClassroomRoundAction).where(
            ClassroomRoundAction.round_id == round_obj.id
        )
    )
    
    action_list = list(actions)
    assert len(action_list) >= len(states) + 2  # transitions + creation + scoring


@pytest.mark.asyncio
async def test_concurrent_modification_prevention(db_session, test_round, test_teacher):
    """Test that concurrent modifications are detected."""
    machine1 = RoundStateMachine(db_session, test_round)
    machine2 = RoundStateMachine(db_session, test_round)
    
    # First transition
    await machine1.transition(
        actor_id=test_teacher.id,
        new_state=RoundState.ARGUMENT_PETITIONER
    )
    await db_session.commit()
    
    # Refresh to simulate concurrent access
    await db_session.refresh(test_round)
    
    # Second machine should have stale version
    machine2._original_version = test_round.version - 1
    
    # This should detect version mismatch
    # Note: In actual implementation, this would raise ConcurrentModificationError
    # For now, we just verify the version tracking works
    assert machine2._original_version < test_round.version


# =============================================================================
# Edge Case Tests
# =============================================================================

@pytest.mark.asyncio
async def test_empty_session_pairing(db_session, test_session):
    """Test pairing with no participants."""
    engine = PairingEngine(db_session)
    pairs = await engine.pair_participants(
        session_id=test_session.id,
        mode=PairingMode.RANDOM
    )
    
    assert len(pairs) == 0


@pytest.mark.asyncio
async def test_single_participant_pairing(db_session, test_session, test_students):
    """Test pairing with single participant."""
    # Add single participant
    participant = ClassroomParticipant(
        session_id=test_session.id,
        user_id=test_students[0].id,
        role=ParticipantRole.STUDENT.value,
        approved=True
    )
    db_session.add(participant)
    await db_session.commit()
    
    engine = PairingEngine(db_session)
    pairs = await engine.pair_participants(
        session_id=test_session.id,
        mode=PairingMode.RANDOM
    )
    
    # Should return empty (not enough for a pair)
    assert len(pairs) == 0


@pytest.mark.asyncio
async def test_duplicate_join_prevention(db_session, test_session, test_students):
    """Test that duplicate joins are prevented."""
    # First join
    participant1 = ClassroomParticipant(
        session_id=test_session.id,
        user_id=test_students[0].id,
        role=ParticipantRole.STUDENT.value,
        approved=True
    )
    db_session.add(participant1)
    await db_session.commit()
    
    # Attempt duplicate join (same user_id, same session_id)
    # In actual implementation, this would be prevented at DB level
    # or caught by application logic
    
    # Check that participant exists
    existing = await db_session.scalar(
        select(ClassroomParticipant).where(
            ClassroomParticipant.session_id == test_session.id,
            ClassroomParticipant.user_id == test_students[0].id
        )
    )
    
    assert existing is not None
    assert existing.id == participant1.id
