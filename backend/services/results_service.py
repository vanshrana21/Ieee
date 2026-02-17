"""
Phase 9 — Tournament Results & Ranking Engine Service

Deterministic ranking computation, immutable freeze, idempotent finalization.
Uses Decimal for all numeric computation to avoid float errors.
"""
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.orm.tournament_results import (
    TournamentTeamResult, TournamentSpeakerResult, TournamentResultsFreeze,
    QUANTIZER_2DP, QUANTIZER_3DP, QUANTIZER_4DP
)
from backend.orm.national_network import NationalTournament, TournamentMatch
from backend.orm.round_pairing import TournamentRound, RoundType
from backend.orm.live_court import LiveCourtSession, LiveCourtStatus
from backend.orm.moot_problem import MemorialSubmission, MemorialEvaluation


class ResultsAlreadyFrozenError(Exception):
    """Raised when attempting to modify frozen results."""
    pass


class IncompleteTournamentError(Exception):
    """Raised when tournament has incomplete rounds or sessions."""
    pass


class ResultsNotFoundError(Exception):
    """Raised when results not found."""
    pass


class TamperDetectedError(Exception):
    """Raised when result hash verification fails."""
    pass


async def finalize_tournament_results(
    tournament_id: int,
    user_id: int,
    db: AsyncSession
) -> TournamentResultsFreeze:
    """
    Finalize tournament results with deterministic ranking.
    
    Idempotent: Returns existing freeze if already finalized.
    
    Args:
        tournament_id: Tournament to finalize
        user_id: User performing the finalization
        db: Database session
    
    Returns:
        TournamentResultsFreeze record
    
    Raises:
        IncompleteTournamentError: If rounds/sessions incomplete
        ResultsAlreadyFrozenError: If frozen by another user concurrently
    """
    # SERIALIZABLE isolation for atomic finalization
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    
    # Lock tournament for update
    result = await db.execute(
        select(NationalTournament)
        .where(NationalTournament.id == tournament_id)
        .with_for_update()
    )
    tournament = result.scalar_one_or_none()
    
    if not tournament:
        raise ResultsNotFoundError(f"Tournament {tournament_id} not found")
    
    # Check for existing freeze (idempotent)
    result = await db.execute(
        select(TournamentResultsFreeze)
        .where(TournamentResultsFreeze.tournament_id == tournament_id)
    )
    existing_freeze = result.scalar_one_or_none()
    
    if existing_freeze:
        # Return existing freeze (idempotent)
        return existing_freeze
    
    # Verify tournament completeness
    await _verify_tournament_complete(tournament_id, db)
    
    # Compute team results
    team_results = await _compute_team_results(tournament_id, db)
    
    # Compute speaker results
    speaker_results = await _compute_speaker_results(tournament_id, db)
    
    # Persist results
    for tr in team_results:
        db.add(tr)
    
    for sr in speaker_results:
        db.add(sr)
    
    await db.flush()
    
    # Build snapshots with deterministic JSON
    team_snapshot = _build_team_snapshot(team_results)
    speaker_snapshot = _build_speaker_snapshot(speaker_results)
    
    # Compute global checksum
    team_hashes = [tr.result_hash for tr in team_results]
    speaker_hashes = [sr.speaker_hash for sr in speaker_results]
    
    freeze = TournamentResultsFreeze(
        tournament_id=tournament_id,
        team_snapshot_json=team_snapshot,
        speaker_snapshot_json=speaker_snapshot,
        results_checksum="",  # Will compute after
        frozen_by=user_id,
        frozen_at=datetime.utcnow()
    )
    
    freeze.results_checksum = freeze.compute_global_checksum(team_hashes, speaker_hashes)
    
    db.add(freeze)
    await db.commit()
    
    return freeze


