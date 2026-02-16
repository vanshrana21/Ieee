"""
Phase 14 — Timer Service

Crash-recoverable timer with WebSocket broadcast.
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.orm.phase14_round_engine import (
    MatchTimerState, MatchSpeakerTurn, TurnStatus,
    TournamentMatch, MatchStatus
)


class TimerService:
    """
    Service for managing match timers.
    
    Timer state is DB-backed for crash recovery.
    Auto-closes turns when time expires.
    """
    
    @staticmethod
    async def initialize_timer(
        db: AsyncSession,
        match_id: uuid.UUID,
        active_turn_id: uuid.UUID,
        remaining_seconds: int
    ) -> MatchTimerState:
        """
        Initialize timer state for a match.
        
        Args:
            db: Database session
            match_id: Match UUID
            active_turn_id: Active turn UUID
            remaining_seconds: Initial remaining seconds
            
        Returns:
            Created MatchTimerState
        """
        # Check if timer already exists
        result = await db.execute(
            select(MatchTimerState).where(
                MatchTimerState.match_id == match_id
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            # Update existing timer
            existing.active_turn_id = active_turn_id
            existing.remaining_seconds = remaining_seconds
            existing.paused = False
            existing.last_tick = datetime.utcnow()
            await db.commit()
            await db.refresh(existing)
            return existing
        
        # Create new timer
        timer = MatchTimerState(
            match_id=match_id,
            active_turn_id=active_turn_id,
            remaining_seconds=remaining_seconds,
            paused=False,
            last_tick=datetime.utcnow()
        )
        db.add(timer)
        await db.commit()
        await db.refresh(timer)
        return timer
    
    @staticmethod
    async def tick(
        db: AsyncSession,
        match_id: uuid.UUID
    ) -> Optional[MatchTimerState]:
        """
        Process a timer tick.
        
        Updates remaining_seconds based on elapsed time.
        Auto-completes turn if time hits 0.
        
        Args:
            db: Database session
            match_id: Match UUID
            
        Returns:
            Updated MatchTimerState or None if not found
        """
        # Lock timer row
        result = await db.execute(
            select(MatchTimerState).where(
                MatchTimerState.match_id == match_id
            ).with_for_update()
        )
        timer = result.scalar_one_or_none()
        
        if not timer:
            return None
        
        if timer.paused:
            # Just update last_tick, no time deduction
            timer.last_tick = datetime.utcnow()
            await db.commit()
            return timer
        
        # Calculate elapsed time
        now = datetime.utcnow()
        if timer.last_tick:
            elapsed = (now - timer.last_tick).total_seconds()
            timer.remaining_seconds = max(0, timer.remaining_seconds - int(elapsed))
        
        timer.last_tick = now
        
        # Check if time expired
        if timer.remaining_seconds <= 0 and timer.active_turn_id:
            # Time's up - auto-complete the turn
            await TimerService._auto_complete_turn(db, timer.active_turn_id)
            timer.active_turn_id = None
        
        await db.commit()
        await db.refresh(timer)
        return timer
    
    @staticmethod
    async def _auto_complete_turn(
        db: AsyncSession,
        turn_id: uuid.UUID
    ) -> MatchSpeakerTurn:
        """
        Auto-complete a turn when timer expires.
        
        Args:
            db: Database session
            turn_id: Turn UUID
            
        Returns:
            Completed MatchSpeakerTurn
        """
        from sqlalchemy import select as sa_select
        
        result = await db.execute(
            sa_select(MatchSpeakerTurn).where(
                MatchSpeakerTurn.id == turn_id
            ).with_for_update()
        )
        turn = result.scalar_one_or_none()
        
        if turn and turn.status == TurnStatus.ACTIVE.value:
            turn.status = TurnStatus.COMPLETED.value
            turn.ended_at = datetime.utcnow()
            await db.commit()
            await db.refresh(turn)
        
        return turn
    
    @staticmethod
    async def pause_timer(
        db: AsyncSession,
        match_id: uuid.UUID
    ) -> MatchTimerState:
        """
        Pause the match timer.
        
        Args:
            db: Database session
            match_id: Match UUID
            
        Returns:
            Updated MatchTimerState
        """
        result = await db.execute(
            select(MatchTimerState).where(
                MatchTimerState.match_id == match_id
            ).with_for_update()
        )
        timer = result.scalar_one_or_none()
        
        if not timer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Timer not found"
            )
        
        timer.paused = True
        timer.last_tick = datetime.utcnow()
        
        await db.commit()
        await db.refresh(timer)
        return timer
    
    @staticmethod
    async def resume_timer(
        db: AsyncSession,
        match_id: uuid.UUID
    ) -> MatchTimerState:
        """
        Resume the match timer.
        
        Args:
            db: Database session
            match_id: Match UUID
            
        Returns:
            Updated MatchTimerState
        """
        result = await db.execute(
            select(MatchTimerState).where(
                MatchTimerState.match_id == match_id
            ).with_for_update()
        )
        timer = result.scalar_one_or_none()
        
        if not timer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Timer not found"
            )
        
        timer.paused = False
        timer.last_tick = datetime.utcnow()
        
        await db.commit()
        await db.refresh(timer)
        return timer
    
    @staticmethod
    async def get_timer_state(
        db: AsyncSession,
        match_id: uuid.UUID
    ) -> Optional[MatchTimerState]:
        """
        Get current timer state.
        
        Args:
            db: Database session
            match_id: Match UUID
            
        Returns:
            MatchTimerState or None
        """
        result = await db.execute(
            select(MatchTimerState)
            .where(MatchTimerState.match_id == match_id)
            .options(selectinload(MatchTimerState.active_turn))
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def restore_live_matches(
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """
        Crash recovery: Restore all LIVE matches with elapsed time adjustment.
        
        Detects LIVE matches and recalculates timer state based on elapsed time.
        Auto-completes turns that expired during downtime.
        
        Args:
            db: Database session
            
        Returns:
            List of live match states for recovery
        """
        result = await db.execute(
            select(TournamentMatch).where(
                TournamentMatch.status == MatchStatus.LIVE.value
            ).options(
                selectinload(TournamentMatch.timer_state),
                selectinload(TournamentMatch.speaker_turns)
            )
        )
        live_matches = result.scalars().all()
        
        recovery_data = []
        for match in live_matches:
            timer = match.timer_state
            active_turn = timer.active_turn if timer else None
            
            # Calculate elapsed time and adjust remaining seconds
            adjusted_remaining = timer.remaining_seconds if timer else 0
            was_paused = timer.paused if timer else True
            elapsed_downtime = 0
            
            if timer and not timer.paused and timer.last_tick:
                now = datetime.utcnow()
                elapsed_downtime = int((now - timer.last_tick).total_seconds())
                adjusted_remaining = max(0, timer.remaining_seconds - elapsed_downtime)
                
                # Check if turn expired during downtime
                if adjusted_remaining <= 0 and active_turn and active_turn.status == TurnStatus.ACTIVE.value:
                    # Auto-complete the expired turn
                    active_turn.status = TurnStatus.COMPLETED.value
                    active_turn.ended_at = now
                    timer.active_turn_id = None
                    await db.flush()
            
            recovery_data.append({
                "match_id": str(match.id),
                "status": match.status,
                "timer": {
                    "active_turn_id": str(timer.active_turn_id) if timer and timer.active_turn_id else None,
                    "remaining_seconds": adjusted_remaining,
                    "original_remaining": timer.remaining_seconds if timer else 0,
                    "elapsed_downtime": elapsed_downtime,
                    "paused": was_paused,
                    "last_tick": timer.last_tick.isoformat() if timer and timer.last_tick else None
                },
                "active_turn": {
                    "id": str(active_turn.id) if active_turn else None,
                    "turn_order": active_turn.turn_order if active_turn else None,
                    "speaker_role": active_turn.speaker_role if active_turn else None,
                    "status": active_turn.status if active_turn else None
                } if active_turn else None,
                "recovered_at": datetime.utcnow().isoformat()
            })
        
        await db.commit()
        return recovery_data
    
    @staticmethod
    async def broadcast_timer_update(
        match_id: uuid.UUID,
        timer_state: MatchTimerState,
        active_turn: Optional[MatchSpeakerTurn]
    ) -> Dict[str, Any]:
        """
        Prepare timer update for WebSocket broadcast.
        
        Args:
            match_id: Match UUID
            timer_state: Current timer state
            active_turn: Current active turn
            
        Returns:
            Dict formatted for WebSocket broadcast
        """
        return {
            "event": "timer_update",
            "match_id": str(match_id),
            "timestamp": datetime.utcnow().isoformat(),
            "timer": {
                "remaining_seconds": timer_state.remaining_seconds,
                "paused": timer_state.paused,
                "active_turn_id": str(timer_state.active_turn_id) if timer_state.active_turn_id else None
            },
            "turn": {
                "id": str(active_turn.id) if active_turn else None,
                "turn_order": active_turn.turn_order if active_turn else None,
                "speaker_role": active_turn.speaker_role if active_turn else None,
                "status": active_turn.status if active_turn else None,
                "allocated_seconds": active_turn.allocated_seconds if active_turn else 0
            } if active_turn else None
        }
