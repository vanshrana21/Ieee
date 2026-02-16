"""
Phase 5 — Live Courtroom Tamper Detection Test Suite

Tests for all tamper detection scenarios:
- Event hash mismatch detected
- Event row deletion detected
- Event sequence reordering detected
- Payload modification detected
- Previous hash chain break detected
"""
import pytest
from datetime import datetime
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.live_court import (
    LiveCourtSession, LiveTurn, LiveEventLog,
    LiveCourtStatus, LiveTurnState, OralSide, OralTurnType
)
from backend.orm.national_network import Institution
from backend.orm.round_pairing import TournamentRound, RoundType
from backend.services.live_court_service import (
    verify_event_chain, start_session, start_turn, end_turn,
    complete_session
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def tamper_test_session(db: AsyncSession) -> LiveCourtSession:
    """Create a session with event chain for tamper testing."""
    inst = Institution(
        name="Tamper Test College",
        code="TTC001",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(inst)
    await db.flush()
    
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
        institution_id=inst.id,
        status=LiveCourtStatus.LIVE,
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(session)
    await db.flush()
    
    # Create event chain
    previous_hash = "0" * 64
    
    for i in range(5):
        event = LiveEventLog(
            session_id=session.id,
            event_sequence=i + 1,
            event_type=f"TEST_EVENT_{i+1}",
            event_payload_json={"index": i + 1, "data": f"event_{i+1}"},
            previous_hash=previous_hash,
            event_hash=LiveEventLog.compute_event_hash(
                previous_hash=previous_hash,
                event_sequence=i + 1,
                event_type=f"TEST_EVENT_{i+1}",
                payload={"index": i + 1, "data": f"event_{i+1}"},
                created_at=datetime.utcnow()
            ),
            created_at=datetime.utcnow()
        )
        db.add(event)
        previous_hash = event.event_hash
    
    await db.flush()
    return session


# =============================================================================
# Test: Event Hash Mismatch
# =============================================================================

@pytest.mark.asyncio
async def test_verify_detects_event_hash_mismatch(
    db: AsyncSession,
    tamper_test_session: LiveCourtSession
):
    """Test that verification detects tampered event hash."""
    # Get an event
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == tamper_test_session.id)
        .where(LiveEventLog.event_sequence == 3)
    )
    event = result.scalar_one()
    
    # Tamper with the hash
    original_hash = event.event_hash
    event.event_hash = "tampered" + "0" * 56  # Invalid hash
    
    await db.flush()
    
    # Verify should detect tampering
    result = await verify_event_chain(tamper_test_session.id, db)
    
    assert result["found"] is True
    assert result["valid"] is False
    assert result["tamper_detected"] is True
    assert len(result["tampered_events"]) > 0
    
    # Check the specific tampering detected
    tampered = result["tampered_events"][0]
    assert tampered["event_sequence"] == 3
    assert "hash mismatch" in tampered["issue"].lower() or "mismatch" in tampered["issue"].lower()


# =============================================================================
# Test: Event Row Deletion
# =============================================================================

@pytest.mark.asyncio
async def test_verify_detects_deleted_event(
    db: AsyncSession,
    tamper_test_session: LiveCourtSession
):
    """Test that verification detects missing (deleted) events."""
    # Delete an event
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == tamper_test_session.id)
        .where(LiveEventLog.event_sequence == 3)
    )
    event = result.scalar_one()
    
    await db.delete(event)
    await db.flush()
    
    # Verify should detect missing event
    result = await verify_event_chain(tamper_test_session.id, db)
    
    assert result["found"] is True
    assert result["valid"] is False
    assert result["tamper_detected"] is True


# =============================================================================
# Test: Event Sequence Reordering
# =============================================================================

@pytest.mark.asyncio
async def test_verify_detects_sequence_gap(
    db: AsyncSession,
    tamper_test_session: LiveCourtSession
):
    """Test that verification detects sequence gaps."""
    # Get event 3
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == tamper_test_session.id)
        .where(LiveEventLog.event_sequence == 3)
    )
    event3 = result.scalar_one()
    
    # Change its sequence to create a gap
    event3.event_sequence = 10
    
    await db.flush()
    
    # Verify should detect gap
    result = await verify_event_chain(tamper_test_session.id, db)
    
    assert result["found"] is True
    assert result["valid"] is False
    assert result["tamper_detected"] is True


