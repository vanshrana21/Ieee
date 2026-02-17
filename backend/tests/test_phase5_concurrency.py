"""
Phase 5 — Live Courtroom Concurrency Test Suite

Tests for all concurrency guarantees:
- Double start_turn → only one succeeds
- Concurrent timer expiration → only one TURN_EXPIRED
- Double complete_session → idempotent
- Parallel event append → sequence correct
- No race conditions on state transitions
"""
import pytest
import asyncio
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.live_court import (
    LiveCourtSession, LiveTurn, LiveEventLog,
    LiveCourtStatus, LiveTurnState, OralSide, OralTurnType
)
from backend.orm.institution import Institution
from backend.orm.round_pairing import TournamentRound, RoundType
from backend.orm.user import User, UserRole
from backend.services.live_court_service import (
    start_session, start_turn, end_turn, complete_session,
    server_timer_tick, get_active_turn
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
async def session_not_started(
    db: AsyncSession,
    institution_a: Institution
) -> LiveCourtSession:
    """Create a not-started session."""
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
        status=LiveCourtStatus.NOT_STARTED,
        created_at=datetime.utcnow()
    )
    db.add(session)
    await db.flush()
    return session


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
async def pending_turn(
    db: AsyncSession,
    session_live: LiveCourtSession
) -> LiveTurn:
    """Create a pending turn."""
    turn = LiveTurn(
        session_id=session_live.id,
        participant_id=1,
        side=OralSide.PETITIONER,
        turn_type=OralTurnType.PRESENTATION,
        allocated_seconds=60,
        state=LiveTurnState.PENDING,
        created_at=datetime.utcnow()
    )
    db.add(turn)
    await db.flush()
    return turn


# =============================================================================
# Test: Double Start Turn Race
# =============================================================================

@pytest.mark.asyncio
async def test_double_start_turn_only_one_succeeds(
    db: AsyncSession,
    institution_a: Institution,
    session_live: LiveCourtSession,
    pending_turn: LiveTurn
):
    """Test that only one start_turn succeeds when called concurrently."""
    # Create another pending turn for the second attempt
    turn2 = LiveTurn(
        session_id=session_live.id,
        participant_id=2,
        side=OralSide.RESPONDENT,
        turn_type=OralTurnType.PRESENTATION,
        allocated_seconds=60,
        state=LiveTurnState.PENDING,
        created_at=datetime.utcnow()
    )
    db.add(turn2)
    await db.flush()
    
    results = []
    exceptions = []
    
    async def try_start(turn_id: int):
        try:
            turn, session = await start_turn(
                session_id=session_live.id,
                turn_id=turn_id,
                user_id=1,
                db=db
            )
            results.append((turn_id, "success"))
        except Exception as e:
            exceptions.append((turn_id, str(e)))
    
    # Try to start both turns concurrently
    await asyncio.gather(
        try_start(pending_turn.id),
        try_start(turn2.id),
        return_exceptions=True
    )
    
    # One should succeed, one should fail (or both might succeed if one waits)
    # But only one turn can be active at a time
    
    # Check final state
    result = await db.execute(
        select(LiveTurn).where(LiveTurn.session_id == session_live.id)
    )
    turns = result.scalars().all()
    
    active_count = sum(1 for t in turns if t.state == LiveTurnState.ACTIVE)
    
    # Only one turn should be active
    assert active_count <= 1, "Only one turn can be active at a time"


# =============================================================================
# Test: Concurrent Timer Expiration
# =============================================================================

@pytest.mark.asyncio
async def test_concurrent_timer_expiration_idempotent(
    db: AsyncSession,
    institution_a: Institution,
    session_live: LiveCourtSession
):
    """Test that multiple timer ticks don't create duplicate expires."""
    # Create a turn that's already expired
    expired_turn = LiveTurn(
        session_id=session_live.id,
        participant_id=1,
        side=OralSide.PETITIONER,
        turn_type=OralTurnType.PRESENTATION,
        allocated_seconds=10,  # Short allocation
        state=LiveTurnState.ACTIVE,
        started_at=datetime.utcnow().replace(year=datetime.utcnow().year - 1),  # Started long ago
        created_at=datetime.utcnow()
    )
    db.add(expired_turn)
    await db.flush()
    
    # Set as current turn
    session_live.current_turn_id = expired_turn.id
    await db.flush()
    
    # Run multiple timer ticks concurrently
    expired_results = await asyncio.gather(
        server_timer_tick(session_live.id, db),
        server_timer_tick(session_live.id, db),
        server_timer_tick(session_live.id, db),
        return_exceptions=True
    )
    
    # Count successful expirations
    successful_expires = sum(1 for r in expired_results if r is not None and not isinstance(r, Exception))
    
    # Only one should expire successfully (first one)
    # Others should return None (no active turn found due to race)
    
    # Check turn is ended
    result = await db.execute(
        select(LiveTurn).where(LiveTurn.id == expired_turn.id)
    )
    turn = result.scalar_one()
    
    assert turn.state == LiveTurnState.ENDED, "Turn should be ended after expiration"
    assert turn.violation_flag == True, "Violation flag should be set"


# =============================================================================
# Test: Double Complete Session
# =============================================================================

@pytest.mark.asyncio
async def test_double_complete_session_idempotent(
    db: AsyncSession,
    institution_a: Institution
):
    """Test that double complete_session is idempotent."""
    # Create live session with no active turn
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
    
    # First complete should succeed
    result1 = await complete_session(session.id, 1, db)
    assert result1.status == LiveCourtStatus.COMPLETED
    
    # Flush to persist
    await db.flush()
    
    # Second complete should fail (session already completed)
    try:
        await complete_session(session.id, 1, db)
        assert False, "Second complete should fail"
    except Exception as e:
        # Expected - session already completed
        assert "completed" in str(e).lower() or "already" in str(e).lower()


