"""
Phase 8 — Global Integrity Verification Test Suite

Tests for full-system integrity audit endpoint.
Verifies event chains, hash validation, and tamper detection.
"""
import pytest
import json
import hashlib
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.live_court import (
    LiveCourtSession, LiveCourtStatus, LiveEventLog, LiveEventType,
    LiveTurn, LiveTurnState, OralSide, OralTurnType
)
from backend.orm.live_objection import LiveObjection, ObjectionType, ObjectionState
from backend.orm.exhibit import SessionExhibit, ExhibitState
from backend.orm.national_network import Institution
from backend.orm.round_pairing import TournamentRound, RoundType
from backend.routes.integrity import IntegrityVerifier


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
async def session_with_events(
    db: AsyncSession,
    institution_a: Institution
) -> tuple[LiveCourtSession, list[LiveEventLog]]:
    """Create session with event chain."""
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
    
    # Create events
    events = []
    for i in range(5):
        payload = {"action": f"event_{i}", "data": i}
        payload_json = json.dumps(payload, sort_keys=True)
        
        # Compute hash
        hash_input = (
            f"{session.id}|"
            f"{LiveEventType.TURN_STARTED.value}|"
            f"{payload_json}|"
            f"{datetime.utcnow().isoformat()}"
        )
        event_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        
        event = LiveEventLog(
            session_id=session.id,
            event_type=LiveEventType.TURN_STARTED,
            event_sequence=i + 1,
            payload_json=payload_json,
            event_hash=event_hash,
            created_at=datetime.utcnow()
        )
        db.add(event)
        events.append(event)
    
    await db.flush()
    return session, events


# =============================================================================
# Test: Event Chain Continuity
# =============================================================================

@pytest.mark.asyncio
async def test_event_chain_no_gaps(db: AsyncSession, session_with_events):
    """Test that event chain has no sequence gaps."""
    session, events = session_with_events
    
    verifier = IntegrityVerifier(db)
    issues = await verifier._verify_event_chain(session.id)
    
    assert len(issues) == 0, f"Unexpected issues: {issues}"


@pytest.mark.asyncio
async def test_event_chain_detects_gap(db: AsyncSession, session_with_events):
    """Test that sequence gaps are detected."""
    session, events = session_with_events
    
    # Delete event 3 to create gap
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == session.id)
        .where(LiveEventLog.event_sequence == 3)
    )
    event_to_delete = result.scalar_one()
    await db.delete(event_to_delete)
    await db.flush()
    
    verifier = IntegrityVerifier(db)
    issues = await verifier._verify_event_chain(session.id)
    
    assert len(issues) > 0
    assert any("Sequence gap" in issue for issue in issues)


# =============================================================================
# Test: Event Hash Validation
# =============================================================================

@pytest.mark.asyncio
async def test_valid_event_hashes(db: AsyncSession, session_with_events):
    """Test that valid event hashes pass verification."""
    session, events = session_with_events
    
    verifier = IntegrityVerifier(db)
    issues = await verifier._verify_event_chain(session.id)
    
    assert len(issues) == 0


@pytest.mark.asyncio
async def test_tampered_event_hash_detected(db: AsyncSession, session_with_events):
    """Test that tampered event hashes are detected."""
    session, events = session_with_events
    
    # Tamper with an event hash
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == session.id)
        .where(LiveEventLog.event_sequence == 2)
    )
    event_to_tamper = result.scalar_one()
    event_to_tamper.event_hash = "tampered_hash_" * 4
    await db.flush()
    
    verifier = IntegrityVerifier(db)
    issues = await verifier._verify_event_chain(session.id)
    
    assert len(issues) > 0
    assert any("Hash mismatch" in issue for issue in issues)


@pytest.mark.asyncio
async def test_tampered_payload_detected(db: AsyncSession, session_with_events):
    """Test that tampered payloads are detected via hash mismatch."""
    session, events = session_with_events
    
    # Tamper with payload
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == session.id)
        .where(LiveEventLog.event_sequence == 2)
    )
    event_to_tamper = result.scalar_one()
    event_to_tamper.payload_json = json.dumps({"tampered": True}, sort_keys=True)
    await db.flush()
    
    verifier = IntegrityVerifier(db)
    issues = await verifier._verify_event_chain(session.id)
    
    assert len(issues) > 0
    assert any("Hash mismatch" in issue for issue in issues)


# =============================================================================
# Test: Turn State Validation
# =============================================================================

@pytest.mark.asyncio
async def test_multiple_active_turns_detected(db: AsyncSession, institution_a: Institution):
    """Test detection of multiple active turns."""
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
    
    # Create two active turns
    for i in range(2):
        turn = LiveTurn(
            session_id=session.id,
            participant_id=i + 1,
            side=OralSide.PETITIONER if i == 0 else OralSide.RESPONDENT,
            turn_type=OralTurnType.PRESENTATION,
            allocated_seconds=60,
            state=LiveTurnState.ACTIVE,
            started_at=datetime.utcnow(),
            is_timer_paused=False,
            created_at=datetime.utcnow()
        )
        db.add(turn)
    
    await db.flush()
    
    verifier = IntegrityVerifier(db)
    issues = await verifier._verify_turn_states(session.id)
    
    assert len(issues) > 0
    assert any("Multiple active turns" in issue for issue in issues)