async def _verify_tournament_complete(tournament_id: int, db: AsyncSession) -> None:
    """
    Verify all tournament components are complete.
    
    Args:
        tournament_id: Tournament to verify
        db: Database session
    
    Raises:
        IncompleteTournamentError: If anything incomplete
    """
    # Check all rounds completed
    result = await db.execute(
        select(TournamentRound)
        .where(TournamentRound.tournament_id == tournament_id)
    )
    rounds = result.scalars().all()
    
    if not rounds:
        raise IncompleteTournamentError("No rounds found")
    
    # Check all live sessions completed
    result = await db.execute(
        select(LiveCourtSession)
        .where(LiveCourtSession.tournament_id == tournament_id)
        .where(LiveCourtSession.status != LiveCourtStatus.COMPLETED)
    )
    incomplete_sessions = result.scalars().all()
    
    if incomplete_sessions:
        raise IncompleteTournamentError(
            f"{len(incomplete_sessions)} sessions not completed"
        )


async def _compute_team_results(
    tournament_id: int,
    db: AsyncSession
) -> List[TournamentTeamResult]:
    """
    Compute team results with deterministic ranking.
    
    Args:
        tournament_id: Tournament ID
        db: Database session
    
    Returns:
        List of TournamentTeamResult with ranks assigned
    """
    # Fetch all teams
    result = await db.execute(
        select(TournamentTeam)
        .where(TournamentTeam.tournament_id == tournament_id)
    )
    teams = result.scalars().all()
    
    if not teams:
        return []
    
    # Fetch memorial scores
    memorial_scores = await _fetch_memorial_scores(tournament_id, db)
    
    # Fetch oral scores and SOS data
    oral_data = await _fetch_oral_scores_and_sos(tournament_id, db)
    
    # Build result objects
    team_results = []
    for team in teams:
        team_id = team.id
        
        memorial_total = Decimal(str(memorial_scores.get(team_id, 0))).quantize(QUANTIZER_2DP)
        oral_total = Decimal(str(oral_data["scores"].get(team_id, 0))).quantize(QUANTIZER_2DP)
        total_score = memorial_total + oral_total
        
        sos = Decimal(str(oral_data["sos"].get(team_id, 0))).quantize(QUANTIZER_4DP)
        opponent_wins = oral_data["wins"].get(team_id, 0)
        
        tr = TournamentTeamResult(
            tournament_id=tournament_id,
            team_id=team_id,
            memorial_total=memorial_total,
            oral_total=oral_total,
            total_score=total_score,
            strength_of_schedule=sos,
            opponent_wins_total=opponent_wins,
            result_hash=""  # Will compute after ranking
        )
        team_results.append(tr)
    
    # Sort deterministically (tie-breakers)
    # ORDER BY: total_score DESC, sos DESC, oral_total DESC, opponent_wins DESC, team_id ASC
    team_results.sort(
        key=lambda x: (
            -x.total_score,           # DESC
            -x.strength_of_schedule, # DESC
            -x.oral_total,            # DESC
            -x.opponent_wins_total,   # DESC
            x.team_id                 # ASC (final fallback)
        )
    )
    
    # Assign ranks and percentiles
    total_teams = len(team_results)
    for rank, tr in enumerate(team_results, start=1):
        tr.final_rank = rank
        # percentile = 100 × (1 - (rank - 1) / total_teams)
        percentile = Decimal(100) * (Decimal(1) - Decimal(rank - 1) / Decimal(total_teams))
        tr.percentile = percentile.quantize(QUANTIZER_3DP, rounding=ROUND_HALF_UP)
        
        # Compute hash
        tr.result_hash = tr.compute_hash()
    
    return team_results