# =============================================================================
# Test: Payload Modification
# =============================================================================

@pytest.mark.asyncio
async def test_verify_detects_payload_modification(
    db: AsyncSession,
    tamper_test_session: LiveCourtSession
):
    """Test that verification detects modified payload."""
    # Get an event
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == tamper_test_session.id)
        .where(LiveEventLog.event_sequence == 2)
    )
    event = result.scalar_one()
    
    # Tamper with payload
    original_payload = event.event_payload_json
    event.event_payload_json = {"tampered": True, "original": original_payload}
    
    await db.flush()
    
    # Verify should detect payload tampering (via hash mismatch)
    result = await verify_event_chain(tamper_test_session.id, db)
    
    assert result["found"] is True
    assert result["valid"] is False
    assert result["tamper_detected"] is True


# =============================================================================
# Test: Previous Hash Chain Break
# =============================================================================

@pytest.mark.asyncio
async def test_verify_detects_chain_break(
    db: AsyncSession,
    tamper_test_session: LiveCourtSession
):
    """Test that verification detects broken hash chain."""
    # Get event 3
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == tamper_test_session.id)
        .where(LiveEventLog.event_sequence == 3)
    )
    event3 = result.scalar_one()
    
    # Break the chain by changing previous_hash
    event3.previous_hash = "broken" + "0" * 59
    
    # Recompute hash to make it "valid" for this event
    event3.event_hash = LiveEventLog.compute_event_hash(
        previous_hash=event3.previous_hash,
        event_sequence=event3.event_sequence,
        event_type=event3.event_type,
        payload=event3.event_payload_json,
        created_at=event3.created_at
    )
    
    await db.flush()
    
    # Verify should detect chain break
    result = await verify_event_chain(tamper_test_session.id, db)
    
    assert result["found"] is True
    assert result["valid"] is False
    assert result["tamper_detected"] is True
    
    # Should indicate previous hash mismatch
    tampered = result["tampered_events"][0]
    assert "chain" in tampered["issue"].lower() or "previous" in tampered["issue"].lower() or "mismatch" in tampered["issue"].lower()


# =============================================================================
# Test: Complete Valid Chain
# =============================================================================

@pytest.mark.asyncio
async def test_verify_valid_chain_passes(
    db: AsyncSession,
    tamper_test_session: LiveCourtSession
):
    """Test that a valid chain passes verification."""
    # Verify the untouched chain
    result = await verify_event_chain(tamper_test_session.id, db)
    
    assert result["found"] is True
    assert result["valid"] is True
    assert result["tamper_detected"] is False
    assert result["total_events"] == 5
    assert result["tampered_events"] is None


# =============================================================================
# Test: Single Event Chain
# =============================================================================

