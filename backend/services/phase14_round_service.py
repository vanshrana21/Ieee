"""
Phase 14 — Round Service

Strict transactional round management with state machine enforcement.
"""
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.orm.phase14_round_engine import (
    TournamentRound, RoundType, RoundStatus,
    TournamentMatch, MatchStatus,
    MatchSpeakerTurn, SpeakerRole, TurnStatus,
    SPEAKER_FLOW_SEQUENCE
)


class RoundServiceError(Exception):
    """Base exception for round service errors."""
    pass


class InvalidStateTransitionError(RoundServiceError):
    """Raised when attempting invalid state transition."""
    pass


class RoundService:
    """
    Service for managing tournament rounds.
    
    All operations are transaction-safe with proper locking.
    """
    
    @staticmethod
    async def create_round(
        db: AsyncSession,
        tournament_id: uuid.UUID,
        round_number: int,
        round_type: RoundType,
        bench_count: int = 0
    ) -> TournamentRound:
        """
        Create a new round in SCHEDULED status.
        
        Args:
            db: Database session
            tournament_id: Tournament UUID
            round_number: Round number (must be unique per tournament)
            round_type: Type of round (PRELIM, QUARTER_FINAL, etc.)
            bench_count: Number of benches/matches in this round
            
        Returns:
            Created TournamentRound
            
        Raises:
            HTTPException: If round number already exists for tournament
        """
        # Check for duplicate round number
        result = await db.execute(
            select(TournamentRound).where(
                and_(
                    TournamentRound.tournament_id == tournament_id,
                    TournamentRound.round_number == round_number
                )
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Round {round_number} already exists for this tournament"
            )
        
        round_obj = TournamentRound(
            id=uuid.uuid4(),
            tournament_id=tournament_id,
            round_number=round_number,
            round_type=round_type.value,
            status=RoundStatus.SCHEDULED.value,
            bench_count=bench_count
        )
        db.add(round_obj)
        await db.commit()
        await db.refresh(round_obj)
        return round_obj
    
    @staticmethod
    async def assign_matches(
        db: AsyncSession,
        round_id: uuid.UUID,
        matches_config: List[Dict[str, Any]]
    ) -> List[TournamentMatch]:
        """
        Assign matches to a round.
        
        Args:
            db: Database session
            round_id: Round UUID
            matches_config: List of match configurations
                Each config must have:
                - bench_number: int
                - team_petitioner_id: UUID
                - team_respondent_id: UUID
                
        Returns:
            List of created TournamentMatch objects
            
        Raises:
            HTTPException: If round is not in SCHEDULED status
            HTTPException: If bench_number already exists
        """
        # Lock the round row
        result = await db.execute(
            select(TournamentRound).where(
                TournamentRound.id == round_id
            ).with_for_update()
        )
        round_obj = result.scalar_one_or_none()
        
        if not round_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Round not found"
            )
        
        if round_obj.status != RoundStatus.SCHEDULED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot assign matches to round in {round_obj.status} status"
            )
        
        # Check for duplicate bench numbers
        existing_benches = set()
        for config in matches_config:
            bench_num = config['bench_number']
            if bench_num in existing_benches:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Duplicate bench number: {bench_num}"
                )
            existing_benches.add(bench_num)
        
        created_matches = []
        for config in matches_config:
            match = TournamentMatch(
                id=uuid.uuid4(),
                round_id=round_id,
                bench_number=config['bench_number'],
                team_petitioner_id=config['team_petitioner_id'],
                team_respondent_id=config['team_respondent_id'],
                status=MatchStatus.SCHEDULED.value,
                locked=False
            )
            db.add(match)
            created_matches.append(match)
        
        await db.commit()
        return created_matches
    
    @staticmethod
    async def start_round(
        db: AsyncSession,
        round_id: uuid.UUID
    ) -> TournamentRound:
        """
        Start a round (transition from SCHEDULED to LIVE).
        
        Args:
            db: Database session
            round_id: Round UUID
            
        Returns:
            Updated TournamentRound
            
        Raises:
            HTTPException: If round not found
            HTTPException: If round not in SCHEDULED status
            HTTPException: If no matches assigned
        """
        # Lock the round row
        result = await db.execute(
            select(TournamentRound).where(
                TournamentRound.id == round_id
            ).with_for_update()
        )
        round_obj = result.scalar_one_or_none()
        
        if not round_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Round not found"
            )
        
        if round_obj.status != RoundStatus.SCHEDULED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot start round in {round_obj.status} status"
            )
        
        # Check if matches exist
        matches_result = await db.execute(
            select(TournamentMatch).where(
                TournamentMatch.round_id == round_id
            )
        )
        matches = matches_result.scalars().all()
        
        if not matches:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot start round without assigned matches"
            )
        
        round_obj.status = RoundStatus.LIVE.value
        await db.commit()
        await db.refresh(round_obj)
        return round_obj
    
    @staticmethod
    async def complete_round(
        db: AsyncSession,
        round_id: uuid.UUID
    ) -> TournamentRound:
        """
        Complete a round (transition from LIVE to COMPLETED).
        
        All matches must be COMPLETED or FROZEN.
        
        Args:
            db: Database session
            round_id: Round UUID
            
        Returns:
            Updated TournamentRound
        """
        # Lock the round row
        result = await db.execute(
            select(TournamentRound).where(
                TournamentRound.id == round_id
            ).with_for_update()
        )
        round_obj = result.scalar_one_or_none()
        
        if not round_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Round not found"
            )
        
        if round_obj.status != RoundStatus.LIVE.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot complete round in {round_obj.status} status"
            )
        
        # Check all matches are completed
        matches_result = await db.execute(
            select(TournamentMatch).where(
                TournamentMatch.round_id == round_id
            )
        )
        matches = matches_result.scalars().all()
        
        incomplete = [m for m in matches if m.status not in (MatchStatus.COMPLETED.value, MatchStatus.FROZEN.value)]
        if incomplete:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot complete round. {len(incomplete)} matches not completed."
            )
        
        round_obj.status = RoundStatus.COMPLETED.value
        await db.commit()
        await db.refresh(round_obj)
        return round_obj
    
    @staticmethod
    async def freeze_round(
        db: AsyncSession,
        round_id: uuid.UUID
    ) -> TournamentRound:
        """
        Freeze a round (transition from COMPLETED to FROZEN).
        
        This is the terminal state. No further modifications allowed.
        
        Args:
            db: Database session
            round_id: Round UUID
            
        Returns:
            Updated TournamentRound
        """
        # Lock the round row
        result = await db.execute(
            select(TournamentRound).where(
                TournamentRound.id == round_id
            ).with_for_update()
        )
        round_obj = result.scalar_one_or_none()
        
        if not round_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Round not found"
            )
        
        if round_obj.status != RoundStatus.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot freeze round in {round_obj.status} status"
            )
        
        round_obj.status = RoundStatus.FROZEN.value
        await db.commit()
        await db.refresh(round_obj)
        return round_obj
    
    @staticmethod
    async def get_round_with_matches(
        db: AsyncSession,
        round_id: uuid.UUID
    ) -> Optional[TournamentRound]:
        """
        Get round with all matches loaded.
        
        Args:
            db: Database session
            round_id: Round UUID
            
        Returns:
            TournamentRound with matches, or None
        """
        result = await db.execute(
            select(TournamentRound)
            .where(TournamentRound.id == round_id)
            .options(selectinload(TournamentRound.matches))
        )
        return result.scalar_one_or_none()