@pytest.mark.asyncio
async def test_completed_turn_missing_ended_at(db: AsyncSession, institution_a: Institution):
    """Test detection of completed turn without ended_at."""
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
    
    turn = LiveTurn(
        session_id=session.id,
        participant_id=1,
        side=OralSide.PETITIONER,
        turn_type=OralTurnType.PRESENTATION,
        allocated_seconds=60,
        state=LiveTurnState.COMPLETED,
        started_at=datetime.utcnow(),
        ended_at=None,  # Missing!
        is_timer_paused=False,
        created_at=datetime.utcnow()
    )
    db.add(turn)
    await db.flush()
    
    verifier = IntegrityVerifier(db)
    issues = await verifier._verify_turn_states(session.id)
    
    assert len(issues) > 0
    assert any("completed but no ended_at" in issue for issue in issues)


# =============================================================================
# Test: Objection State Validation
# =============================================================================

@pytest.mark.asyncio
async def test_ruled_objection_missing_ruling_fields(
    db: AsyncSession,
    institution_a: Institution
):
    """Test detection of ruled objection without ruling fields."""
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
    
    objection = LiveObjection(
        session_id=session.id,
        turn_id=None,
        institution_id=institution_a.id,
        raised_by_user_id=1,
        raised_by_side="petitioner",
        objection_type=ObjectionType.RELEVANCE,
        state=ObjectionState.SUSTAINED,
        raised_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        # Missing ruled_at and ruled_by_user_id!
    )
    db.add(objection)
    await db.flush()
    
    verifier = IntegrityVerifier(db)
    issues = await verifier._verify_objection_states(session.id)
    
    assert len(issues) > 0


# =============================================================================
# Test: Exhibit State Validation
# =============================================================================

@pytest.mark.asyncio
async def test_marked_exhibit_missing_number(db: AsyncSession, institution_a: Institution):
    """Test detection of marked exhibit without exhibit_number."""
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
    
    exhibit = SessionExhibit(
        session_id=session.id,
        institution_id=institution_a.id,
        side="petitioner",
        exhibit_number=None,  # Missing!
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
        file_hash_sha256="a" * 64,
        state=ExhibitState.MARKED,
        marked_by_user_id=1,
        marked_at=datetime.utcnow(),
        exhibit_hash="b" * 64,
        created_at=datetime.utcnow()
    )
    db.add(exhibit)
    await db.flush()
    
    verifier = IntegrityVerifier(db)
    issues = await verifier._verify_exhibit_integrity(session.id)
    
    assert len(issues) > 0
    assert any("no exhibit_number" in issue for issue in issues)


@pytest.mark.asyncio
async def test_ruled_exhibit_missing_ruled_at(db: AsyncSession, institution_a: Institution):
    """Test detection of ruled exhibit without ruled_at."""
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
    
    exhibit = SessionExhibit(
        session_id=session.id,
        institution_id=institution_a.id,
        side="petitioner",
        exhibit_number=1,
        original_filename="test.pdf",
        file_path="/tmp/test.pdf",
        file_hash_sha256="a" * 64,
        state=ExhibitState.ADMITTED,
        marked_by_user_id=1,
        marked_at=datetime.utcnow(),
        ruled_by_user_id=2,
        ruled_at=None,  # Missing!
        exhibit_hash="b" * 64,
        created_at=datetime.utcnow()
    )
    db.add(exhibit)
    await db.flush()
    
    verifier = IntegrityVerifier(db)
    issues = await verifier._verify_exhibit_integrity(session.id)
    
    assert len(issues) > 0
    assert any("ruled but no ruled_at" in issue for issue in issues)


# =============================================================================
# Test: Full Verification Report
# =============================================================================

@pytest.mark.asyncio
async def test_full_verification_valid_system(db: AsyncSession, session_with_events):
    """Test full verification on valid system."""
    session, events = session_with_events
    
    verifier = IntegrityVerifier(db)
    result = await verifier.verify_all_sessions()
    
    assert result["sessions_checked"] >= 1
    assert result["invalid_sessions"] == []
    assert result["tamper_detected"] is False
    assert result["system_valid"] is True
    assert "checked_at" in result


@pytest.mark.asyncio
async def test_full_verification_detects_tampering(db: AsyncSession, session_with_events):
    """Test full verification detects tampering."""
    session, events = session_with_events
    
    # Tamper with an event
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == session.id)
        .where(LiveEventLog.event_sequence == 1)
    )
    event = result.scalar_one()
    event.event_hash = "tampered"
    await db.flush()
    
    verifier = IntegrityVerifier(db)
    result = await verifier.verify_all_sessions()
    
    assert result["tamper_detected"] is True
    assert result["system_valid"] is False
    assert len(result["invalid_sessions"]) > 0
    assert result["invalid_sessions"][0]["session_id"] == session.id


# =============================================================================
# Test: Invalid JSON Payload Detection
# =============================================================================

@pytest.mark.asyncio
async def test_invalid_json_payload_detected(db: AsyncSession, session_with_events):
    """Test detection of invalid JSON in payload."""
    session, events = session_with_events
    
    # Corrupt JSON payload
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == session.id)
        .where(LiveEventLog.event_sequence == 1)
    )
    event = result.scalar_one()
    event.payload_json = "not valid json {{{"
    await db.flush()
    
    verifier = IntegrityVerifier(db)
    issues = await verifier._verify_event_chain(session.id)
    
    assert len(issues) > 0
    assert any("Invalid JSON" in issue for issue in issues)