@pytest.mark.asyncio
async def test_verify_single_event_chain(db: AsyncSession):
    """Test verification with single event (genesis)."""
    inst = Institution(
        name="Single Event College",
        code="SEC001",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(inst)
    await db.flush()
    
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
        institution_id=inst.id,
        status=LiveCourtStatus.LIVE,
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(session)
    await db.flush()
    
    # Create single genesis event
    event = LiveEventLog(
        session_id=session.id,
        event_sequence=1,
        event_type="GENESIS",
        event_payload_json={"genesis": True},
        previous_hash="0" * 64,
        event_hash=LiveEventLog.compute_event_hash(
            previous_hash="0" * 64,
            event_sequence=1,
            event_type="GENESIS",
            payload={"genesis": True},
            created_at=datetime.utcnow()
        ),
        created_at=datetime.utcnow()
    )
    db.add(event)
    await db.flush()
    
    # Should verify successfully
    result = await verify_event_chain(session.id, db)
    
    assert result["found"] is True
    assert result["valid"] is True
    assert result["total_events"] == 1


# =============================================================================
# Test: Empty Chain
# =============================================================================

@pytest.mark.asyncio
async def test_verify_empty_chain(db: AsyncSession):
    """Test verification with no events."""
    inst = Institution(
        name="Empty Chain College",
        code="ECC001",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(inst)
    await db.flush()
    
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
        institution_id=inst.id,
        status=LiveCourtStatus.LIVE,
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(session)
    await db.flush()
    
    # Verify empty chain
    result = await verify_event_chain(session.id, db)
    
    assert result["found"] is True
    assert result["frozen"] is False
    assert result["valid"] is True
    assert result["total_events"] == 0


# =============================================================================
# Test: Session Not Found
# =============================================================================

@pytest.mark.asyncio
async def test_verify_session_not_found(db: AsyncSession):
    """Test verification for non-existent session."""
    result = await verify_event_chain(99999, db)
    
    assert result["found"] is False
    assert result["valid"] is False
    assert "not found" in result["error"].lower()


# =============================================================================
# Test: PostgreSQL Trigger Enforcement
# =============================================================================

@pytest.mark.asyncio
async def test_postgresql_trigger_blocks_event_update(
    db: AsyncSession,
    tamper_test_session: LiveCourtSession
):
    """
    Test PostgreSQL trigger blocks direct UPDATE to event log.
    
    Only runs on PostgreSQL.
    """
    # Check dialect
    result = await db.execute(text("SHOW server_version"))
    version = result.scalar()
    
    if not version or "SQLite" in str(version):
        pytest.skip("PostgreSQL-specific test")
    
    # Get an event
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == tamper_test_session.id)
        .limit(1)
    )
    event = result.scalar_one()
    
    # Try direct SQL update (should fail due to trigger)
    try:
        await db.execute(
            text(f"""
                UPDATE live_event_log 
                SET event_type = 'TAMPERED'
                WHERE id = {event.id}
            """)
        )
        await db.flush()
        pytest.fail("Expected trigger to block update")
    except Exception as e:
        assert "append-only" in str(e).lower() or "cannot modify" in str(e).lower(), \
            f"Trigger should block with append-only message: {e}"


@pytest.mark.asyncio
async def test_postgresql_trigger_blocks_event_delete(
    db: AsyncSession,
    tamper_test_session: LiveCourtSession
):
    """
    Test PostgreSQL trigger blocks direct DELETE from event log.
    
    Only runs on PostgreSQL.
    """
    # Check dialect
    result = await db.execute(text("SHOW server_version"))
    version = result.scalar()
    
    if not version or "SQLite" in str(version):
        pytest.skip("PostgreSQL-specific test")
    
    # Get an event
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == tamper_test_session.id)
        .limit(1)
    )
    event = result.scalar_one()
    
    # Try direct SQL delete (should fail due to trigger)
    try:
        await db.execute(
            text(f"""
                DELETE FROM live_event_log
                WHERE id = {event.id}
            """)
        )
        await db.flush()
        pytest.fail("Expected trigger to block delete")
    except Exception as e:
        assert "append-only" in str(e).lower() or "cannot modify" in str(e).lower(), \
            f"Trigger should block with append-only message: {e}"


# =============================================================================
# Test: Session Completed Immutability
# =============================================================================

@pytest.mark.asyncio
async def test_completed_session_blocks_turn_modification(
    db: AsyncSession
):
    """Test that completed session blocks turn modifications."""
    inst = Institution(
        name="Complete Test College",
        code="CTC001",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(inst)
    await db.flush()
    
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
        institution_id=inst.id,
        status=LiveCourtStatus.COMPLETED,
        started_at=datetime.utcnow(),
        ended_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(session)
    await db.flush()
    
    # Create a turn
    turn = LiveTurn(
        session_id=session.id,
        participant_id=1,
        side=OralSide.PETITIONER,
        turn_type=OralTurnType.PRESENTATION,
        allocated_seconds=60,
        state=LiveTurnState.ENDED,
        created_at=datetime.utcnow()
    )
    db.add(turn)
    await db.flush()
    
    # Try to modify turn (should fail at ORM/DB level)
    # Note: This test may fail on SQLite without triggers
    # but passes on PostgreSQL with triggers installed
    result = await db.execute(text("SHOW server_version"))
    version = result.scalar()
    
    if version and "SQLite" not in str(version):
        # PostgreSQL - should have trigger
        try:
            turn.allocated_seconds = 120
            await db.flush()
            # If we get here without exception, check if change was actually applied
            result = await db.execute(
                select(LiveTurn.allocated_seconds)
                .where(LiveTurn.id == turn.id)
            )
            actual = result.scalar()
            if actual == 120:
                pytest.fail("Expected trigger to block turn modification after session completed")
        except Exception as e:
            assert "completed" in str(e).lower(), f"Should block with completed message: {e}"