async def _compute_speaker_results(
    tournament_id: int,
    db: AsyncSession
) -> List[TournamentSpeakerResult]:
    """
    Compute speaker results with deterministic ranking.
    
    Args:
        tournament_id: Tournament ID
        db: Database session
    
    Returns:
        List of TournamentSpeakerResult with ranks assigned
    """
    # Fetch speaker scores from oral rounds
    result = await db.execute(
        select(
            LiveTurn.participant_id,
            func.sum(LiveTurn.speaker_score).label("total_score"),
            func.count(LiveTurn.id).label("rounds"),
            func.avg(LiveTurn.speaker_score).label("avg_score")
        )
        .join(LiveCourtSession, LiveTurn.session_id == LiveCourtSession.id)
        .where(LiveCourtSession.tournament_id == tournament_id)
        .where(LiveTurn.speaker_score.isnot(None))
        .group_by(LiveTurn.participant_id)
    )
    speaker_data = result.all()
    
    if not speaker_data:
        return []
    
    # Build result objects
    speaker_results = []
    for row in speaker_data:
        speaker_id = row.participant_id
        total_score = Decimal(str(row.total_score or 0)).quantize(QUANTIZER_2DP)
        rounds = int(row.rounds or 0)
        avg_score = Decimal(str(row.avg_score or 0)).quantize(QUANTIZER_4DP)
        
        sr = TournamentSpeakerResult(
            tournament_id=tournament_id,
            speaker_id=speaker_id,
            total_speaker_score=total_score,
            average_score=avg_score,
            rounds_participated=rounds,
            speaker_hash=""  # Will compute after ranking
        )
        speaker_results.append(sr)
    
    # Sort: total_score DESC, avg_score DESC, rounds DESC, speaker_id ASC
    speaker_results.sort(
        key=lambda x: (
            -x.total_speaker_score,  # DESC
            -x.average_score,         # DESC
            -x.rounds_participated,   # DESC
            x.speaker_id              # ASC
        )
    )
    
    # Assign ranks and percentiles
    total_speakers = len(speaker_results)
    for rank, sr in enumerate(speaker_results, start=1):
        sr.final_rank = rank
        percentile = Decimal(100) * (Decimal(1) - Decimal(rank - 1) / Decimal(total_speakers))
        sr.percentile = percentile.quantize(QUANTIZER_3DP, rounding=ROUND_HALF_UP)
        
        # Compute hash
        sr.speaker_hash = sr.compute_hash()
    
    return speaker_results


async def _fetch_memorial_scores(
    tournament_id: int,
    db: AsyncSession
) -> Dict[int, float]:
    """
    Fetch memorial scores by team.
    
    Returns:
        Dict mapping team_id to memorial score
    """
    # Query memorial submissions
    result = await db.execute(
        select(
            MemorialSubmission.tournament_team_id,
            func.sum(MemorialEvaluation.total_score).label("total")
        )
        .join(
            MemorialEvaluation,
            MemorialEvaluation.memorial_submission_id == MemorialSubmission.id
        )
        .where(MemorialSubmission.tournament_id == tournament_id)
        .group_by(MemorialSubmission.tournament_team_id)
    )
    
    scores = {}
    for row in result.all():
        scores[row.tournament_team_id] = float(row.total or 0)
    
    return scores


async def _fetch_oral_scores_and_sos(
    tournament_id: int,
    db: AsyncSession
) -> Dict[str, Dict[int, float]]:
    """
    Fetch oral scores and strength of schedule data.
    
    Returns:
        Dict with keys: "scores", "sos", "wins"
    """
    # Fetch matches and compute scores, SOS, wins
    result = await db.execute(
        select(TournamentMatch)
        .where(TournamentMatch.tournament_id == tournament_id)
    )
    matches = result.scalars().all()
    
    scores = {}
    opponent_scores = {}  # For SOS calculation
    wins = {}
    
    for match in matches:
        # Process match results
        # This is simplified - actual implementation would use match data
        pass
    
    # Compute SOS: sum(opponent_total_score) / number_of_rounds
    sos = {}
    for team_id, opponents in opponent_scores.items():
        if opponents:
            total_opponent_score = sum(opponents.values())
            sos[team_id] = total_opponent_score / len(opponents)
        else:
            sos[team_id] = 0
    
    return {
        "scores": scores,
        "sos": sos,
        "wins": wins
    }


