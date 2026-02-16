"""
Phase 15 — Snapshot Builder Service

Builds deterministic, hashable snapshots of match state for AI evaluation.
Must validate match is FROZEN before building snapshot.
"""
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select as sa_select
from fastapi import HTTPException, status

from backend.services.phase15_hash_service import HashService
from backend.services.phase15_credit_optimizer import CreditOptimizerService
from backend.orm.phase14_round_engine import (
    TournamentMatch, MatchSpeakerTurn, MatchScoreLock,
    MatchStatus, TurnStatus, SpeakerRole, SPEAKER_FLOW_SEQUENCE
)


class SnapshotBuilderService:
    """
    Builds compact, deterministic snapshots of match state.
    Snapshots are used for AI evaluation and must be reproducible.
    """

    # Maximum length for summaries
    MAX_SUMMARY_LENGTH = 1000

    @staticmethod
    async def build_match_snapshot(
        db: AsyncSession,
        match_id: uuid.UUID,
        validate_frozen: bool = True
    ) -> Dict[str, Any]:
        """
        Build a complete snapshot of a match for AI evaluation.

        Args:
            db: Database session
            match_id: Match UUID
            validate_frozen: Whether to validate match is frozen

        Returns:
            Dictionary containing match snapshot

        Raises:
            HTTPException: If match not found or not frozen
        """
        # Fetch match
        match_result = await db.execute(
            sa_select(TournamentMatch).where(TournamentMatch.id == match_id)
        )
        match = match_result.scalar_one_or_none()

        if not match:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Match {match_id} not found"
            )

        # Validate match is frozen (required for official evaluation)
        if validate_frozen and match.status != MatchStatus.FROZEN.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cannot evaluate unfrozen match. Status: {match.status}"
            )

        # Fetch speaker turns
        turns_result = await db.execute(
            sa_select(MatchSpeakerTurn)
            .where(MatchSpeakerTurn.match_id == match_id)
            .order_by(MatchSpeakerTurn.turn_order)
        )
        turns = turns_result.scalars().all()

        # Fetch score lock (if frozen)
        score_lock = None
        if match.status == MatchStatus.FROZEN.value:
            lock_result = await db.execute(
                sa_select(MatchScoreLock).where(MatchScoreLock.match_id == match_id)
            )
            score_lock = lock_result.scalar_one_or_none()

        # Build speaker summaries by role
        speaker_summaries = SnapshotBuilderService._build_speaker_summaries(turns)

        # Build objection statistics
        objection_stats = SnapshotBuilderService._build_objection_stats(turns)

        # Build heuristics
        heuristics = SnapshotBuilderService._build_heuristics(turns, score_lock)

        # Construct snapshot
        snapshot = {
            "match_id": str(match_id),
            "bench_number": match.bench_number,
            "petitioner_team_id": str(match.team_petitioner_id),
            "respondent_team_id": str(match.team_respondent_id),
            "match_status": match.status,

            # Speaker summaries
            "petitioner_summary": speaker_summaries.get("petitioner", ""),
            "respondent_summary": speaker_summaries.get("respondent", ""),
            "rebuttal_summary": speaker_summaries.get("rebuttal", ""),

            # Turn sequence
            "speaker_sequence": [
                {
                    "role": turn.speaker_role,
                    "order": turn.turn_order,
                    "actual_seconds": turn.actual_seconds,
                    "status": turn.status,
                }
                for turn in turns
            ],

            # Statistics
            "objection_stats": objection_stats,
            "heuristics": heuristics,

            # Score lock (if available)
            "official_scores": {
                "petitioner": str(score_lock.total_petitioner_score) if score_lock else None,
                "respondent": str(score_lock.total_respondent_score) if score_lock else None,
                "winner": str(score_lock.winner_team_id) if score_lock else None,
            } if score_lock else None,
        }

        # Optimize for AI consumption
        optimized = CreditOptimizerService.optimize_match_summary(snapshot)

        # Compute hash
        snapshot_hash = HashService.generate_snapshot_hash(optimized)

        return {
            "snapshot": optimized,
            "snapshot_hash": snapshot_hash,
            "turn_count": len(turns),
            "is_frozen": match.status == MatchStatus.FROZEN.value,
        }

    @staticmethod
    def _build_speaker_summaries(turns: List[MatchSpeakerTurn]) -> Dict[str, str]:
        """
        Build text summaries for petitioner, respondent, and rebuttal phases.
        """
        summaries = {
            "petitioner": [],
            "respondent": [],
            "rebuttal": [],
        }

        for turn in turns:
            role = turn.speaker_role

            if role in [SpeakerRole.P1.value, SpeakerRole.P2.value]:
                summaries["petitioner"].append(
                    f"{role.upper()}: {turn.actual_seconds}s, status={turn.status}"
                )
            elif role in [SpeakerRole.R1.value, SpeakerRole.R2.value]:
                summaries["respondent"].append(
                    f"{role.upper()}: {turn.actual_seconds}s, status={turn.status}"
                )
            elif role in [SpeakerRole.REBUTTAL_P.value, SpeakerRole.REBUTTAL_R.value]:
                summaries["rebuttal"].append(
                    f"{role.upper()}: {turn.actual_seconds}s, status={turn.status}"
                )

        return {
            key: "; ".join(items) if items else "N/A"
            for key, items in summaries.items()
        }

    @staticmethod
    def _build_objection_stats(turns: List[MatchSpeakerTurn]) -> Dict[str, Any]:
        """
        Build objection statistics from speaker turns.
        """
        total_objections = 0
        sustained = 0
        overruled = 0

        # Note: In a real implementation, this would query objection records
        # For now, we return placeholder stats
        return {
            "total_objections": total_objections,
            "sustained": sustained,
            "overruled": overruled,
            "objection_rate": 0.0 if not turns else total_objections / len(turns),
        }

    @staticmethod
    def _build_heuristics(
        turns: List[MatchSpeakerTurn],
        score_lock: Optional[MatchScoreLock]
    ) -> Dict[str, Any]:
        """
        Build heuristic metrics from turn data.
        """
        if not turns:
            return {}

        # Calculate time usage statistics
        allocated_times = [t.allocated_seconds for t in turns]
        actual_times = [t.actual_seconds or 0 for t in turns]

        total_allocated = sum(allocated_times)
        total_actual = sum(actual_times)

        # Time efficiency (how well teams used their time)
        time_efficiency = total_actual / total_allocated if total_allocated > 0 else 0

        # Turn completion rate
        completed_turns = sum(1 for t in turns if t.status == TurnStatus.COMPLETED.value)
        completion_rate = completed_turns / len(turns) if turns else 0

        return {
            "time_efficiency": round(time_efficiency, 2),
            "completion_rate": round(completion_rate, 2),
            "total_allocated_seconds": total_allocated,
            "total_actual_seconds": total_actual,
            "turn_count": len(turns),
            "has_score_lock": score_lock is not None,
        }

    @staticmethod
    async def verify_snapshot_integrity(
        db: AsyncSession,
        match_id: uuid.UUID,
        expected_hash: str
    ) -> bool:
        """
        Verify that a stored snapshot hash matches current match state.

        Args:
            db: Database session
            match_id: Match UUID
            expected_hash: Expected snapshot hash

        Returns:
            True if hash matches, False otherwise
        """
        try:
            result = await SnapshotBuilderService.build_match_snapshot(
                db=db,
                match_id=match_id,
                validate_frozen=False
            )
            current_hash = result["snapshot_hash"]
            return HashService.compare_hashes(current_hash, expected_hash)
        except Exception:
            return False

    @staticmethod
    def get_snapshot_summary(snapshot: Dict[str, Any]) -> str:
        """
        Get human-readable summary of snapshot.
        """
        return (
            f"Match {snapshot.get('match_id', 'unknown')}: "
            f"{snapshot.get('turn_count', 0)} turns, "
            f"frozen={snapshot.get('is_frozen', False)}"
        )


# Singleton instance
snapshot_builder = SnapshotBuilderService()