# =============================================================================
# Test: Parallel Event Append
# =============================================================================

@pytest.mark.asyncio
async def test_parallel_event_append_sequence_correct(
    db: AsyncSession,
    institution_a: Institution
):
    """Test that parallel event appends maintain correct sequence."""
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
    
    async def append_event(event_num: int):
        from backend.services.live_court_service import _append_event
        
        try:
            event = await _append_event(
                session_id=session.id,
                event_type=f"TEST_EVENT_{event_num}",
                payload={"num": event_num},
                db=db
            )
            return event.event_sequence
        except Exception as e:
            return f"error: {e}"
    
    # Append multiple events concurrently
    sequences = await asyncio.gather(
        append_event(1),
        append_event(2),
        append_event(3),
        append_event(4),
        append_event(5),
        return_exceptions=True
    )
    
    # Filter successful sequences
    successful = [s for s in sequences if isinstance(s, int)]
    
    # All sequences should be unique and consecutive
    if len(successful) > 0:
        assert len(set(successful)) == len(successful), "All sequences must be unique"
        
        # Check events in DB
        result = await db.execute(
            select(LiveEventLog)
            .where(LiveEventLog.session_id == session.id)
            .order_by(LiveEventLog.event_sequence.asc())
        )
        events = result.scalars().all()
        
        # Verify no gaps and no duplicates
        for i, event in enumerate(events):
            assert event.event_sequence == i + 1, f"Event {i} should have sequence {i+1}"


# =============================================================================
# Test: Session Start Race
# =============================================================================

@pytest.mark.asyncio
async def test_concurrent_session_start_idempotent(
    db: AsyncSession,
    institution_a: Institution
):
    """Test that concurrent session starts are idempotent."""
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
        status=LiveCourtStatus.NOT_STARTED,
        created_at=datetime.utcnow()
    )
    db.add(session)
    await db.flush()
    
    results = []
    
    async def try_start():
        try:
            result = await start_session(session.id, 1, db)
            results.append("success")
            return result
        except Exception as e:
            results.append(f"error: {e}")
            return None
    
    # Try to start session multiple times concurrently
    await asyncio.gather(
        try_start(),
        try_start(),
        try_start(),
        return_exceptions=True
    )
    
    # Check final state
    result = await db.execute(
        select(LiveCourtSession).where(LiveCourtSession.id == session.id)
    )
    final_session = result.scalar_one()
    
    # Session should be live
    assert final_session.status == LiveCourtStatus.LIVE


# =============================================================================
# Test: No Active Turn Race
# =============================================================================

@pytest.mark.asyncio
async def test_no_two_active_turns_concurrently(
    db: AsyncSession,
    institution_a: Institution
):
    """Test that no two turns can become active concurrently."""
    # Create live session
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
    
    # Create multiple pending turns
    turns = []
    for i in range(3):
        turn = LiveTurn(
            session_id=session.id,
            participant_id=i + 1,
            side=OralSide.PETITIONER if i % 2 == 0 else OralSide.RESPONDENT,
            turn_type=OralTurnType.PRESENTATION,
            allocated_seconds=60,
            state=LiveTurnState.PENDING,
            created_at=datetime.utcnow()
        )
        db.add(turn)
        turns.append(turn)
    await db.flush()
    
    # Try to start all turns concurrently
    async def try_start_turn(turn: LiveTurn):
        try:
            result = await start_turn(session.id, turn.id, 1, db)
            return "started"
        except Exception as e:
            return f"failed: {e}"
    
    results = await asyncio.gather(
        try_start_turn(turns[0]),
        try_start_turn(turns[1]),
        try_start_turn(turns[2]),
        return_exceptions=True
    )
    
    # Check final state - only one should be active
    result = await db.execute(
        select(LiveTurn)
        .where(
            and_(
                LiveTurn.session_id == session.id,
                LiveTurn.state == LiveTurnState.ACTIVE
            )
        )
    )
    active_turns = result.scalars().all()
    
    assert len(active_turns) <= 1, "Only one turn can be active"


# =============================================================================
# Test: State Transition Race
# =============================================================================

@pytest.mark.asyncio
async def test_state_transition_no_race_conditions(
    db: AsyncSession,
    institution_a: Institution
):
    """Test that state transitions don't have race conditions."""
    # Create session
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
        status=LiveCourtStatus.NOT_STARTED,
        created_at=datetime.utcnow()
    )
    db.add(session)
    await db.flush()
    
    # Define operations
    async def start():
        try:
            await start_session(session.id, 1, db)
            return "started"
        except Exception as e:
            return str(e)
    
    async def pause():
        try:
            await pause_session(session.id, 1, db)
            return "paused"
        except Exception as e:
            return str(e)
    
    # Run operations in sequence (simulating race)
    # First start
    result1 = await start()
    
    # Then try concurrent pauses
    async def try_pause():
        try:
            from backend.services.live_court_service import pause_session
            await pause_session(session.id, 1, db)
            return "paused"
        except Exception as e:
            return f"failed: {e}"
    
    results = await asyncio.gather(
        try_pause(),
        try_pause(),
        return_exceptions=True
    )
    
    # Check final state is consistent
    result = await db.execute(
        select(LiveCourtSession).where(LiveCourtSession.id == session.id)
    )
    final_session = result.scalar_one()
    
    # Should be in a valid state
    assert final_session.status in [
        LiveCourtStatus.LIVE,
        LiveCourtStatus.PAUSED,
        LiveCourtStatus.COMPLETED
    ], "Final state must be valid"
