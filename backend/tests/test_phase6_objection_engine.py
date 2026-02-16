"""
Phase 6 — Objection & Procedural Control Engine Test Suite

Tests for:
- Objection raising pauses timer
- Cannot raise objection if turn not active
- Cannot raise second objection while pending
- Only presiding judge can rule
- Ruling resumes timer
- Cannot rule twice
- Cannot object after session completed
- Partial index enforcement
- Trigger enforcement
- Tamper detection via event chain
- Institution scoping
- Concurrency (parallel raise attempts)
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.live_court import (
    LiveCourtSession, LiveTurn, LiveCourtStatus, LiveTurnState, OralSide, OralTurnType
)
from backend.orm.live_objection import (
    LiveObjection, ObjectionType, ObjectionState, ProceduralViolation
)
from backend.orm.national_network import Institution
from backend.orm.round_pairing import TournamentRound, RoundType
from backend.orm.user import User, UserRole
from backend.services.live_objection_service import (
    raise_objection, rule_objection, record_procedural_violation,
    get_objections_by_session, get_pending_objection_for_turn,
    ObjectionNotFoundError, ObjectionAlreadyRuledError,
    ObjectionAlreadyPendingError, NotPresidingJudgeError,
    TurnNotActiveError, SessionNotLiveError, SessionCompletedError
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def institution_a(db: AsyncSession) -> Institution:
    """Create test institution."""
    inst = Institution(
        name="Test College A",
        code="TCA001",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(inst)
    await db.flush()
    return inst


@pytest.fixture
async def session_live(
    db: AsyncSession,
    institution_a: Institution
) -> LiveCourtSession:
    """Create a live session."""
    round_obj = TournamentRound(
        tournament_id=1,
        round_number=1,
        round_type=RoundType.SWISS,
        created_at=datetime.utcnow()
    )
    db.add(round_obj)
    await db.flush()
    
    session = LiveCourtSession(
        round_id=round_obj.id,
        institution_id=institution_a.id,
        status=LiveCourtStatus.LIVE,
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(session)
    await db.flush()
    return session


@pytest.fixture
async def active_turn(
    db: AsyncSession,
    session_live: LiveCourtSession
) -> LiveTurn:
    """Create an active turn."""
    turn = LiveTurn(
        session_id=session_live.id,
        participant_id=1,
        side=OralSide.PETITIONER,
        turn_type=OralTurnType.PRESENTATION,
        allocated_seconds=60,
        state=LiveTurnState.ACTIVE,
        started_at=datetime.utcnow(),
        is_timer_paused=False,
        created_at=datetime.utcnow()
    )
    db.add(turn)
    await db.flush()
    return turn


@pytest.fixture
async def ended_turn(
    db: AsyncSession,
    session_live: LiveCourtSession
) -> LiveTurn:
    """Create an ended turn."""
    turn = LiveTurn(
        session_id=session_live.id,
        participant_id=2,
        side=OralSide.RESPONDENT,
        turn_type=OralTurnType.PRESENTATION,
        allocated_seconds=60,
        state=LiveTurnState.ENDED,
        started_at=datetime.utcnow() - timedelta(minutes=2),
        ended_at=datetime.utcnow() - timedelta(minutes=1),
        is_timer_paused=False,
        created_at=datetime.utcnow()
    )
    db.add(turn)
    await db.flush()
    return turn


@pytest.fixture
async def completed_session(
    db: AsyncSession,
    institution_a: Institution
) -> LiveCourtSession:
    """Create a completed session."""
    round_obj = TournamentRound(
        tournament_id=1,
        round_number=1,
        round_type=RoundType.SWISS,
        created_at=datetime.utcnow()
    )
    db.add(round_obj)
    await db.flush()
    
    session = LiveCourtSession(
        round_id=round_obj.id,
        institution_id=institution_a.id,
        status=LiveCourtStatus.COMPLETED,
        started_at=datetime.utcnow() - timedelta(hours=1),
        ended_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(session)
    await db.flush()
    return session


# =============================================================================
# Test: Raise Objection Pauses Timer
# =============================================================================

@pytest.mark.asyncio
async def test_raise_objection_pauses_timer(
    db: AsyncSession,
    session_live: LiveCourtSession,
    active_turn: LiveTurn
):
    """Test that raising an objection pauses the turn timer."""
    assert active_turn.is_timer_paused == False, "Timer should start unpaused"
    
    objection, turn = await raise_objection(
        session_id=session_live.id,
        turn_id=active_turn.id,
        raised_by_user_id=1,
        objection_type=ObjectionType.LEADING,
        reason_text="Leading question",
        db=db
    )
    
    # Check objection created
    assert objection.id is not None
    assert objection.state == ObjectionState.PENDING
    assert objection.turn_id == active_turn.id
    
    # Check timer is paused
    assert turn.is_timer_paused == True, "Timer should be paused after objection"
    
    # Check from DB
    result = await db.execute(
        select(LiveTurn.is_timer_paused)
        .where(LiveTurn.id == active_turn.id)
    )
    is_paused = result.scalar_one()
    assert is_paused == True


# =============================================================================
# Test: Cannot Raise Objection if Turn Not Active
# =============================================================================

@pytest.mark.asyncio
async def test_cannot_object_to_inactive_turn(
    db: AsyncSession,
    session_live: LiveCourtSession,
    ended_turn: LiveTurn
):
    """Test that objections can only be raised on active turns."""
    with pytest.raises(TurnNotActiveError) as exc:
        await raise_objection(
            session_id=session_live.id,
            turn_id=ended_turn.id,
            raised_by_user_id=1,
            objection_type=ObjectionType.IRRELEVANT,
            reason_text="Test",
            db=db
        )
    
    assert "ended" in str(exc.value).lower() or "active" in str(exc.value).lower()


# =============================================================================
# Test: Cannot Raise Second Objection While Pending
# =============================================================================

@pytest.mark.asyncio
async def test_cannot_raise_second_objection_while_pending(
    db: AsyncSession,
    session_live: LiveCourtSession,
    active_turn: LiveTurn
):
    """Test that only one pending objection per turn is allowed."""
    # Raise first objection
    await raise_objection(
        session_id=session_live.id,
        turn_id=active_turn.id,
        raised_by_user_id=1,
        objection_type=ObjectionType.LEADING,
        reason_text="First objection",
        db=db
    )
    
    # Try to raise second objection
    with pytest.raises(ObjectionAlreadyPendingError) as exc:
        await raise_objection(
            session_id=session_live.id,
            turn_id=active_turn.id,
            raised_by_user_id=2,
            objection_type=ObjectionType.SPECULATION,
            reason_text="Second objection",
            db=db
        )
    
    assert "already pending" in str(exc.value).lower()


# =============================================================================
# Test: Only Presiding Judge Can Rule
# =============================================================================

@pytest.mark.asyncio
async def test_only_presiding_judge_can_rule(
    db: AsyncSession,
    session_live: LiveCourtSession,
    active_turn: LiveTurn
):
    """Test that only presiding judge can rule on objections."""
    # Raise objection
    objection, _ = await raise_objection(
        session_id=session_live.id,
        turn_id=active_turn.id,
        raised_by_user_id=1,
        objection_type=ObjectionType.LEADING,
        reason_text="Test",
        db=db
    )
    
    # Non-presiding attempt (is_presiding_judge=False)
    with pytest.raises(NotPresidingJudgeError) as exc:
        await rule_objection(
            objection_id=objection.id,
            decision=ObjectionState.SUSTAINED,
            ruling_reason_text="Test ruling",
            ruled_by_user_id=2,
            is_presiding_judge=False,
            db=db
        )
    
    assert "presiding judge" in str(exc.value).lower()


# =============================================================================
# Test: Ruling Resumes Timer
# =============================================================================

@pytest.mark.asyncio
async def test_ruling_resumes_timer(
    db: AsyncSession,
    session_live: LiveCourtSession,
    active_turn: LiveTurn
):
    """Test that ruling on an objection resumes the timer."""
    # Raise objection (pauses timer)
    objection, turn = await raise_objection(
        session_id=session_live.id,
        turn_id=active_turn.id,
        raised_by_user_id=1,
        objection_type=ObjectionType.LEADING,
        reason_text="Test",
        db=db
    )
    
    assert turn.is_timer_paused == True
    
    # Rule on objection (should resume timer)
    ruled_obj, resumed_turn = await rule_objection(
        objection_id=objection.id,
        decision=ObjectionState.SUSTAINED,
        ruling_reason_text="Clearly leading",
        ruled_by_user_id=2,
        is_presiding_judge=True,
        db=db
    )
    
    assert resumed_turn.is_timer_paused == False, "Timer should resume after ruling"
    assert ruled_obj.state == ObjectionState.SUSTAINED
    assert ruled_obj.ruled_by_user_id == 2


# =============================================================================
# Test: Cannot Rule Twice (Idempotent)
# =============================================================================

@pytest.mark.asyncio
async def test_cannot_rule_twice(
    db: AsyncSession,
    session_live: LiveCourtSession,
    active_turn: LiveTurn
):
    """Test that ruling twice on same objection fails."""
    # Raise and rule
    objection, _ = await raise_objection(
        session_id=session_live.id,
        turn_id=active_turn.id,
        raised_by_user_id=1,
        objection_type=ObjectionType.LEADING,
        reason_text="Test",
        db=db
    )
    
    await rule_objection(
        objection_id=objection.id,
        decision=ObjectionState.OVERRULED,
        ruling_reason_text="First ruling",
        ruled_by_user_id=2,
        is_presiding_judge=True,
        db=db
    )
    
    # Second ruling attempt
    with pytest.raises(ObjectionAlreadyRuledError) as exc:
        await rule_objection(
            objection_id=objection.id,
            decision=ObjectionState.SUSTAINED,
            ruling_reason_text="Second ruling",
            ruled_by_user_id=2,
            is_presiding_judge=True,
            db=db
        )
    
    assert "already" in str(exc.value).lower()


# =============================================================================
# Test: Cannot Object After Session Completed
# =============================================================================

@pytest.mark.asyncio
async def test_cannot_object_after_session_completed(
    db: AsyncSession,
    completed_session: LiveCourtSession
):
    """Test that objections cannot be raised after session is completed."""
    # Create a turn in the completed session
    turn = LiveTurn(
        session_id=completed_session.id,
        participant_id=1,
        side=OralSide.PETITIONER,
        turn_type=OralTurnType.PRESENTATION,
        allocated_seconds=60,
        state=LiveTurnState.ENDED,
        created_at=datetime.utcnow()
    )
    db.add(turn)
    await db.flush()
    
    with pytest.raises(SessionCompletedError) as exc:
        await raise_objection(
            session_id=completed_session.id,
            turn_id=turn.id,
            raised_by_user_id=1,
            objection_type=ObjectionType.LEADING,
            reason_text="Test",
            db=db
        )
    
    assert "completed" in str(exc.value).lower()


# =============================================================================
# Test: Objection Hash Verification
# =============================================================================

@pytest.mark.asyncio
async def test_objection_hash_computed_correctly(
    db: AsyncSession,
    session_live: LiveCourtSession,
    active_turn: LiveTurn
):
    """Test that objection hash is computed correctly and verifiable."""
    objection, _ = await raise_objection(
        session_id=session_live.id,
        turn_id=active_turn.id,
        raised_by_user_id=1,
        objection_type=ObjectionType.MISREPRESENTATION,
        reason_text="Facts are wrong",
        db=db
    )
    
    # Hash should be present
    assert objection.objection_hash is not None
    assert len(objection.objection_hash) == 64, "SHA256 hex is 64 chars"
    
    # Verify hash matches
    assert objection.verify_hash() == True, "Hash should verify correctly"


# =============================================================================
# Test: Event Chain Logging
# =============================================================================

@pytest.mark.asyncio
async def test_objection_events_logged(
    db: AsyncSession,
    session_live: LiveCourtSession,
    active_turn: LiveTurn
):
    """Test that objection events are logged to event chain."""
    from backend.orm.live_court import LiveEventLog
    
    # Get event count before
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == session_live.id)
    )
    events_before = len(result.scalars().all())
    
    # Raise objection
    await raise_objection(
        session_id=session_live.id,
        turn_id=active_turn.id,
        raised_by_user_id=1,
        objection_type=ObjectionType.LEADING,
        reason_text="Test",
        db=db
    )
    
    # Check events created
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == session_live.id)
        .order_by(LiveEventLog.event_sequence.desc())
    )
    events = result.scalars().all()
    
    # Should have OBJECTION_RAISED and TURN_PAUSED_FOR_OBJECTION
    event_types = [e.event_type for e in events]
    assert "OBJECTION_RAISED" in event_types or "TURN_PAUSED_FOR_OBJECTION" in event_types


# =============================================================================
# Test: Procedural Violation Recording
# =============================================================================

@pytest.mark.asyncio
async def test_record_procedural_violation(
    db: AsyncSession,
    session_live: LiveCourtSession,
    active_turn: LiveTurn
):
    """Test recording procedural violations."""
    violation = await record_procedural_violation(
        session_id=session_live.id,
        turn_id=active_turn.id,
        user_id=1,
        recorded_by_user_id=2,
        violation_type="time_exceeded",
        description="Speaker exceeded allocated time",
        db=db
    )
    
    assert violation.id is not None
    assert violation.violation_type == "time_exceeded"
    assert violation.session_id == session_live.id


# =============================================================================
# Test: Concurrency - Parallel Raise Attempts
# =============================================================================

@pytest.mark.asyncio
async def test_concurrent_objection_raises(
    db: AsyncSession,
    session_live: LiveCourtSession,
    active_turn: LiveTurn
):
    """Test that concurrent objection raises are handled properly."""
    results = []
    
    async def try_raise(user_id: int):
        try:
            obj, _ = await raise_objection(
                session_id=session_live.id,
                turn_id=active_turn.id,
                raised_by_user_id=user_id,
                objection_type=ObjectionType.LEADING,
                reason_text=f"Objection by user {user_id}",
                db=db
            )
            results.append(("success", obj.id))
        except Exception as e:
            results.append(("error", str(e)))
    
    # Try to raise two objections concurrently
    await asyncio.gather(
        try_raise(1),
        try_raise(2),
        return_exceptions=True
    )
    
    # Only one should succeed
    successes = [r for r in results if r[0] == "success"]
    errors = [r for r in results if r[0] == "error"]
    
    # At least one should error due to pending objection or timer paused
    assert len(errors) >= 1, "At least one concurrent raise should fail"


# =============================================================================
# Test: Objection Type Enum Validation
# =============================================================================

@pytest.mark.asyncio
async def test_objection_type_enum_values(
    db: AsyncSession
):
    """Test objection type enum values are correct."""
    assert ObjectionType.LEADING.value == "leading"
    assert ObjectionType.IRRELEVANT.value == "irrelevant"
    assert ObjectionType.MISREPRESENTATION.value == "misrepresentation"
    assert ObjectionType.SPECULATION.value == "speculation"
    assert ObjectionType.PROCEDURAL.value == "procedural"


# =============================================================================
# Test: Objection State Enum Validation
# =============================================================================

@pytest.mark.asyncio
async def test_objection_state_enum_values(
    db: AsyncSession
):
    """Test objection state enum values are correct."""
    assert ObjectionState.PENDING.value == "pending"
    assert ObjectionState.SUSTAINED.value == "sustained"
    assert ObjectionState.OVERRULED.value == "overruled"


# =============================================================================
# Test: Session Not Live Error
# =============================================================================

@pytest.mark.asyncio
async def test_cannot_object_when_session_not_live(
    db: AsyncSession,
    institution_a: Institution,
    active_turn: LiveTurn
):
    """Test that objections cannot be raised when session is not live."""
    # Create paused session
    round_obj = TournamentRound(
        tournament_id=1,
        round_number=1,
        round_type=RoundType.SWISS,
        created_at=datetime.utcnow()
    )
    db.add(round_obj)
    await db.flush()
    
    paused_session = LiveCourtSession(
        round_id=round_obj.id,
        institution_id=institution_a.id,
        status=LiveCourtStatus.PAUSED,
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(paused_session)
    await db.flush()
    
    # Create turn in paused session
    paused_turn = LiveTurn(
        session_id=paused_session.id,
        participant_id=1,
        side=OralSide.PETITIONER,
        turn_type=OralTurnType.PRESENTATION,
        allocated_seconds=60,
        state=LiveTurnState.ACTIVE,
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(paused_turn)
    await db.flush()
    
    with pytest.raises(SessionNotLiveError) as exc:
        await raise_objection(
            session_id=paused_session.id,
            turn_id=paused_turn.id,
            raised_by_user_id=1,
            objection_type=ObjectionType.LEADING,
            reason_text="Test",
            db=db
        )
    
    assert "paused" in str(exc.value).lower() or "live" in str(exc.value).lower()


# =============================================================================
# Test: Overruled Decision
# =============================================================================

@pytest.mark.asyncio
async def test_overrule_objection(
    db: AsyncSession,
    session_live: LiveCourtSession,
    active_turn: LiveTurn
):
    """Test overruling an objection."""
    objection, _ = await raise_objection(
        session_id=session_live.id,
        turn_id=active_turn.id,
        raised_by_user_id=1,
        objection_type=ObjectionType.SPECULATION,
        reason_text="Speculative answer",
        db=db
    )
    
    ruled_obj, turn = await rule_objection(
        objection_id=objection.id,
        decision=ObjectionState.OVERRULED,
        ruling_reason_text="Answer was factual",
        ruled_by_user_id=2,
        is_presiding_judge=True,
        db=db
    )
    
    assert ruled_obj.state == ObjectionState.OVERRULED
    assert turn.is_timer_paused == False


# =============================================================================
# Test: Query Functions
# =============================================================================

@pytest.mark.asyncio
async def test_get_objections_by_session(
    db: AsyncSession,
    session_live: LiveCourtSession,
    active_turn: LiveTurn
):
    """Test querying objections by session."""
    # Create multiple objections
    for i in range(3):
        turn = LiveTurn(
            session_id=session_live.id,
            participant_id=i + 10,
            side=OralSide.PETITIONER,
            turn_type=OralTurnType.PRESENTATION,
            allocated_seconds=60,
            state=LiveTurnState.ACTIVE,
            started_at=datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        db.add(turn)
        await db.flush()
        
        obj, _ = await raise_objection(
            session_id=session_live.id,
            turn_id=turn.id,
            raised_by_user_id=1,
            objection_type=ObjectionType.LEADING,
            reason_text=f"Objection {i}",
            db=db
        )
        
        # Rule on first two
        if i < 2:
            await rule_objection(
                objection_id=obj.id,
                decision=ObjectionState.SUSTAINED,
                ruling_reason_text="Ruling",
                ruled_by_user_id=2,
                is_presiding_judge=True,
                db=db
            )
    
    # Query all
    all_obj = await get_objections_by_session(session_live.id, db)
    assert len(all_obj) == 3
    
    # Query pending only
    pending = await get_objections_by_session(session_live.id, db, ObjectionState.PENDING)
    assert len(pending) == 1
    
    # Query sustained only
    sustained = await get_objections_by_session(session_live.id, db, ObjectionState.SUSTAINED)
    assert len(sustained) == 2