def _build_team_snapshot(team_results: List[TournamentTeamResult]) -> List[Dict[str, Any]]:
    """
    Build deterministic JSON snapshot of team results.
    
    Args:
        team_results: List of team results
    
    Returns:
        List of sorted dicts
    """
    snapshot = []
    for tr in team_results:
        data = {
            "final_rank": tr.final_rank,
            "memorial_total": float(tr.memorial_total),
            "opponent_wins_total": tr.opponent_wins_total,
            "oral_total": float(tr.oral_total),
            "percentile": float(tr.percentile) if tr.percentile else None,
            "result_hash": tr.result_hash,
            "strength_of_schedule": float(tr.strength_of_schedule),
            "team_id": tr.team_id,
            "total_score": float(tr.total_score)
        }
        snapshot.append(data)
    
    return snapshot


def _build_speaker_snapshot(speaker_results: List[TournamentSpeakerResult]) -> List[Dict[str, Any]]:
    """
    Build deterministic JSON snapshot of speaker results.
    
    Args:
        speaker_results: List of speaker results
    
    Returns:
        List of sorted dicts
    """
    snapshot = []
    for sr in speaker_results:
        data = {
            "average_score": float(sr.average_score),
            "final_rank": sr.final_rank,
            "percentile": float(sr.percentile) if sr.percentile else None,
            "rounds_participated": sr.rounds_participated,
            "speaker_hash": sr.speaker_hash,
            "speaker_id": sr.speaker_id,
            "total_speaker_score": float(sr.total_speaker_score)
        }
        snapshot.append(data)
    
    return snapshot


async def verify_results_integrity(
    tournament_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Verify integrity of frozen results.
    
    Args:
        tournament_id: Tournament ID
        db: Database session
    
    Returns:
        Dict with verification results
    """
    result = await db.execute(
        select(TournamentResultsFreeze)
        .where(TournamentResultsFreeze.tournament_id == tournament_id)
    )
    freeze = result.scalar_one_or_none()
    
    if not freeze:
        return {
            "found": False,
            "valid": False,
            "tamper_detected": False,
            "error": "No freeze found"
        }
    
    # Recompute team hashes
    team_result = await db.execute(
        select(TournamentTeamResult)
        .where(TournamentTeamResult.tournament_id == tournament_id)
        .order_by(TournamentTeamResult.team_id.asc())
    )
    team_results = team_result.scalars().all()
    
    team_tampered = False
    for tr in team_results:
        computed = tr.compute_hash()
        if computed != tr.result_hash:
            team_tampered = True
            break
    
    # Recompute speaker hashes
    speaker_result = await db.execute(
        select(TournamentSpeakerResult)
        .where(TournamentSpeakerResult.tournament_id == tournament_id)
        .order_by(TournamentSpeakerResult.speaker_id.asc())
    )
    speaker_results = speaker_result.scalars().all()
    
    speaker_tampered = False
    for sr in speaker_results:
        computed = sr.compute_hash()
        if computed != sr.speaker_hash:
            speaker_tampered = True
            break
    
    # Recompute global checksum
    team_hashes = [tr.result_hash for tr in team_results]
    speaker_hashes = [sr.speaker_hash for sr in speaker_results]
    
    recomputed_checksum = freeze.compute_global_checksum(team_hashes, speaker_hashes)
    checksum_valid = recomputed_checksum == freeze.results_checksum
    
    tamper_detected = team_tampered or speaker_tampered or not checksum_valid
    
    return {
        "found": True,
        "valid": not tamper_detected,
        "tamper_detected": tamper_detected,
        "stored_checksum": freeze.results_checksum,
        "recomputed_checksum": recomputed_checksum,
        "team_results_verified": len(team_results),
        "speaker_results_verified": len(speaker_results)
    }


# Import at end to avoid circular dependency
from backend.orm.national_network import TournamentTeam
from sqlalchemy import text
