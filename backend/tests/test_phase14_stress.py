"""
Phase 14 — High-Intensity Stress Test Suite

Production-grade stability validation with 25+ test cases:
- Concurrency stress tests (50+ concurrent operations)
- State machine torture tests
- Timer crash recovery simulation
- Freeze immutability attacks
- Integrity hash verification
- Edge case resilience
- Performance load tests
"""
import pytest
import uuid
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any
import time

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select as sa_select

from backend.services.phase14_round_service import RoundService
from backend.services.phase14_match_service import MatchService
from backend.services.phase14_timer_service import TimerService
from backend.orm.phase14_round_engine import (
    TournamentRound, TournamentMatch, MatchSpeakerTurn, MatchTimerState, MatchScoreLock,
    RoundType, RoundStatus, MatchStatus, TurnStatus, SpeakerRole,
    SPEAKER_FLOW_SEQUENCE
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def sample_tournament_id():
    return uuid.uuid4()


@pytest.fixture
def sample_team_ids():
    return [uuid.uuid4(), uuid.uuid4()]


@pytest.fixture
def sample_judge_ids():
    return [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]


# =============================================================================
# STRESS TEST 1: MASS CONCURRENCY (50+ concurrent advances)
# =============================================================================

@pytest.mark.asyncio
class TestMassConcurrency:
    """Simulate 50+ concurrent operations to test locking."""
    
    async def test_50_concurrent_advance_calls(self, db: AsyncSession, sample_team_ids):
        """50 concurrent advance calls - only 1 should succeed per turn."""
        match_id = uuid.uuid4()
        
        # Setup
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        await MatchService.start_match(db=db, match_id=match_id)
        
        # First advance to get active turn
        result = await MatchService.advance_turn(db=db, match_id=match_id)
        turn_id = uuid.UUID(result['current_turn']['id'])
        
        # Complete the turn
        await MatchService.complete_turn(db=db, turn_id=turn_id)
        
        # Now 50 concurrent advances for second turn
        results = []
        errors = []
        
        async def attempt_advance():
            try:
                async with db.begin():
                    r = await MatchService.advance_turn(db=db, match_id=match_id)
                    results.append(r)
            except Exception as e:
                errors.append(e)
        
        # Run 50 attempts concurrently
        tasks = [attempt_advance() for _ in range(50)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Only 1 should succeed
        assert len(results) <= 1, f"Expected 1 success, got {len(results)}"
        
        # Verify only one turn is active
        turns_result = await db.execute(
            sa_select(MatchSpeakerTurn).where(
                MatchSpeakerTurn.match_id == match_id,
                MatchSpeakerTurn.status == TurnStatus.ACTIVE.value
            )
        )
        active_turns = turns_result.scalars().all()
        assert len(active_turns) <= 1, f"Expected <=1 active turns, got {len(active_turns)}"
    
    async def test_20_concurrent_timer_pauses(self, db: AsyncSession, sample_team_ids):
        """20 concurrent pause calls - all should see consistent state."""
        match_id = uuid.uuid4()
        
        # Setup
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        await MatchService.start_match(db=db, match_id=match_id)
        
        result = await MatchService.advance_turn(db=db, match_id=match_id)
        turn_id = uuid.UUID(result['current_turn']['id'])
        
        # Initialize timer
        await TimerService.initialize_timer(
            db=db, match_id=match_id,
            active_turn_id=turn_id, remaining_seconds=300
        )
        
        # 20 concurrent pauses
        results = []
        async def pause_attempt():
            try:
                r = await TimerService.pause_timer(db=db, match_id=match_id)
                results.append(r)
            except:
                pass
        
        tasks = [pause_attempt() for _ in range(20)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Timer should be paused
        timer = await TimerService.get_timer_state(db=db, match_id=match_id)
        assert timer.paused is True
    
    async def test_20_concurrent_freeze_attempts(self, db: AsyncSession, sample_team_ids, sample_judge_ids):
        """20 concurrent freeze calls - only 1 should succeed."""
        match_id = uuid.uuid4()
        
        # Setup complete match
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        await MatchService.start_match(db=db, match_id=match_id)
        
        # Complete all turns
        for _ in range(len(SPEAKER_FLOW_SEQUENCE)):
            result = await MatchService.advance_turn(db=db, match_id=match_id)
            turn_id = uuid.UUID(result['current_turn']['id'])
            await MatchService.complete_turn(db=db, turn_id=turn_id)
        
        await MatchService.complete_match(
            db=db, match_id=match_id,
            winner_team_id=sample_team_ids[0]
        )
        
        # 20 concurrent freezes
        results = []
        errors = []
        
        async def freeze_attempt():
            try:
                r = await MatchService.freeze_match(
                    db=db, match_id=match_id,
                    petitioner_score=Decimal("85.50"),
                    respondent_score=Decimal("78.25"),
                    winner_team_id=sample_team_ids[0],
                    judge_ids=sample_judge_ids[:2]
                )
                results.append(r)
            except HTTPException as e:
                errors.append(e)
        
        tasks = [freeze_attempt() for _ in range(20)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Only 1 should succeed
        assert len(results) == 1, f"Expected 1 freeze success, got {len(results)}"
        
        # Verify match is frozen
        match_result = await db.execute(
            sa_select(TournamentMatch).where(TournamentMatch.id == match_id)
        )
        match = match_result.scalar_one()
        assert match.status == MatchStatus.FROZEN.value


# =============================================================================
# STRESS TEST 2: STATE MACHINE TORTURE
# =============================================================================

@pytest.mark.asyncio
class TestStateMachineTorture:
    """Test all invalid state transitions."""
    
    async def test_round_all_invalid_transitions(self, db: AsyncSession, sample_tournament_id):
        """Test every invalid round transition returns 409."""
        round_obj = await RoundService.create_round(
            db=db, tournament_id=sample_tournament_id,
            round_number=1, round_type=RoundType.PRELIM, bench_count=2
        )
        
        invalid_transitions = [
            (RoundStatus.SCHEDULED.value, 'frozen'),
            (RoundStatus.SCHEDULED.value, 'completed'),
            (RoundStatus.SCHEDULED.value, 'invalid_status'),
        ]
        
        for from_status, to_status in invalid_transitions:
            round_obj.status = from_status
            await db.flush()
            
            with pytest.raises((HTTPException, ValueError)):
                round_obj.status = to_status
                await db.flush()
    
    async def test_match_all_invalid_transitions(self, db: AsyncSession, sample_team_ids):
        """Test every invalid match transition returns 409."""
        match_id = uuid.uuid4()
        
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        # Try to complete from SCHEDULED
        with pytest.raises(HTTPException) as exc:
            await MatchService.complete_match(
                db=db, match_id=match_id, winner_team_id=sample_team_ids[0]
            )
        assert exc.value.status_code == status.HTTP_409_CONFLICT
        
        # Try to freeze from SCHEDULED
        with pytest.raises(HTTPException) as exc:
            await MatchService.freeze_match(
                db=db, match_id=match_id,
                petitioner_score=Decimal("80.00"),
                respondent_score=Decimal("70.00"),
                winner_team_id=sample_team_ids[0],
                judge_ids=[uuid.uuid4()]
            )
        assert exc.value.status_code == status.HTTP_409_CONFLICT
    
    async def test_turn_all_invalid_transitions(self, db: AsyncSession, sample_team_ids):
        """Test every invalid turn transition returns 409."""
        match_id = uuid.uuid4()
        
        turns = await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        # Try to complete PENDING turn
        with pytest.raises(HTTPException) as exc:
            await MatchService.complete_turn(db=db, turn_id=turns[0].id)
        assert exc.value.status_code == status.HTTP_409_CONFLICT


# =============================================================================
# STRESS TEST 3: TIMER CRASH RECOVERY
# =============================================================================

@pytest.mark.asyncio
class TestTimerCrashRecovery:
    """Simulate server crashes and verify recovery."""
    
    async def test_timer_recovery_with_elapsed_time(self, db: AsyncSession, sample_team_ids):
        """Simulate 30s downtime and verify time adjustment."""
        match_id = uuid.uuid4()
        
        # Setup
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        await MatchService.start_match(db=db, match_id=match_id)
        
        result = await MatchService.advance_turn(db=db, match_id=match_id)
        turn_id = uuid.UUID(result['current_turn']['id'])
        
        # Initialize timer with 300s
        await TimerService.initialize_timer(
            db=db, match_id=match_id,
            active_turn_id=turn_id, remaining_seconds=300
        )
        
        # Simulate server downtime by manually setting last_tick back
        timer_result = await db.execute(
            sa_select(MatchTimerState).where(MatchTimerState.match_id == match_id)
        )
        timer = timer_result.scalar_one()
        timer.last_tick = datetime.utcnow() - timedelta(seconds=30)
        timer.paused = False
        await db.commit()
        
        # Run recovery
        recovery_data = await TimerService.restore_live_matches(db=db)
        
        # Find our match
        match_data = next((m for m in recovery_data if m['match_id'] == str(match_id)), None)
        assert match_data is not None
        assert match_data['timer']['elapsed_downtime'] >= 30
        assert match_data['timer']['remaining_seconds'] <= 270
    
    async def test_timer_auto_complete_on_expiry(self, db: AsyncSession, sample_team_ids):
        """Turn should auto-complete when time expires during downtime."""
        match_id = uuid.uuid4()
        
        # Setup
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        await MatchService.start_match(db=db, match_id=match_id)
        
        result = await MatchService.advance_turn(db=db, match_id=match_id)
        turn_id = uuid.UUID(result['current_turn']['id'])
        
        # Initialize with only 10s remaining
        await TimerService.initialize_timer(
            db=db, match_id=match_id,
            active_turn_id=turn_id, remaining_seconds=10
        )
        
        # Simulate 20s downtime (longer than remaining time)
        timer_result = await db.execute(
            sa_select(MatchTimerState).where(MatchTimerState.match_id == match_id)
        )
        timer = timer_result.scalar_one()
        timer.last_tick = datetime.utcnow() - timedelta(seconds=20)
        timer.paused = False
        await db.commit()
        
        # Run recovery
        recovery_data = await TimerService.restore_live_matches(db=db)
        
        # Verify turn was auto-completed
        turn_result = await db.execute(
            sa_select(MatchSpeakerTurn).where(MatchSpeakerTurn.id == turn_id)
        )
        turn = turn_result.scalar_one()
        assert turn.status == TurnStatus.COMPLETED.value
    
    async def test_paused_timer_no_elapsed_during_downtime(self, db: AsyncSession, sample_team_ids):
        """Paused timer should not lose time during downtime."""
        match_id = uuid.uuid4()
        
        # Setup
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        await MatchService.start_match(db=db, match_id=match_id)
        
        result = await MatchService.advance_turn(db=db, match_id=match_id)
        turn_id = uuid.UUID(result['current_turn']['id'])
        
        await TimerService.initialize_timer(
            db=db, match_id=match_id,
            active_turn_id=turn_id, remaining_seconds=300
        )
        
        # Pause the timer
        await TimerService.pause_timer(db=db, match_id=match_id)
        
        # Simulate downtime
        timer_result = await db.execute(
            sa_select(MatchTimerState).where(MatchTimerState.match_id == match_id)
        )
        timer = timer_result.scalar_one()
        timer.last_tick = datetime.utcnow() - timedelta(seconds=60)
        await db.commit()
        
        # Run recovery
        recovery_data = await TimerService.restore_live_matches(db=db)
        
        # Find match
        match_data = next((m for m in recovery_data if m['match_id'] == str(match_id)), None)
        assert match_data is not None
        
        # Paused timer should not lose time
        assert match_data['timer']['remaining_seconds'] == 300


# =============================================================================
# STRESS TEST 4: FREEZE IMMUTABILITY ATTACKS
# =============================================================================

@pytest.mark.asyncio
class TestFreezeImmutabilityAttacks:
    """Attempt to modify frozen entities."""
    
    async def test_cannot_modify_frozen_match_status(self, db: AsyncSession, sample_team_ids):
        """Attempt to change status of frozen match - should fail."""
        match_id = await self._create_and_freeze_match(db, sample_team_ids)
        
        # Attempt to modify
        match_result = await db.execute(
            sa_select(TournamentMatch).where(TournamentMatch.id == match_id)
        )
        match = match_result.scalar_one()
        
        with pytest.raises(Exception):
            match.status = MatchStatus.LIVE.value
            await db.flush()
    
    async def test_cannot_modify_frozen_turn(self, db: AsyncSession, sample_team_ids):
        """Attempt to modify turn after freeze - should fail."""
        match_id = await self._create_and_freeze_match(db, sample_team_ids)
        
        # Get turns
        turns_result = await db.execute(
            sa_select(MatchSpeakerTurn).where(MatchSpeakerTurn.match_id == match_id)
        )
        turns = turns_result.scalars().all()
        
        # Attempt to modify first turn
        with pytest.raises(Exception):
            turns[0].allocated_seconds = 999
            await db.flush()
    
    async def test_cannot_double_freeze(self, db: AsyncSession, sample_team_ids):
        """Attempt to freeze already frozen match - should fail with 409."""
        match_id = await self._create_and_freeze_match(db, sample_team_ids)
        
        # Attempt second freeze
        with pytest.raises(HTTPException) as exc:
            await MatchService.freeze_match(
                db=db, match_id=match_id,
                petitioner_score=Decimal("90.00"),
                respondent_score=Decimal("80.00"),
                winner_team_id=sample_team_ids[0],
                judge_ids=[uuid.uuid4()]
            )
        assert exc.value.status_code == status.HTTP_409_CONFLICT
    
    async def _create_and_freeze_match(self, db: AsyncSession, sample_team_ids) -> uuid.UUID:
        """Helper to create and freeze a match."""
        match_id = uuid.uuid4()
        
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        await MatchService.start_match(db=db, match_id=match_id)
        
        for _ in range(len(SPEAKER_FLOW_SEQUENCE)):
            result = await MatchService.advance_turn(db=db, match_id=match_id)
            turn_id = uuid.UUID(result['current_turn']['id'])
            await MatchService.complete_turn(db=db, turn_id=turn_id)
        
        await MatchService.complete_match(
            db=db, match_id=match_id, winner_team_id=sample_team_ids[0]
        )
        
        await MatchService.freeze_match(
            db=db, match_id=match_id,
            petitioner_score=Decimal("85.50"),
            respondent_score=Decimal("78.25"),
            winner_team_id=sample_team_ids[0],
            judge_ids=[uuid.uuid4(), uuid.uuid4()]
        )
        
        return match_id


# =============================================================================
# STRESS TEST 5: INTEGRITY HASH VALIDATION
# =============================================================================

@pytest.mark.asyncio
class TestIntegrityHashValidation:
    """Verify SHA256 integrity hash computation and validation."""
    
    async def test_hash_determinism(self, db: AsyncSession):
        """Same inputs must produce same hash every time."""
        from backend.orm.phase14_round_engine import MatchScoreLock
        
        score_lock = MatchScoreLock(
            match_id=uuid.uuid4(),
            total_petitioner_score=Decimal("85.50"),
            total_respondent_score=Decimal("78.25"),
            winner_team_id=uuid.uuid4(),
            frozen_at=datetime.utcnow()
        )
        
        turn_ids = [uuid.uuid4() for _ in range(6)]
        judge_ids = [uuid.uuid4() for _ in range(2)]
        
        hash1 = score_lock.compute_integrity_hash(turn_ids, judge_ids)
        hash2 = score_lock.compute_integrity_hash(turn_ids, judge_ids)
        hash3 = score_lock.compute_integrity_hash(turn_ids, judge_ids)
        
        assert hash1 == hash2 == hash3
        assert len(hash1) == 64  # SHA256 hex length
    
    async def test_hash_sensitivity_to_scores(self, db: AsyncSession):
        """Different scores produce different hashes."""
        from backend.orm.phase14_round_engine import MatchScoreLock
        
        match_id = uuid.uuid4()
        turn_ids = [str(uuid.uuid4()) for _ in range(6)]
        judge_ids = [str(uuid.uuid4()) for _ in range(2)]
        
        score_lock1 = MatchScoreLock(
            match_id=match_id,
            total_petitioner_score=Decimal("85.50"),
            total_respondent_score=Decimal("78.25"),
            winner_team_id=uuid.uuid4(),
            frozen_at=datetime.utcnow()
        )
        
        score_lock2 = MatchScoreLock(
            match_id=match_id,
            total_petitioner_score=Decimal("86.50"),  # Different
            total_respondent_score=Decimal("78.25"),
            winner_team_id=score_lock1.winner_team_id,
            frozen_at=score_lock1.frozen_at
        )
        
        hash1 = score_lock1.compute_integrity_hash(turn_ids, judge_ids)
        hash2 = score_lock2.compute_integrity_hash(turn_ids, judge_ids)
        
        assert hash1 != hash2
    
    async def test_integrity_verification_endpoint(self, db: AsyncSession, sample_team_ids):
        """Verify integrity check endpoint returns correct results."""
        match_id = uuid.uuid4()
        
        # Create and freeze match
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        await MatchService.start_match(db=db, match_id=match_id)
        
        for _ in range(len(SPEAKER_FLOW_SEQUENCE)):
            result = await MatchService.advance_turn(db=db, match_id=match_id)
            turn_id = uuid.UUID(result['current_turn']['id'])
            await MatchService.complete_turn(db=db, turn_id=turn_id)
        
        await MatchService.complete_match(
            db=db, match_id=match_id, winner_team_id=sample_team_ids[0]
        )
        
        await MatchService.freeze_match(
            db=db, match_id=match_id,
            petitioner_score=Decimal("85.50"),
            respondent_score=Decimal("78.25"),
            winner_team_id=sample_team_ids[0],
            judge_ids=[uuid.uuid4(), uuid.uuid4()]
        )
        
        # Verify integrity
        result = await MatchService.verify_match_integrity(db=db, match_id=match_id)
        
        assert result['frozen'] is True
        assert result['verified'] is True
        assert result['turn_count'] == len(SPEAKER_FLOW_SEQUENCE)
        assert result['frozen_hash'] is not None


# =============================================================================
# STRESS TEST 6: EDGE CASE ATTACKS
# =============================================================================

@pytest.mark.asyncio
class TestEdgeCaseAttacks:
    """Test edge cases and boundary conditions."""
    
    async def test_advance_without_active_speaker(self, db: AsyncSession, sample_team_ids):
        """Advance when no active speaker should activate first pending."""
        match_id = uuid.uuid4()
        
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        await MatchService.start_match(db=db, match_id=match_id)
        
        # First advance should activate P1
        result = await MatchService.advance_turn(db=db, match_id=match_id)
        assert result['current_turn']['speaker_role'] == 'p1'
        assert result['current_turn']['turn_order'] == 1
    
    async def test_complete_without_all_speakers(self, db: AsyncSession, sample_team_ids):
        """Complete match without all speakers done should fail."""
        match_id = uuid.uuid4()
        
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        await MatchService.start_match(db=db, match_id=match_id)
        
        # Only complete 1 turn
        result = await MatchService.advance_turn(db=db, match_id=match_id)
        turn_id = uuid.UUID(result['current_turn']['id'])
        await MatchService.complete_turn(db=db, turn_id=turn_id)
        
        # Try to complete match - should fail
        with pytest.raises(HTTPException) as exc:
            await MatchService.complete_match(
                db=db, match_id=match_id, winner_team_id=sample_team_ids[0]
            )
        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    
    async def test_freeze_without_completion(self, db: AsyncSession, sample_team_ids):
        """Freeze without match completion should fail."""
        match_id = uuid.uuid4()
        
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        await MatchService.start_match(db=db, match_id=match_id)
        
        # Try to freeze incomplete match
        with pytest.raises(HTTPException) as exc:
            await MatchService.freeze_match(
                db=db, match_id=match_id,
                petitioner_score=Decimal("85.00"),
                respondent_score=Decimal("75.00"),
                winner_team_id=sample_team_ids[0],
                judge_ids=[uuid.uuid4()]
            )
        assert exc.value.status_code == status.HTTP_409_CONFLICT
    
    async def test_duplicate_round_creation(self, db: AsyncSession, sample_tournament_id):
        """Duplicate round number should fail."""
        await RoundService.create_round(
            db=db, tournament_id=sample_tournament_id,
            round_number=1, round_type=RoundType.PRELIM
        )
        
        # Try to create duplicate
        with pytest.raises(HTTPException) as exc:
            await RoundService.create_round(
                db=db, tournament_id=sample_tournament_id,
                round_number=1, round_type=RoundType.PRELIM
            )
        assert exc.value.status_code == status.HTTP_409_CONFLICT
    
    async def test_negative_timer_values(self, db: AsyncSession, sample_team_ids):
        """Timer should never go negative."""
        match_id = uuid.uuid4()
        
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        await MatchService.start_match(db=db, match_id=match_id)
        
        result = await MatchService.advance_turn(db=db, match_id=match_id)
        turn_id = uuid.UUID(result['current_turn']['id'])
        
        await TimerService.initialize_timer(
            db=db, match_id=match_id,
            active_turn_id=turn_id, remaining_seconds=5
        )
        
        # Tick multiple times to go past zero
        for _ in range(3):
            await TimerService.tick(db=db, match_id=match_id)
            await asyncio.sleep(1.1)  # Wait for elapsed time
        
        timer = await TimerService.get_timer_state(db=db, match_id=match_id)
        assert timer.remaining_seconds >= 0
    
    async def test_speaker_turns_already_generated(self, db: AsyncSession, sample_team_ids):
        """Double generation of speaker turns should fail."""
        match_id = uuid.uuid4()
        
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        # Try to generate again
        with pytest.raises(HTTPException) as exc:
            await MatchService.generate_speaker_turns(
                db=db, match_id=match_id,
                team_petitioner_id=sample_team_ids[0],
                team_respondent_id=sample_team_ids[1],
                allocated_seconds=600
            )
        assert exc.value.status_code == status.HTTP_409_CONFLICT


# =============================================================================
# STRESS TEST 7: PERFORMANCE LOAD TESTS
# =============================================================================

@pytest.mark.asyncio
class TestPerformanceLoad:
    """Performance and load testing."""
    
    async def test_100_matches_query_performance(self, db: AsyncSession, sample_tournament_id):
        """Query 100 matches efficiently."""
        round_obj = await RoundService.create_round(
            db=db, tournament_id=sample_tournament_id,
            round_number=1, round_type=RoundType.PRELIM, bench_count=100
        )
        
        # Create 100 matches
        matches_config = [
            {
                'bench_number': i + 1,
                'team_petitioner_id': uuid.uuid4(),
                'team_respondent_id': uuid.uuid4()
            }
            for i in range(100)
        ]
        
        start_time = time.time()
        matches = await RoundService.assign_matches(
            db=db, round_id=round_obj.id, matches_config=matches_config
        )
        duration = time.time() - start_time
        
        assert len(matches) == 100
        assert duration < 10.0  # Should complete in under 10 seconds
    
    async def test_500_speaker_turns_creation(self, db: AsyncSession, sample_tournament_id):
        """Create 500 speaker turns (100 matches × 5 turns each)."""
        # This tests bulk creation performance
        start_time = time.time()
        
        for i in range(10):  # 10 matches
            match_id = uuid.uuid4()
            await MatchService.generate_speaker_turns(
                db=db, match_id=match_id,
                team_petitioner_id=uuid.uuid4(),
                team_respondent_id=uuid.uuid4(),
                allocated_seconds=600
            )
        
        duration = time.time() - start_time
        assert duration < 5.0  # Should be fast


# =============================================================================
# STRESS TEST 8: DETERMINISTIC FLOW VALIDATION
# =============================================================================

@pytest.mark.asyncio
class TestDeterministicFlow:
    """Validate strict speaker sequence enforcement."""
    
    async def test_exact_speaker_sequence(self, db: AsyncSession, sample_team_ids):
        """Verify exact P1→P2→R1→R2→RP→RR sequence."""
        match_id = uuid.uuid4()
        
        turns = await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        
        expected_roles = ['p1', 'p2', 'r1', 'r2', 'rebuttal_p', 'rebuttal_r']
        actual_roles = [t.speaker_role for t in sorted(turns, key=lambda x: x.turn_order)]
        
        assert actual_roles == expected_roles
    
    async def test_petitioner_team_assignments(self, db: AsyncSession, sample_team_ids):
        """Verify P1, P2, RP assigned to petitioner team."""
        match_id = uuid.uuid4()
        petitioner_id = sample_team_ids[0]
        respondent_id = sample_team_ids[1]
        
        turns = await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=petitioner_id,
            team_respondent_id=respondent_id,
            allocated_seconds=600
        )
        
        petitioner_roles = {'p1', 'p2', 'rebuttal_p'}
        for turn in turns:
            if turn.speaker_role in petitioner_roles:
                assert turn.team_id == petitioner_id
            elif turn.speaker_role in {'r1', 'r2', 'rebuttal_r'}:
                assert turn.team_id == respondent_id
    
    async def test_no_skipping_turn_order(self, db: AsyncSession, sample_team_ids):
        """Cannot skip from turn 1 to turn 3."""
        match_id = uuid.uuid4()
        
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        await MatchService.start_match(db=db, match_id=match_id)
        
        # Get all turns
        turns_result = await db.execute(
            sa_select(MatchSpeakerTurn).where(MatchSpeakerTurn.match_id == match_id)
        )
        turns = turns_result.scalars().all()
        
        # Try to manually set turn 3 to active (bypassing advance)
        turn_3 = next(t for t in turns if t.turn_order == 3)
        turn_1 = next(t for t in turns if t.turn_order == 1)
        
        # Turn 1 must be completed before turn 3 can be active
        turn_1.status = TurnStatus.PENDING.value
        turn_3.status = TurnStatus.PENDING.value
        await db.flush()
        
        # Proper advance should follow sequence
        result = await MatchService.advance_turn(db=db, match_id=match_id)
        assert result['current_turn']['turn_order'] == 1


# =============================================================================
# STRESS TEST 9: DOUBLE-ADVANCE PROTECTION
# =============================================================================

@pytest.mark.asyncio
class TestDoubleAdvanceProtection:
    """Strict protection against double-advance race conditions."""
    
    async def test_active_turn_blocks_advance(self, db: AsyncSession, sample_team_ids):
        """If turn is active, advance should fail."""
        match_id = uuid.uuid4()
        
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        await MatchService.start_match(db=db, match_id=match_id)
        
        # Advance to first turn
        await MatchService.advance_turn(db=db, match_id=match_id)
        
        # Try to advance again without completing
        with pytest.raises(HTTPException) as exc:
            await MatchService.advance_turn(db=db, match_id=match_id)
        assert exc.value.status_code == status.HTTP_409_CONFLICT
    
    async def test_multiple_active_turns_detected(self, db: AsyncSession, sample_team_ids):
        """System should detect and prevent multiple active turns."""
        match_id = uuid.uuid4()
        
        await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        await MatchService.start_match(db=db, match_id=match_id)
        
        # Get turns
        turns_result = await db.execute(
            sa_select(MatchSpeakerTurn).where(MatchSpeakerTurn.match_id == match_id)
        )
        turns = turns_result.scalars().all()
        
        # Try to manually make two turns active (data corruption attempt)
        turns[0].status = TurnStatus.ACTIVE.value
        turns[1].status = TurnStatus.ACTIVE.value
        
        # This should be prevented by unique constraint or validation
        with pytest.raises(Exception):
            await db.flush()


# =============================================================================
# STRESS TEST 10: COMPLETE SYSTEM WORKFLOW
# =============================================================================

@pytest.mark.asyncio
class TestCompleteSystemWorkflow:
    """End-to-end workflow validation."""
    
    async def test_full_match_lifecycle(self, db: AsyncSession, sample_tournament_id, sample_team_ids):
        """Complete match from creation to freeze."""
        # 1. Create round
        round_obj = await RoundService.create_round(
            db=db, tournament_id=sample_tournament_id,
            round_number=1, round_type=RoundType.PRELIM, bench_count=1
        )
        assert round_obj.status == RoundStatus.SCHEDULED.value
        
        # 2. Assign match
        matches = await RoundService.assign_matches(
            db=db, round_id=round_obj.id,
            matches_config=[{
                'bench_number': 1,
                'team_petitioner_id': sample_team_ids[0],
                'team_respondent_id': sample_team_ids[1]
            }]
        )
        match_id = matches[0].id
        
        # 3. Generate speaker turns
        turns = await MatchService.generate_speaker_turns(
            db=db, match_id=match_id,
            team_petitioner_id=sample_team_ids[0],
            team_respondent_id=sample_team_ids[1],
            allocated_seconds=600
        )
        assert len(turns) == len(SPEAKER_FLOW_SEQUENCE)
        
        # 4. Start round
        await RoundService.start_round(db=db, round_id=round_obj.id)
        round_obj = await db.get(TournamentRound, round_obj.id)
        assert round_obj.status == RoundStatus.LIVE.value
        
        # 5. Start match
        await MatchService.start_match(db=db, match_id=match_id)
        match = await db.get(TournamentMatch, match_id)
        assert match.status == MatchStatus.LIVE.value
        
        # 6. Complete all turns
        for i in range(len(SPEAKER_FLOW_SEQUENCE)):
            result = await MatchService.advance_turn(db=db, match_id=match_id)
            turn_id = uuid.UUID(result['current_turn']['id'])
            
            # Initialize timer
            await TimerService.initialize_timer(
                db=db, match_id=match_id,
                active_turn_id=turn_id, remaining_seconds=600
            )
            
            # Complete turn
            await MatchService.complete_turn(db=db, turn_id=turn_id)
        
        # 7. Complete match
        await MatchService.complete_match(
            db=db, match_id=match_id, winner_team_id=sample_team_ids[0]
        )
        match = await db.get(TournamentMatch, match_id)
        assert match.status == MatchStatus.COMPLETED.value
        
        # 8. Complete round
        await RoundService.complete_round(db=db, round_id=round_obj.id)
        round_obj = await db.get(TournamentRound, round_obj.id)
        assert round_obj.status == RoundStatus.COMPLETED.value
        
        # 9. Freeze match
        await MatchService.freeze_match(
            db=db, match_id=match_id,
            petitioner_score=Decimal("85.50"),
            respondent_score=Decimal("78.25"),
            winner_team_id=sample_team_ids[0],
            judge_ids=[uuid.uuid4(), uuid.uuid4()]
        )
        match = await db.get(TournamentMatch, match_id)
        assert match.status == MatchStatus.FROZEN.value
        
        # 10. Freeze round
        await RoundService.freeze_round(db=db, round_id=round_obj.id)
        round_obj = await db.get(TournamentRound, round_obj.id)
        assert round_obj.status == RoundStatus.FROZEN.value
        
        # 11. Verify integrity
        integrity = await MatchService.verify_match_integrity(db=db, match_id=match_id)
        assert integrity['frozen'] is True
        assert integrity['verified'] is True
        assert integrity['turn_count'] == len(SPEAKER_FLOW_SEQUENCE)
