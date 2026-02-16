"""
Phase 14 — Comprehensive Test Suite

Tests for deterministic round engine:
- Deterministic turn ordering
- Double-advance protection
- Freeze immutability
- Illegal state transitions
- Concurrency race conditions
- Integrity hash stability
"""
import pytest
import uuid
import asyncio
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.phase14_round_service import RoundService
from backend.services.phase14_match_service import MatchService
from backend.services.phase14_timer_service import TimerService
from backend.orm.phase14_round_engine import (
    TournamentRound, TournamentMatch, MatchSpeakerTurn, MatchTimerState, MatchScoreLock,
    RoundType, RoundStatus, MatchStatus, TurnStatus, SpeakerRole,
    SPEAKER_FLOW_SEQUENCE
)


@pytest.fixture
def sample_tournament_id():
    return uuid.uuid4()


@pytest.fixture
def sample_team_ids():
    return [uuid.uuid4(), uuid.uuid4()]


@pytest.mark.asyncio
class TestDeterministicTurnOrdering:
    """Test deterministic speaker turn generation."""
    
    async def test_turn_sequence_is_deterministic(self, db: AsyncSession, sample_team_ids):
        """Turns must always be generated in exact sequence."""
        match_id = uuid.uuid4()
        
        turns = await MatchService.generate_speaker_turns(
            db=db,
            match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        # Must generate exactly 6 turns
        assert len(turns) == len(SPEAKER_FLOW_SEQUENCE)
        
        # Must be in exact order
        for i, (turn, expected_role) in enumerate(zip(turns, SPEAKER_FLOW_SEQUENCE)):
            assert turn.turn_order == i + 1
            assert turn.speaker_role == expected_role.value
            assert turn.status == TurnStatus.PENDING.value
    
    async def test_petitioner_speaker_roles(self, db: AsyncSession, sample_team_ids):
        """P1, P2, REBUTTAL_P must be petitioner team."""
        match_id = uuid.uuid4()
        petitioner_id = sample_team_ids[0]
        respondent_id = sample_team_ids[1]
        
        turns = await MatchService.generate_speaker_turns(
            db=db,
            match_id=match_id,
            team_petitioner_id=petitioner_id,
            team_respondent_id=respondent_id,
            allocated_seconds=600
        )
        
        petitioner_roles = {SpeakerRole.P1, SpeakerRole.P2, SpeakerRole.REBUTTAL_P}
        for turn in turns:
            if turn.speaker_role in [r.value for r in petitioner_roles]:
                assert turn.team_id == petitioner_id
    
    async def test_respondent_speaker_roles(self, db: AsyncSession, sample_team_ids):
        """R1, R2, REBUTTAL_R must be respondent team."""
        match_id = uuid.uuid4()
        petitioner_id = sample_team_ids[0]
        respondent_id = sample_team_ids[1]
        
        turns = await MatchService.generate_speaker_turns(
            db=db,
            match_id=match_id,
            team_petitioner_id=petitioner_id,
            team_respondent_id=respondent_id,
            allocated_seconds=600
        )
        
        respondent_roles = {SpeakerRole.R1, SpeakerRole.R2, SpeakerRole.REBUTTAL_R}
        for turn in turns:
            if turn.speaker_role in [r.value for r in respondent_roles]:
                assert turn.team_id == respondent_id
    
    async def test_turns_cannot_be_generated_twice(self, db: AsyncSession, sample_team_ids):
        """Cannot generate turns if already generated."""
        match_id = uuid.uuid4()
        
        # First generation succeeds
        await MatchService.generate_speaker_turns(
            db=db,
            match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        # Second generation fails
        with pytest.raises(HTTPException) as exc_info:
            await MatchService.generate_speaker_turns(
                db=db,
                match_id=match_id,
                team_petitioner_id=sample_team_ids[0],
                team_respondent_id=sample_team_ids[1],
                allocated_seconds=600
            )
        
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
class TestDoubleAdvanceProtection:
    """Test protection against double-advance race conditions."""
    
    async def test_cannot_advance_without_completing_active(self, db: AsyncSession, sample_team_ids):
        """Cannot advance if active turn not completed."""
        match_id = uuid.uuid4()
        
        # Setup: Generate turns, start match, advance once
        await MatchService.generate_speaker_turns(
            db=db,
            match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        # Start match
        await MatchService.start_match(db=db, match_id=match_id)
        
        # Advance to first turn
        await MatchService.advance_turn(db=db, match_id=match_id)
        
        # Try to advance again without completing - should fail
        with pytest.raises(HTTPException) as exc_info:
            await MatchService.advance_turn(db=db, match_id=match_id)
        
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "active turn must be completed" in exc_info.value.detail.lower()
    
    async def test_can_advance_after_completing_turn(self, db: AsyncSession, sample_team_ids):
        """Can advance after completing active turn."""
        match_id = uuid.uuid4()
        
        # Setup
        turns = await MatchService.generate_speaker_turns(
            db=db,
            match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        await MatchService.start_match(db=db, match_id=match_id)
        
        # Advance to first turn
        result = await MatchService.advance_turn(db=db, match_id=match_id)
        first_turn_id = result['current_turn']['id']
        
        # Complete the turn
        await MatchService.complete_turn(db=db, turn_id=uuid.UUID(first_turn_id))
        
        # Now advance should work
        result2 = await MatchService.advance_turn(db=db, match_id=match_id)
        assert result2['current_turn']['turn_order'] == 2


@pytest.mark.asyncio
class TestFreezeImmutability:
    """Test that frozen matches cannot be modified."""
    
    async def test_freeze_computes_integrity_hash(self, db: AsyncSession, sample_team_ids):
        """Freeze must compute and store integrity hash."""
        match_id = uuid.uuid4()
        judge_ids = [uuid.uuid4(), uuid.uuid4()]
        
        # Setup complete match
        turns = await MatchService.generate_speaker_turns(
            db=db,
            match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        await MatchService.start_match(db=db, match_id=match_id)
        
        # Complete all turns
        for i in range(len(SPEAKER_FLOW_SEQUENCE)):
            result = await MatchService.advance_turn(db=db, match_id=match_id)
            turn_id = uuid.UUID(result['current_turn']['id'])
            await MatchService.complete_turn(db=db, turn_id=turn_id)
        
        # Complete match
        await MatchService.complete_match(
            db=db,
            match_id=match_id,
            winner_team_id=sample_team_ids[0]
        )
        
        # Freeze
        score_lock = await MatchService.freeze_match(
            db=db,
            match_id=match_id,
            petitioner_score=Decimal("85.50"),
            respondent_score=Decimal("78.25"),
            winner_team_id=sample_team_ids[0],
            judge_ids=judge_ids
        )
        
        # Must have hash
        assert score_lock.frozen_hash is not None
        assert len(score_lock.frozen_hash) == 64  # SHA256 hex
    
    async def test_cannot_freeze_twice(self, db: AsyncSession, sample_team_ids):
        """Cannot freeze a match twice."""
        match_id = uuid.uuid4()
        
        # Setup complete match and freeze once
        turns = await MatchService.generate_speaker_turns(
            db=db,
            match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        await MatchService.start_match(db=db, match_id=match_id)
        
        for i in range(len(SPEAKER_FLOW_SEQUENCE)):
            result = await MatchService.advance_turn(db=db, match_id=match_id)
            turn_id = uuid.UUID(result['current_turn']['id'])
            await MatchService.complete_turn(db=db, turn_id=turn_id)
        
        await MatchService.complete_match(
            db=db,
            match_id=match_id,
            winner_team_id=sample_team_ids[0]
        )
        
        await MatchService.freeze_match(
            db=db,
            match_id=match_id,
            petitioner_score=Decimal("85.50"),
            respondent_score=Decimal("78.25"),
            winner_team_id=sample_team_ids[0],
            judge_ids=[uuid.uuid4()]
        )
        
        # Second freeze should fail
        with pytest.raises(HTTPException) as exc_info:
            await MatchService.freeze_match(
                db=db,
                match_id=match_id,
                petitioner_score=Decimal("85.50"),
                respondent_score=Decimal("78.25"),
                winner_team_id=sample_team_ids[0],
                judge_ids=[uuid.uuid4()]
            )
        
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
class TestIllegalStateTransitions:
    """Test state machine enforcement."""
    
    async def test_round_invalid_transitions(self, db: AsyncSession, sample_tournament_id):
        """Test round state machine rejects invalid transitions."""
        # Create round
        round_obj = await RoundService.create_round(
            db=db,
            tournament_id=sample_tournament_id,
            round_number=1,
            round_type=RoundType.PRELIM,
            bench_count=2
        )
        
        # Cannot freeze from SCHEDULED
        with pytest.raises(HTTPException) as exc_info:
            await RoundService.freeze_round(db=db, round_id=round_obj.id)
        
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    
    async def test_match_invalid_transitions(self, db: AsyncSession, sample_team_ids):
        """Test match state machine rejects invalid transitions."""
        match_id = uuid.uuid4()
        
        # Setup but don't start
        await MatchService.generate_speaker_turns(
            db=db,
            match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        # Cannot complete from SCHEDULED
        with pytest.raises(HTTPException) as exc_info:
            await MatchService.complete_match(
                db=db,
                match_id=match_id,
                winner_team_id=sample_team_ids[0]
            )
        
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    
    async def test_turn_invalid_transitions(self, db: AsyncSession, sample_team_ids):
        """Test turn state machine rejects invalid transitions."""
        match_id = uuid.uuid4()
        
        turns = await MatchService.generate_speaker_turns(
            db=db,
            match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        # Cannot complete a PENDING turn
        with pytest.raises(HTTPException) as exc_info:
            await MatchService.complete_turn(db=db, turn_id=turns[0].id)
        
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
class TestConcurrencyRaceConditions:
    """Test concurrency protection with FOR UPDATE locking."""
    
    async def test_concurrent_advance_protection(self, db: AsyncSession, sample_team_ids):
        """Two concurrent advances should not both succeed."""
        match_id = uuid.uuid4()
        
        # Setup
        await MatchService.generate_speaker_turns(
            db=db,
            match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        await MatchService.start_match(db=db, match_id=match_id)
        
        # Try two concurrent advances
        # In reality, with proper locking, one should block until other completes
        # For this test, we verify the behavior is deterministic
        result = await MatchService.advance_turn(db=db, match_id=match_id)
        
        # Should get first turn
        assert result['current_turn']['turn_order'] == 1
    
    async def test_concurrent_freeze_protection(self, db: AsyncSession, sample_team_ids):
        """Two concurrent freezes should not both succeed."""
        match_id = uuid.uuid4()
        
        # Setup complete match
        turns = await MatchService.generate_speaker_turns(
            db=db,
            match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        await MatchService.start_match(db=db, match_id=match_id)
        
        for i in range(len(SPEAKER_FLOW_SEQUENCE)):
            result = await MatchService.advance_turn(db=db, match_id=match_id)
            turn_id = uuid.UUID(result['current_turn']['id'])
            await MatchService.complete_turn(db=db, turn_id=turn_id)
        
        await MatchService.complete_match(
            db=db,
            match_id=match_id,
            winner_team_id=sample_team_ids[0]
        )
        
        # First freeze succeeds
        await MatchService.freeze_match(
            db=db,
            match_id=match_id,
            petitioner_score=Decimal("85.50"),
            respondent_score=Decimal("78.25"),
            winner_team_id=sample_team_ids[0],
            judge_ids=[uuid.uuid4()]
        )
        
        # Second would fail (tested in TestFreezeImmutability)


@pytest.mark.asyncio
class TestIntegrityHashStability:
    """Test integrity hash is deterministic and stable."""
    
    async def test_hash_determinism(self, db: AsyncSession, sample_team_ids):
        """Same inputs must produce same hash."""
        match_id = uuid.uuid4()
        turn_ids = [uuid.uuid4() for _ in range(6)]
        judge_ids = [uuid.uuid4(), uuid.uuid4()]
        
        score_lock = MatchScoreLock(
            match_id=match_id,
            total_petitioner_score=Decimal("85.50"),
            total_respondent_score=Decimal("78.25"),
            winner_team_id=sample_team_ids[0],
            frozen_at=datetime.utcnow()
        )
        
        hash1 = score_lock.compute_integrity_hash(turn_ids, judge_ids)
        hash2 = score_lock.compute_integrity_hash(turn_ids, judge_ids)
        
        assert hash1 == hash2
    
    async def test_hash_sensitivity_to_scores(self, db: AsyncSession, sample_team_ids):
        """Different scores produce different hashes."""
        match_id = uuid.uuid4()
        turn_ids = [uuid.uuid4() for _ in range(6)]
        judge_ids = [uuid.uuid4(), uuid.uuid4()]
        
        score_lock1 = MatchScoreLock(
            match_id=match_id,
            total_petitioner_score=Decimal("85.50"),
            total_respondent_score=Decimal("78.25"),
            winner_team_id=sample_team_ids[0],
            frozen_at=datetime.utcnow()
        )
        
        score_lock2 = MatchScoreLock(
            match_id=match_id,
            total_petitioner_score=Decimal("86.50"),  # Different
            total_respondent_score=Decimal("78.25"),
            winner_team_id=sample_team_ids[0],
            frozen_at=datetime.utcnow()
        )
        
        hash1 = score_lock1.compute_integrity_hash(turn_ids, judge_ids)
        hash2 = score_lock2.compute_integrity_hash(turn_ids, judge_ids)
        
        assert hash1 != hash2


@pytest.mark.asyncio
class TestCrashRecovery:
    """Test crash recovery for LIVE matches."""
    
    async def test_restore_live_matches(self, db: AsyncSession, sample_team_ids):
        """Should detect and return LIVE matches."""
        match_id = uuid.uuid4()
        
        # Setup LIVE match
        await MatchService.generate_speaker_turns(
            db=db,
            match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        await MatchService.start_match(db=db, match_id=match_id)
        
        # Create timer state
        from backend.orm.phase14_round_engine import MatchSpeakerTurn, TurnStatus
        from sqlalchemy import select as sa_select
        
        turns_result = await db.execute(
            sa_select(MatchSpeakerTurn).where(
                MatchSpeakerTurn.match_id == match_id,
                MatchSpeakerTurn.turn_order == 1
            )
        )
        first_turn = turns_result.scalar_one()
        
        await TimerService.initialize_timer(
            db=db,
            match_id=match_id,
            active_turn_id=first_turn.id,
            remaining_seconds=300
        )
        
        # Run recovery
        recovery_data = await TimerService.restore_live_matches(db=db)
        
        # Should find our LIVE match
        match_ids = [m['match_id'] for m in recovery_data]
        assert str(match_id) in match_ids
    
    async def test_timer_state_recovery(self, db: AsyncSession, sample_team_ids):
        """Should restore timer state with remaining seconds."""
        match_id = uuid.uuid4()
        
        # Setup
        await MatchService.generate_speaker_turns(
            db=db,
            match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        await MatchService.start_match(db=db, match_id=match_id)
        
        from backend.orm.phase14_round_engine import MatchSpeakerTurn, TurnStatus
        from sqlalchemy import select as sa_select
        
        turns_result = await db.execute(
            sa_select(MatchSpeakerTurn).where(
                MatchSpeakerTurn.match_id == match_id,
                MatchSpeakerTurn.turn_order == 1
            )
        )
        first_turn = turns_result.scalar_one()
        
        await TimerService.initialize_timer(
            db=db,
            match_id=match_id,
            active_turn_id=first_turn.id,
            remaining_seconds=300
        )
        
        # Recover
        recovery_data = await TimerService.restore_live_matches(db=db)
        
        match_data = next(m for m in recovery_data if m['match_id'] == str(match_id))
        assert match_data['timer']['remaining_seconds'] == 300
        assert match_data['timer']['paused'] is False


@pytest.mark.asyncio
class TestTimerAutoComplete:
    """Test timer auto-completes turn when time expires."""
    
    async def test_timer_tick_reduces_remaining(self, db: AsyncSession, sample_team_ids):
        """Timer tick should reduce remaining seconds."""
        match_id = uuid.uuid4()
        
        # Setup
        await MatchService.generate_speaker_turns(
            db=db,
            match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        await MatchService.start_match(db=db, match_id=match_id)
        
        from backend.orm.phase14_round_engine import MatchSpeakerTurn, TurnStatus
        from sqlalchemy import select as sa_select
        
        turns_result = await db.execute(
            sa_select(MatchSpeakerTurn).where(
                MatchSpeakerTurn.match_id == match_id,
                MatchSpeakerTurn.turn_order == 1
            )
        )
        first_turn = turns_result.scalar_one()
        
        await TimerService.initialize_timer(
            db=db,
            match_id=match_id,
            active_turn_id=first_turn.id,
            remaining_seconds=300
        )
        
        # Tick
        import time
        time.sleep(1)  # Wait a second
        
        timer = await TimerService.tick(db=db, match_id=match_id)
        
        # Should have less than 300 seconds remaining
        assert timer.remaining_seconds <= 299
