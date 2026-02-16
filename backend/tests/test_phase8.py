"""
Phase 8 — Live Courtroom Engine Comprehensive Tests

Test coverage for:
1. Single active turn enforcement
2. Timer expiration auto end
3. Objection pauses timer
4. Judge conflict detection
5. Event hash chain verification
6. Concurrent turn start rejection
7. WebSocket reconnect replay
8. Multi-institution isolation
9. No float usage test
10. Full lifecycle integration test
"""
import asyncio
import json
import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.live_courtroom import (
    LiveCourtSession, LiveTurn, LiveObjection, LiveJudgeScore, LiveSessionEvent,
    LiveSessionStatus, LiveTurnType, ObjectionType, ObjectionStatus,
    VisibilityMode, ScoreVisibility, LiveScoreType, LiveEventType,
    compute_event_hash
)
from backend.orm.institutional_governance import Institution
from backend.orm.user import User, UserRole
from backend.orm.classroom_session import ClassroomSession, ClassroomParticipant
from backend.services.live_courtroom_service import (
    start_live_session, start_turn, get_timer_status, check_and_handle_timer_expiration,
    raise_objection, resolve_objection, submit_live_score, complete_live_session,
    check_judge_conflict, verify_live_event_chain, append_live_event,
    get_last_event_hash, LiveCourtroomError, SessionConflictError, TurnConflictError,
    ObjectionError, JudgeConflictError
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def test_institution(db: AsyncSession):
    """Create a test institution."""
    institution = Institution(
        name="Test Institution",
        slug="test-institution",
        compliance_mode="standard",
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(institution)
    await db.flush()
    return institution


@pytest.fixture
async def second_institution(db: AsyncSession):
    """Create a second test institution."""
    institution = Institution(
        name="Second Institution",
        slug="second-institution",
        compliance_mode="standard",
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(institution)
    await db.flush()
    return institution


@pytest.fixture
async def test_user(db: AsyncSession, test_institution):
    """Create a test admin user."""
    user = User(
        email="test@example.com",
        hashed_password="hashed_password",
        full_name="Test User",
        role=UserRole.teacher,
        institution_id=test_institution.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def judge_user(db: AsyncSession, test_institution):
    """Create a test judge user."""
    user = User(
        email="judge@example.com",
        hashed_password="hashed_password",
        full_name="Judge User",
        role=UserRole.teacher,
        institution_id=test_institution.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def second_judge(db: AsyncSession, second_institution):
    """Create a second judge from different institution."""
    user = User(
        email="judge2@example.com",
        hashed_password="hashed_password",
        full_name="Second Judge",
        role=UserRole.teacher,
        institution_id=second_institution.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def test_participant(db: AsyncSession, test_institution, test_user):
    """Create a test classroom participant."""
    # First create a classroom session
    from backend.orm.classroom_session import ClassroomSession
    
    session = ClassroomSession(
        name="Test Session",
        institution_id=test_institution.id,
        created_by=test_user.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(session)
    await db.flush()
    
    participant = ClassroomParticipant(
        session_id=session.id,
        user_id=test_user.id,
        side="petitioner",
        is_active=True,
        joined_at=datetime.utcnow()
    )
    db.add(participant)
    await db.flush()
    
    return participant


@pytest.fixture
async def second_participant(db: AsyncSession, test_institution, test_user):
    """Create a second test participant (respondent side)."""
    from backend.orm.classroom_session import ClassroomSession
    
    session = ClassroomSession(
        name="Test Session 2",
        institution_id=test_institution.id,
        created_by=test_user.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(session)
    await db.flush()
    
    participant = ClassroomParticipant(
        session_id=session.id,
        user_id=test_user.id,
        side="respondent",
        is_active=True,
        joined_at=datetime.utcnow()
    )
    db.add(participant)
    await db.flush()
    
    return participant


@pytest.fixture
async def live_session(db: AsyncSession, test_institution, test_user):
    """Create a test live courtroom session."""
    session = await start_live_session(
        session_id=None,
        tournament_match_id=None,
        institution_id=test_institution.id,
        created_by=test_user.id,
        db=db,
        visibility_mode=VisibilityMode.INSTITUTION,
        score_visibility=ScoreVisibility.AFTER_COMPLETION
    )
    return session


# =============================================================================
# Test 1: Single Active Turn Enforcement
# =============================================================================

@pytest.mark.asyncio
async def test_single_active_turn_enforcement(db: AsyncSession, live_session, test_participant, second_participant):
    """
    Test that only one turn can be active at a time.
    
    - Start first turn
    - Try to start second turn while first is active
    - Should raise TurnConflictError
    """
    # Start first turn
    turn1 = await start_turn(
        live_session_id=live_session.id,
        participant_id=test_participant.id,
        side="petitioner",
        turn_type=LiveTurnType.ARGUMENT,
        allocated_seconds=300,
        db=db
    )
    
    assert turn1.is_active() is True
    assert live_session.current_turn_id == turn1.id
    
    # Try to start second turn while first is active
    with pytest.raises(TurnConflictError) as exc_info:
        await start_turn(
            live_session_id=live_session.id,
            participant_id=second_participant.id,
            side="respondent",
            turn_type=LiveTurnType.ARGUMENT,
            allocated_seconds=300,
            db=db
        )
    
    assert "still active" in str(exc_info.value).lower()


# =============================================================================
# Test 2: Timer Expiration Auto End
# =============================================================================

@pytest.mark.asyncio
async def test_timer_expiration_auto_end(db: AsyncSession, live_session, test_participant):
    """
    Test that turns auto-end when time expires.
    
    - Start turn with 1 second allocation
    - Wait for expiration
    - Verify turn is ended with violation flag
    """
    # Start turn with only 1 second allocation
    turn = await start_turn(
        live_session_id=live_session.id,
        participant_id=test_participant.id,
        side="petitioner",
        turn_type=LiveTurnType.OPENING,
        allocated_seconds=1,
        db=db
    )
    
    assert turn.is_active() is True
    
    # Check timer status
    timer = await get_timer_status(turn.id, db)
    assert timer["is_active"] is True
    assert timer["allocated_seconds"] == 1
    
    # Wait for expiration (allow small buffer for test)
    await asyncio.sleep(1.5)
    
    # Check and handle expiration
    expired_turn = await check_and_handle_timer_expiration(turn.id, db)
    
    # Should be expired
    assert expired_turn is not None
    assert expired_turn.violation_flag is True
    assert expired_turn.ended_at is not None
    assert expired_turn.actual_seconds >= 1


# =============================================================================
# Test 3: Objection Pauses Timer
# =============================================================================

@pytest.mark.asyncio
async def test_objection_pauses_timer(db: AsyncSession, live_session, test_participant, second_participant, judge_user):
    """
    Test that raising an objection pauses the session.
    
    - Start turn
    - Raise objection
    - Verify session is paused
    - Resolve objection
    - Verify session resumes
    """
    # Start turn
    turn = await start_turn(
        live_session_id=live_session.id,
        participant_id=test_participant.id,
        side="petitioner",
        turn_type=LiveTurnType.ARGUMENT,
        allocated_seconds=300,
        db=db
    )
    
    # Reload session to get fresh state
    result = await db.execute(
        select(LiveCourtSession).where(LiveCourtSession.id == live_session.id)
    )
    session = result.scalar_one()
    assert session.status == LiveSessionStatus.LIVE
    
    # Raise objection from opposing side
    objection = await raise_objection(
        live_turn_id=turn.id,
        raised_by_participant_id=second_participant.id,
        objection_type=ObjectionType.LEADING,
        db=db
    )
    
    assert objection.status == ObjectionStatus.PENDING
    
    # Reload session
    result = await db.execute(
        select(LiveCourtSession).where(LiveCourtSession.id == live_session.id)
    )
    session = result.scalar_one()
    assert session.status == LiveSessionStatus.PAUSED
    
    # Reload turn
    result = await db.execute(
        select(LiveTurn).where(LiveTurn.id == turn.id)
    )
    turn = result.scalar_one()
    assert turn.is_interrupted is True
    
    # Resolve objection
    resolved = await resolve_objection(
        objection_id=objection.id,
        judge_id=judge_user.id,
        status=ObjectionStatus.OVERRULED,
        db=db
    )
    
    assert resolved.status == ObjectionStatus.OVERRULED
    
    # Reload session - should be resumed
    result = await db.execute(
        select(LiveCourtSession).where(LiveCourtSession.id == live_session.id)
    )
    session = result.scalar_one()
    assert session.status == LiveSessionStatus.LIVE


# =============================================================================
# Test 4: Judge Conflict Detection
# =============================================================================

@pytest.mark.asyncio
async def test_judge_conflict_detection(db: AsyncSession, test_institution, second_institution, test_user, test_participant):
    """
    Test that judges cannot score participants from their own institution.
    
    - Create tournament match with teams from different institutions
    - Try to assign judge from same institution as participant
    - Should raise JudgeConflictError
    """
    # Create a tournament match scenario
    # For this test, we'll simulate by checking the conflict detection function
    
    # Create a live session linked to a tournament match
    from backend.orm.national_network import NationalTournament, TournamentMatch, TournamentTeam
    
    # Create tournament
    tournament = NationalTournament(
        name="Conflict Test Tournament",
        slug="conflict-test",
        host_institution_id=test_institution.id,
        format="swiss",
        status="in_progress",
        registration_opens_at=datetime.utcnow(),
        registration_closes_at=datetime.utcnow() + timedelta(days=1),
        tournament_starts_at=datetime.utcnow(),
        created_by=test_user.id,
        created_at=datetime.utcnow()
    )
    db.add(tournament)
    await db.flush()
    
    # Create teams
    team1 = TournamentTeam(
        tournament_id=tournament.id,
        institution_id=test_institution.id,
        team_name="Host Team",
        members_json='[]',
        is_active=True,
        registered_by=test_user.id,
        registered_at=datetime.utcnow()
    )
    db.add(team1)
    
    team2 = TournamentTeam(
        tournament_id=tournament.id,
        institution_id=second_institution.id,
        team_name="Guest Team",
        members_json='[]',
        is_active=True,
        registered_by=test_user.id,
        registered_at=datetime.utcnow()
    )
    db.add(team2)
    await db.flush()
    
    # Create match
    match = TournamentMatch(
        round_id=1,
        tournament_id=tournament.id,
        petitioner_team_id=team1.id,
        respondent_team_id=team2.id,
        status="live",
        created_at=datetime.utcnow()
    )
    db.add(match)
    await db.flush()
    
    # Create live session for this match
    live_session = await start_live_session(
        session_id=None,
        tournament_match_id=match.id,
        institution_id=test_institution.id,
        created_by=test_user.id,
        db=db
    )
    
    # Check conflict for judge from same institution as team1
    has_conflict = await check_judge_conflict(live_session.id, test_user.id, db)
    assert has_conflict is True
    
    # Create judge from different institution
    other_judge = User(
        email="other@example.com",
        hashed_password="hashed",
        full_name="Other Judge",
        role=UserRole.teacher,
        institution_id=second_institution.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(other_judge)
    await db.flush()
    
    # Check conflict for judge from different institution
    has_conflict = await check_judge_conflict(live_session.id, other_judge.id, db)
    assert has_conflict is False


# =============================================================================
# Test 5: Event Hash Chain Verification
# =============================================================================

@pytest.mark.asyncio
async def test_event_hash_chain_verification(db: AsyncSession, live_session, test_user):
    """
    Test that event hash chain is correctly formed and verifiable.
    
    - Append multiple events
    - Verify chain integrity
    - Verify hashes are deterministic
    """
    # Append several events
    events = []
    for i in range(3):
        event = await append_live_event(
            live_session_id=live_session.id,
            event_type=LiveEventType.TURN_STARTED,
            event_payload={"test_index": i, "data": f"test_{i}"},
            db=db
        )
        events.append(event)
    
    # Verify chain integrity
    verification = await verify_live_event_chain(live_session.id, db)
    
    assert verification["is_valid"] is True
    assert verification["total_events"] == 3
    assert len(verification["invalid_events"]) == 0
    
    # Verify individual event hashes
    assert events[0].previous_hash == "GENESIS"
    assert events[1].previous_hash == events[0].event_hash
    assert events[2].previous_hash == events[1].event_hash
    
    # Verify hash computation is deterministic
    for event in events:
        assert event.verify_hash() is True
    
    # Test hash computation directly
    hash1 = compute_event_hash("GENESIS", {"test": "data"}, "2026-02-14T10:00:00")
    hash2 = compute_event_hash("GENESIS", {"test": "data"}, "2026-02-14T10:00:00")
    assert hash1 == hash2  # Deterministic
    assert len(hash1) == 64  # SHA256 hex length


# =============================================================================
# Test 6: Concurrent Turn Start Rejection
# =============================================================================

@pytest.mark.asyncio
async def test_concurrent_turn_start_rejection(db: AsyncSession, live_session, test_participant, second_participant):
    """
    Test that concurrent turn starts are properly rejected.
    
    This simulates a race condition where two clients try to start turns simultaneously.
    Only one should succeed.
    """
    # Start first turn
    turn1 = await start_turn(
        live_session_id=live_session.id,
        participant_id=test_participant.id,
        side="petitioner",
        turn_type=LiveTurnType.ARGUMENT,
        allocated_seconds=300,
        db=db
    )
    
    assert turn1 is not None
    
    # Try to start second turn immediately (should fail)
    with pytest.raises(TurnConflictError):
        await start_turn(
            live_session_id=live_session.id,
            participant_id=second_participant.id,
            side="respondent",
            turn_type=LiveTurnType.ARGUMENT,
            allocated_seconds=300,
            db=db
        )
    
    # End first turn
    turn1.ended_at = datetime.utcnow()
    turn1.actual_seconds = 30
    await db.flush()
    
    # Now second turn should succeed
    turn2 = await start_turn(
        live_session_id=live_session.id,
        participant_id=second_participant.id,
        side="respondent",
        turn_type=LiveTurnType.ARGUMENT,
        allocated_seconds=300,
        db=db
    )
    
    assert turn2 is not None
    assert turn2.id != turn1.id


# =============================================================================
# Test 7: WebSocket Reconnect Replay
# =============================================================================

@pytest.mark.asyncio
async def test_websocket_reconnect_replay(db: AsyncSession, live_session, test_user):
    """
    Test that events can be replayed for WebSocket reconnect.
    
    - Create multiple events
    - Get events since a specific ID
    - Verify correct events are returned
    """
    from backend.services.live_courtroom_service import get_events_since
    
    # Create multiple events
    event_ids = []
    for i in range(5):
        event = await append_live_event(
            live_session_id=live_session.id,
            event_type=LiveEventType.TURN_STARTED,
            event_payload={"sequence": i},
            db=db
        )
        event_ids.append(event.id)
    
    # Get events since the 2nd event
    since_id = event_ids[1]
    replay_events = await get_events_since(live_session.id, since_id, db)
    
    # Should return events 3, 4, 5 (ids after since_id)
    assert len(replay_events) == 3
    
    replay_ids = [e.id for e in replay_events]
    assert event_ids[2] in replay_ids
    assert event_ids[3] in replay_ids
    assert event_ids[4] in replay_ids
    assert event_ids[0] not in replay_ids
    assert event_ids[1] not in replay_ids


# =============================================================================
# Test 8: Multi-Institution Isolation
# =============================================================================

@pytest.mark.asyncio
async def test_multi_institution_isolation(db: AsyncSession, test_institution, second_institution, test_user):
    """
    Test that institutions can only access their own live sessions.
    
    - Create session for institution A
    - User from institution B cannot access
    """
    # Create session for first institution
    session1 = await start_live_session(
        session_id=None,
        tournament_match_id=None,
        institution_id=test_institution.id,
        created_by=test_user.id,
        db=db,
        visibility_mode=VisibilityMode.PRIVATE
    )
    
    # Create user from different institution
    other_user = User(
        email="other@institution.com",
        hashed_password="hashed",
        full_name="Other User",
        role=UserRole.student,
        institution_id=second_institution.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(other_user)
    await db.flush()
    
    # Verify institution_id is set correctly
    assert session1.institution_id == test_institution.id
    
    # Create session for second institution
    session2 = await start_live_session(
        session_id=None,
        tournament_match_id=None,
        institution_id=second_institution.id,
        created_by=other_user.id,
        db=db,
        visibility_mode=VisibilityMode.PRIVATE
    )
    
    # Verify isolation
    assert session1.institution_id != session2.institution_id
    
    # Query sessions by institution
    result = await db.execute(
        select(LiveCourtSession).where(
            LiveCourtSession.institution_id == test_institution.id
        )
    )
    inst1_sessions = list(result.scalars().all())
    assert len(inst1_sessions) == 1
    assert inst1_sessions[0].id == session1.id


# =============================================================================
# Test 9: No Float Usage Test
# =============================================================================

@pytest.mark.asyncio
async def test_no_float_usage(db: AsyncSession, live_session, test_participant, judge_user):
    """
    Test that all numeric values use Decimal (never float).
    
    - Submit scores as Decimal
    - Verify they remain Decimal in database
    - Verify no float conversion occurs
    """
    # Submit score with precise Decimal
    precise_score = Decimal("87.65")
    
    score = await submit_live_score(
        live_session_id=live_session.id,
        judge_id=judge_user.id,
        participant_id=test_participant.id,
        score_type=LiveScoreType.ARGUMENT,
        provisional_score=precise_score,
        db=db,
        comment="Test score"
    )
    
    # Verify score is Decimal
    assert isinstance(score.provisional_score, Decimal)
    assert score.provisional_score == precise_score
    
    # Reload from database
    result = await db.execute(
        select(LiveJudgeScore).where(LiveJudgeScore.id == score.id)
    )
    reloaded = result.scalar_one()
    
    # Verify still Decimal
    assert isinstance(reloaded.provisional_score, Decimal)
    assert reloaded.provisional_score == precise_score
    
    # Verify string representation has expected precision
    score_str = str(reloaded.provisional_score)
    assert "." in score_str
    assert len(score_str.split(".")[1]) == 2  # 2 decimal places


# =============================================================================
# Test 10: Full Lifecycle Integration Test
# =============================================================================

@pytest.mark.asyncio
async def test_full_lifecycle_integration(db: AsyncSession, test_institution, test_user, test_participant, second_participant, judge_user):
    """
    Test complete live courtroom lifecycle.
    
    - Start session
    - Start turns
    - Raise and resolve objections
    - Submit scores
    - Complete session
    - Verify event log integrity
    """
    # 1. Start live session
    session = await start_live_session(
        session_id=None,
        tournament_match_id=None,
        institution_id=test_institution.id,
        created_by=test_user.id,
        db=db,
        visibility_mode=VisibilityMode.INSTITUTION
    )
    
    assert session.status == LiveSessionStatus.LIVE
    
    # 2. Start first turn
    turn1 = await start_turn(
        live_session_id=session.id,
        participant_id=test_participant.id,
        side="petitioner",
        turn_type=LiveTurnType.OPENING,
        allocated_seconds=60,
        db=db
    )
    
    # 3. Submit score during turn
    score1 = await submit_live_score(
        live_session_id=session.id,
        judge_id=judge_user.id,
        participant_id=test_participant.id,
        score_type=LiveScoreType.ARGUMENT,
        provisional_score=Decimal("85.50"),
        db=db
    )
    
    # 4. End first turn
    turn1.ended_at = datetime.utcnow()
    turn1.actual_seconds = 45
    await db.flush()
    
    # Append TURN_ENDED event
    await append_live_event(
        live_session_id=session.id,
        event_type=LiveEventType.TURN_ENDED,
        event_payload={"turn_id": turn1.id, "actual_seconds": 45},
        db=db
    )
    
    # 5. Start second turn with objection
    turn2 = await start_turn(
        live_session_id=session.id,
        participant_id=second_participant.id,
        side="respondent",
        turn_type=LiveTurnType.REBUTTAL,
        allocated_seconds=60,
        db=db
    )
    
    # 6. Raise objection
    objection = await raise_objection(
        live_turn_id=turn2.id,
        raised_by_participant_id=test_participant.id,
        objection_type=ObjectionType.MISREPRESENTATION,
        db=db
    )
    
    assert objection.status == ObjectionStatus.PENDING
    
    # 7. Resolve objection
    resolved = await resolve_objection(
        objection_id=objection.id,
        judge_id=judge_user.id,
        status=ObjectionStatus.OVERRULED,
        db=db
    )
    
    assert resolved.status == ObjectionStatus.OVERRULED
    
    # 8. Submit score for second participant
    score2 = await submit_live_score(
        live_session_id=session.id,
        judge_id=judge_user.id,
        participant_id=second_participant.id,
        score_type=LiveScoreType.REBUTTAL,
        provisional_score=Decimal("78.25"),
        db=db
    )
    
    # 9. End second turn
    turn2.ended_at = datetime.utcnow()
    turn2.actual_seconds = 50
    await db.flush()
    
    # 10. Complete session
    completed = await complete_live_session(
        live_session_id=session.id,
        completed_by=test_user.id,
        db=db
    )
    
    assert completed.status == LiveSessionStatus.COMPLETED
    assert completed.ended_at is not None
    
    # 11. Verify event log
    result = await db.execute(
        select(func.count(LiveSessionEvent.id))
        .where(LiveSessionEvent.live_session_id == session.id)
    )
    event_count = result.scalar()
    
    assert event_count >= 7  # session_started, turn_started, score_submitted, turn_ended, objection_raised, objection_resolved, score_submitted, session_completed
    
    # 12. Verify chain integrity
    verification = await verify_live_event_chain(session.id, db)
    assert verification["is_valid"] is True
    assert verification["total_events"] == event_count


# =============================================================================
# Test 11: Objection Rate Limiting
# =============================================================================

@pytest.mark.asyncio
async def test_objection_rate_limiting(db: AsyncSession, live_session, test_participant, second_participant):
    """
    Test that objections are rate-limited per turn.
    
    - Raise max objections (default 3)
    - 4th objection should fail
    """
    # Start turn
    turn = await start_turn(
        live_session_id=live_session.id,
        participant_id=test_participant.id,
        side="petitioner",
        turn_type=LiveTurnType.ARGUMENT,
        allocated_seconds=300,
        db=db
    )
    
    # Create additional participants for objections
    participants = [second_participant]
    
    # Resolve any pending objections first
    result = await db.execute(
        select(LiveObjection).where(LiveObjection.live_turn_id == turn.id)
    )
    existing = list(result.scalars().all())
    for obj in existing:
        obj.status = ObjectionStatus.OVERRULED
    await db.flush()
    
    # Raise 3 objections (should succeed)
    for i in range(3):
        try:
            await resolve_objection(
                objection_id=obj.id,
                judge_id=1,
                status=ObjectionStatus.OVERRULED,
                db=db
            )
        except:
            pass
        
        obj = await raise_objection(
            live_turn_id=turn.id,
            raised_by_participant_id=second_participant.id,
            objection_type=ObjectionType.PROCEDURAL,
            db=db,
            max_objections_per_turn=3
        )
        assert obj is not None
    
    # 4th objection should fail
    with pytest.raises(ObjectionError) as exc_info:
        await raise_objection(
            live_turn_id=turn.id,
            raised_by_participant_id=second_participant.id,
            objection_type=ObjectionType.PROCEDURAL,
            db=db,
            max_objections_per_turn=3
        )
    
    assert "maximum" in str(exc_info.value).lower()


# =============================================================================
# Test 12: Speaker Cannot Object To Own Turn
# =============================================================================

@pytest.mark.asyncio
async def test_speaker_cannot_object_to_own_turn(db: AsyncSession, live_session, test_participant):
    """
    Test that a speaker cannot raise objection to their own turn.
    """
    # Start turn
    turn = await start_turn(
        live_session_id=live_session.id,
        participant_id=test_participant.id,
        side="petitioner",
        turn_type=LiveTurnType.ARGUMENT,
        allocated_seconds=300,
        db=db
    )
    
    # Try to object to own turn
    with pytest.raises(ObjectionError) as exc_info:
        await raise_objection(
            live_turn_id=turn.id,
            raised_by_participant_id=test_participant.id,  # Same as speaker
            objection_type=ObjectionType.LEADING,
            db=db
        )
    
    assert "cannot object to their own" in str(exc_info.value).lower()


# =============================================================================
# Test 13: Score Update (Idempotent Scoring)
# =============================================================================

@pytest.mark.asyncio
async def test_score_update_idempotent(db: AsyncSession, live_session, test_participant, judge_user):
    """
    Test that submitting a score for same judge/participant/type updates existing score.
    """
    # Submit initial score
    score1 = await submit_live_score(
        live_session_id=live_session.id,
        judge_id=judge_user.id,
        participant_id=test_participant.id,
        score_type=LiveScoreType.ARGUMENT,
        provisional_score=Decimal("75.00"),
        db=db
    )
    
    first_id = score1.id
    
    # Submit score for same combination - should update
    score2 = await submit_live_score(
        live_session_id=live_session.id,
        judge_id=judge_user.id,
        participant_id=test_participant.id,
        score_type=LiveScoreType.ARGUMENT,
        provisional_score=Decimal("85.00"),
        db=db
    )
    
    # Should be same record, updated
    assert score2.id == first_id
    assert score2.provisional_score == Decimal("85.00")


# =============================================================================
# Test 14: Pending Objections Block Session Completion
# =============================================================================

@pytest.mark.asyncio
async def test_pending_objections_block_completion(db: AsyncSession, live_session, test_participant, second_participant, judge_user):
    """
    Test that pending objections prevent session completion.
    """
    # Start turn
    turn = await start_turn(
        live_session_id=live_session.id,
        participant_id=test_participant.id,
        side="petitioner",
        turn_type=LiveTurnType.ARGUMENT,
        allocated_seconds=300,
        db=db
    )
    
    # Raise objection (don't resolve)
    objection = await raise_objection(
        live_turn_id=turn.id,
        raised_by_participant_id=second_participant.id,
        objection_type=ObjectionType.PROCEDURAL,
        db=db
    )
    
    # End turn
    turn.ended_at = datetime.utcnow()
    turn.actual_seconds = 30
    await db.flush()
    
    # Try to complete session - should fail
    with pytest.raises(SessionConflictError) as exc_info:
        await complete_live_session(
            live_session_id=live_session.id,
            completed_by=1,
            db=db
        )
    
    assert "pending objection" in str(exc_info.value).lower()
    
    # Resolve objection
    await resolve_objection(
        objection_id=objection.id,
        judge_id=judge_user.id,
        status=ObjectionStatus.OVERRULED,
        db=db
    )
    
    # Now completion should work
    completed = await complete_live_session(
        live_session_id=live_session.id,
        completed_by=1,
        db=db
    )
    
    assert completed.status == LiveSessionStatus.COMPLETED
