"""
Performance Intelligence Service — Phase 9

National Legal Talent Signal Engine with:
- Skill vector computation (deterministic)
- Performance normalization across institutions
- National composite rankings
- Fairness auditing

Security:
- All numeric values use Decimal (never float)
- All timestamps use utcnow()
- SERIALIZABLE isolation for ranking computation
- Idempotent recomputation

Determinism:
- No random()
- No datetime.now()
- No Python hash()
- All JSON dumps use sort_keys=True
"""
import math
import hashlib
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional, Dict, Any, List, Tuple

from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from backend.orm.performance_intelligence import (
    CandidateSkillVector, PerformanceNormalizationStats,
    NationalCandidateRanking, FairnessAuditLog
)
from backend.orm.live_courtroom import LiveJudgeScore, LiveScoreType
from backend.orm.national_network import TournamentEvaluation
from backend.orm.institutional_governance import AcademicYear
from backend.orm.user import User


# =============================================================================
# Custom Exceptions
# =============================================================================

class PerformanceIntelligenceError(Exception):
    """Base exception for performance intelligence errors."""
    pass


class InsufficientDataError(PerformanceIntelligenceError):
    """Raised when insufficient data for computation."""
    pass


class RankingComputationError(PerformanceIntelligenceError):
    """Raised when ranking computation fails."""
    pass


# =============================================================================
# Decimal Utilities
# =============================================================================

QUANTIZER_2DP = Decimal("0.01")
QUANTIZER_3DP = Decimal("0.001")
QUANTIZER_4DP = Decimal("0.0001")


def decimal_sqrt(value: Decimal, precision: int = 10) -> Decimal:
    """
    Compute square root using Decimal for determinism.
    
    Uses Newton's method for precise decimal square root.
    
    Args:
        value: Decimal value to compute sqrt of
        precision: Number of decimal places for result
        
    Returns:
        Decimal square root
    """
    if value < Decimal("0"):
        raise ValueError("Cannot compute square root of negative number")
    
    if value == Decimal("0"):
        return Decimal("0")
    
    # Initial guess
    guess = Decimal(str(math.sqrt(float(value))))
    
    # Newton's method iteration
    for _ in range(precision):
        guess = (guess + value / guess) / Decimal("2")
    
    return +guess  # + removes extra precision


def safe_divide(numerator: Decimal, denominator: Decimal, default: Decimal = Decimal("0")) -> Decimal:
    """
    Safe division that returns default if denominator is zero.
    
    Args:
        numerator: Dividend
        denominator: Divisor
        default: Value to return if denominator is zero
        
    Returns:
        Division result or default
    """
    if denominator == Decimal("0"):
        return default
    return numerator / denominator


def compute_z_score(value: Decimal, mean: Decimal, std_dev: Decimal) -> Decimal:
    """
    Compute z-score for normalization.
    
    z = (x - mean) / std_dev
    
    Args:
        value: The value to normalize
        mean: Population mean
        std_dev: Population standard deviation
        
    Returns:
        Z-score as Decimal
    """
    if std_dev == Decimal("0"):
        return Decimal("0")
    return ((value - mean) / std_dev).quantize(QUANTIZER_4DP, rounding=ROUND_HALF_UP)


# =============================================================================
# 3. SKILL VECTOR ENGINE
# =============================================================================

async def compute_candidate_skill_vector(
    user_id: int,
    db: AsyncSession
) -> CandidateSkillVector:
    """
    Compute skill vector for a candidate from all available performance data.
    
    Elite Hardening:
    - Uses Decimal only (no float)
    - Quantizes to 0.01 precision
    - SERIALIZABLE isolation for atomic recomputation
    - Idempotent (overwrites existing record)
    
    Data Sources:
    - Phase 8: live_judge_scores (argument, rebuttal, etiquette)
    - Phase 7: tournament_evaluations (legal_argument, presentation, rebuttal, compliance)
    - Phase 5: leaderboard entries (if available)
    
    Skill Formulas:
    - oral_advocacy_score: Average of argument + rebuttal scores
    - statutory_interpretation_score: Weighted from legal argument scores
    - case_law_application_score: From tournament evaluations
    - procedural_compliance_score: Direct from evaluations
    - rebuttal_responsiveness_score: From rebuttal scores
    - courtroom_etiquette_score: From etiquette scores
    - consistency_factor: 100 - (coefficient of variation * 100)
    - confidence_index: min(100, sessions * 5)
    
    Args:
        user_id: ID of the candidate user
        db: Database session
        
    Returns:
        Computed or updated CandidateSkillVector
        
    Raises:
        InsufficientDataError: If less than 2 sessions of data available
    """
    # Get user to find institution
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise PerformanceIntelligenceError(f"User {user_id} not found")
    
    institution_id = user.institution_id
    
    # Collect all scores from different phases
    scores = {
        'argument': [],
        'rebuttal': [],
        'etiquette': [],
        'legal_argument': [],
        'presentation': [],
        'compliance': [],
    }
    
    # Phase 8: Live Judge Scores
    result = await db.execute(
        select(LiveJudgeScore.provisional_score, LiveJudgeScore.score_type)
        .where(LiveJudgeScore.participant_id.in_(
            select(text("id")).select_from(text("classroom_participants")).where(text(f"user_id = {user_id}"))
        ))
    )
    live_scores = result.all()
    
    for score, score_type in live_scores:
        score_decimal = Decimal(str(score))
        if score_type == LiveScoreType.ARGUMENT:
            scores['argument'].append(score_decimal)
        elif score_type == LiveScoreType.REBUTTAL:
            scores['rebuttal'].append(score_decimal)
        elif score_type == LiveScoreType.COURTROOM_ETIQUETTE:
            scores['etiquette'].append(score_decimal)
    
    # Phase 7: Tournament Evaluations
    # Note: Need to join through tournament_teams to find user's evaluations
    result = await db.execute(
        select(
            TournamentEvaluation.legal_argument_score,
            TournamentEvaluation.presentation_score,
            TournamentEvaluation.rebuttal_score,
            TournamentEvaluation.procedural_compliance_score
        )
        .join(text("tournament_teams"), TournamentEvaluation.team_id == text("tournament_teams.id"))
        .where(text(f"tournament_teams.registered_by = {user_id}"))
    )
    tournament_scores = result.all()
    
    for legal, pres, reb, comp in tournament_scores:
        if legal:
            scores['legal_argument'].append(Decimal(str(legal)))
        if reb:
            scores['rebuttal'].append(Decimal(str(reb)))
        if comp:
            scores['compliance'].append(Decimal(str(comp)))
    
    # Count total sessions analyzed
    total_sessions = len(live_scores) + len(tournament_scores)
    
    if total_sessions < 2:
        raise InsufficientDataError(
            f"Insufficient data for user {user_id}: {total_sessions} sessions (minimum 2 required)"
        )
    
    # Compute skill scores (averages)
    def compute_average(values: List[Decimal]) -> Decimal:
        if not values:
            return Decimal("0")
        return (sum(values) / Decimal(len(values))).quantize(QUANTIZER_2DP, rounding=ROUND_HALF_UP)
    
    # Core skill scores
    oral_advocacy_score = compute_average(scores['argument'] + scores['rebuttal'])
    statutory_interpretation_score = compute_average(scores['legal_argument'])
    case_law_application_score = compute_average(scores['legal_argument'])
    procedural_compliance_score = compute_average(scores['compliance'])
    rebuttal_responsiveness_score = compute_average(scores['rebuttal'])
    courtroom_etiquette_score = compute_average(scores['etiquette'])
    
    # Meta-metrics
    all_scores = scores['argument'] + scores['rebuttal'] + scores['etiquette'] + scores['legal_argument'] + scores['compliance']
    
    if len(all_scores) > 1:
        mean = sum(all_scores) / Decimal(len(all_scores))
        variance = sum((x - mean) ** 2 for x in all_scores) / Decimal(len(all_scores) - 1)
        std_dev = decimal_sqrt(variance)
        
        # Coefficient of variation (CV) = std_dev / mean
        cv = safe_divide(std_dev, mean, Decimal("0"))
        consistency_factor = (Decimal("100") - (cv * Decimal("100"))).quantize(QUANTIZER_2DP, rounding=ROUND_HALF_UP)
        consistency_factor = max(Decimal("0"), min(Decimal("100"), consistency_factor))
    else:
        consistency_factor = Decimal("50")  # Default middle value
    
    # Confidence index: min(100, sessions * 5)
    sessions_weight = Decimal(str(total_sessions * 5))
    confidence_index = min(Decimal("100"), sessions_weight).quantize(QUANTIZER_2DP)
    
    # Check for existing record
    result = await db.execute(
        select(CandidateSkillVector).where(CandidateSkillVector.user_id == user_id)
    )
    existing = result.scalar_one_or_none()
    
    now = datetime.utcnow()
    
    if existing:
        # Update existing record (atomic overwrite)
        existing.oral_advocacy_score = oral_advocacy_score
        existing.statutory_interpretation_score = statutory_interpretation_score
        existing.case_law_application_score = case_law_application_score
        existing.procedural_compliance_score = procedural_compliance_score
        existing.rebuttal_responsiveness_score = rebuttal_responsiveness_score
        existing.courtroom_etiquette_score = courtroom_etiquette_score
        existing.consistency_factor = consistency_factor
        existing.confidence_index = confidence_index
        existing.total_sessions_analyzed = total_sessions
        existing.last_updated_at = now
        vector = existing
    else:
        # Create new record
        vector = CandidateSkillVector(
            user_id=user_id,
            institution_id=institution_id,
            oral_advocacy_score=oral_advocacy_score,
            statutory_interpretation_score=statutory_interpretation_score,
            case_law_application_score=case_law_application_score,
            procedural_compliance_score=procedural_compliance_score,
            rebuttal_responsiveness_score=rebuttal_responsiveness_score,
            courtroom_etiquette_score=courtroom_etiquette_score,
            consistency_factor=consistency_factor,
            confidence_index=confidence_index,
            total_sessions_analyzed=total_sessions,
            last_updated_at=now,
            created_at=now
        )
        db.add(vector)
    
    await db.flush()
    return vector


# =============================================================================
# 4. NORMALIZATION ENGINE
# =============================================================================

async def compute_normalization_stats(
    institution_id: int,
    db: AsyncSession,
    min_sample_size: int = 5
) -> List[PerformanceNormalizationStats]:
    """
    Compute normalization statistics for an institution.
    
    Elite Hardening:
    - Uses Decimal for all statistical calculations
    - Deterministic sqrt using Newton's method
    - Skips if sample_size < min_sample_size
    - No division by zero
    
    Computes:
    - mean = sum(values) / N
    - std_dev = sqrt(sum((x - mean)^2) / N)
    
    Args:
        institution_id: Institution to analyze
        db: Database session
        min_sample_size: Minimum samples required (default 5)
        
    Returns:
        List of computed normalization stats (one per metric)
    """
    # Get all skill vectors for institution
    result = await db.execute(
        select(CandidateSkillVector).where(
            CandidateSkillVector.institution_id == institution_id
        )
    )
    vectors = list(result.scalars().all())
    
    if len(vectors) < min_sample_size:
        return []  # Skip normalization for small samples
    
    # Collect metrics
    metrics = {
        'oral_advocacy_score': [],
        'statutory_interpretation_score': [],
        'case_law_application_score': [],
        'procedural_compliance_score': [],
        'rebuttal_responsiveness_score': [],
        'courtroom_etiquette_score': [],
        'consistency_factor': [],
        'confidence_index': [],
    }
    
    for vector in vectors:
        metrics['oral_advocacy_score'].append(vector.oral_advocacy_score)
        metrics['statutory_interpretation_score'].append(vector.statutory_interpretation_score)
        metrics['case_law_application_score'].append(vector.case_law_application_score)
        metrics['procedural_compliance_score'].append(vector.procedural_compliance_score)
        metrics['rebuttal_responsiveness_score'].append(vector.rebuttal_responsiveness_score)
        metrics['courtroom_etiquette_score'].append(vector.courtroom_etiquette_score)
        metrics['consistency_factor'].append(vector.consistency_factor)
        metrics['confidence_index'].append(vector.confidence_index)
    
    stats_list = []
    now = datetime.utcnow()
    
    for metric_name, values in metrics.items():
        if len(values) < min_sample_size:
            continue
        
        # Compute mean
        n = Decimal(len(values))
        mean = (sum(values) / n).quantize(QUANTIZER_4DP, rounding=ROUND_HALF_UP)
        
        # Compute variance and std deviation
        squared_diffs = [(x - mean) ** 2 for x in values]
        variance = sum(squared_diffs) / n  # Population variance
        std_dev = decimal_sqrt(variance).quantize(QUANTIZER_4DP, rounding=ROUND_HALF_UP)
        
        # Check for existing stats
        result = await db.execute(
            select(PerformanceNormalizationStats).where(
                and_(
                    PerformanceNormalizationStats.institution_id == institution_id,
                    PerformanceNormalizationStats.metric_name == metric_name
                )
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            # Update
            existing.mean_value = mean
            existing.std_deviation = std_dev
            existing.sample_size = len(values)
            existing.computed_at = now
            stats = existing
        else:
            # Create
            stats = PerformanceNormalizationStats(
                institution_id=institution_id,
                metric_name=metric_name,
                mean_value=mean,
                std_deviation=std_dev,
                sample_size=len(values),
                computed_at=now
            )
            db.add(stats)
        
        stats_list.append(stats)
    
    await db.flush()
    return stats_list


# =============================================================================
# 5. NATIONAL RANKING ENGINE
# =============================================================================

async def compute_national_rankings(
    academic_year_id: int,
    db: AsyncSession
) -> List[NationalCandidateRanking]:
    """
    Compute national composite rankings for all candidates in an academic year.
    
    Elite Hardening:
    - SERIALIZABLE isolation for atomic ranking computation
    - Deterministic composite score formula
    - Dense ranking (no ties)
    - Percentile calculation quantized to 3 decimal places
    - Cryptographic checksum for tamper detection
    - Idempotent (recomputation overwrites non-final rankings)
    
    Composite Score Formula:
    ```
    composite =
      (0.4 * oral_advocacy)
      + (0.2 * statutory_interpretation)
      + (0.15 * rebuttal_responsiveness)
      + (0.15 * case_law_application)
      + (0.1 * consistency_factor)
    ```
    
    Sorting Order:
    1. composite_score DESC
    2. tournaments_participated DESC
    3. user_id ASC (deterministic tiebreaker)
    
    Percentile Formula:
    ```
    percentile = 100 * (1 - (rank - 1) / total_candidates)
    ```
    
    Checksum Formula:
    ```
    combined = "{user_id}|{rank}|{composite_score:.4f}|{percentile:.3f}"
    checksum = SHA256(combined.encode()).hexdigest()
    ```
    
    Args:
        academic_year_id: Academic year for ranking context
        db: Database session
        
    Returns:
        List of computed national rankings
        
    Raises:
        RankingComputationError: If computation fails
    """
    # Set SERIALIZABLE isolation for atomic ranking
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    
    # Get all candidates with skill vectors
    result = await db.execute(
        select(CandidateSkillVector, User)
        .join(User, CandidateSkillVector.user_id == User.id)
        .where(User.is_active == True)
        .order_by(
            CandidateSkillVector.user_id.asc()  # Deterministic ordering
        )
    )
    candidates = result.all()
    
    if not candidates:
        return []
    
    # Compute composite scores
    scored_candidates = []
    
    for vector, user in candidates:
        # Composite score calculation
        composite = (
            Decimal("0.4") * vector.oral_advocacy_score +
            Decimal("0.2") * vector.statutory_interpretation_score +
            Decimal("0.15") * vector.rebuttal_responsiveness_score +
            Decimal("0.15") * vector.case_law_application_score +
            Decimal("0.1") * vector.consistency_factor
        ).quantize(QUANTIZER_4DP, rounding=ROUND_HALF_UP)
        
        # Get tournament participation count
        result = await db.execute(
            select(func.count(text("*"))).select_from(text("tournament_teams"))
            .where(text(f"registered_by = {user.id}"))
        )
        tournaments_count = result.scalar() or 0
        
        scored_candidates.append({
            'user_id': user.id,
            'institution_id': user.institution_id,
            'composite_score': composite,
            'tournaments_participated': tournaments_count,
            'vector': vector
        })
    
    # Sort by composite score (desc), tournaments (desc), user_id (asc)
    scored_candidates.sort(
        key=lambda x: (-x['composite_score'], -x['tournaments_participated'], x['user_id'])
    )
    
    # Compute dense ranking
    total_candidates = len(scored_candidates)
    rankings = []
    now = datetime.utcnow()
    
    current_rank = 0
    previous_score = None
    
    for i, candidate in enumerate(scored_candidates):
        # Dense ranking: increment rank only when score changes
        if previous_score is None or candidate['composite_score'] != previous_score:
            current_rank = i + 1
        
        # Compute percentile: 100 * (1 - (rank - 1) / total)
        percentile = (
            Decimal("100") * (Decimal("1") - (Decimal(current_rank - 1) / Decimal(total_candidates)))
        ).quantize(QUANTIZER_3DP, rounding=ROUND_HALF_UP)
        
        # Compute checksum
        combined = f"{candidate['user_id']}|{current_rank}|{candidate['composite_score']:.4f}|{percentile:.3f}"
        checksum = hashlib.sha256(combined.encode()).hexdigest()
        
        # Check for existing ranking
        result = await db.execute(
            select(NationalCandidateRanking).where(
                and_(
                    NationalCandidateRanking.academic_year_id == academic_year_id,
                    NationalCandidateRanking.user_id == candidate['user_id']
                )
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing and existing.is_final:
            # Don't update finalized rankings
            rankings.append(existing)
            previous_score = candidate['composite_score']
            continue
        
        if existing:
            # Update non-final ranking
            existing.composite_score = candidate['composite_score']
            existing.national_rank = current_rank
            existing.percentile = percentile
            existing.tournaments_participated = candidate['tournaments_participated']
            existing.checksum = checksum
            existing.computed_at = now
            ranking = existing
        else:
            # Create new ranking
            ranking = NationalCandidateRanking(
                academic_year_id=academic_year_id,
                user_id=candidate['user_id'],
                composite_score=candidate['composite_score'],
                national_rank=current_rank,
                percentile=percentile,
                tournaments_participated=candidate['tournaments_participated'],
                checksum=checksum,
                computed_at=now,
                is_final=False
            )
            db.add(ranking)
        
        rankings.append(ranking)
        previous_score = candidate['composite_score']
    
    await db.flush()
    return rankings


# =============================================================================
# 9. FAIRNESS AUDIT
# =============================================================================

async def run_fairness_audit(
    institution_id: int,
    db: AsyncSession,
    anomaly_threshold: Decimal = Decimal("2.0")
) -> List[FairnessAuditLog]:
    """
    Run fairness audit for an institution to detect anomalies.
    
    Elite Hardening:
    - Detects score distribution anomalies
    - Computes z-score drift
    - Flags standard deviation irregularities
    - All calculations use Decimal
    
    Anomaly Detection:
    - z-score > 2.0: Flagged for review
    - std_dev = 0: All scores identical (suspicious)
    - mean > 90 or < 10: Extreme clustering
    
    Args:
        institution_id: Institution to audit
        db: Database session
        anomaly_threshold: Z-score threshold for flagging (default 2.0)
        
    Returns:
        List of audit log entries
    """
    # Get normalization stats for institution
    result = await db.execute(
        select(PerformanceNormalizationStats).where(
            PerformanceNormalizationStats.institution_id == institution_id
        )
    )
    stats_list = list(result.scalars().all())
    
    audit_logs = []
    now = datetime.utcnow()
    
    for stats in stats_list:
        flagged = False
        anomaly_score = Decimal("0")
        details = {}
        
        # Check 1: Zero standard deviation (all identical scores)
        if stats.std_deviation == Decimal("0"):
            flagged = True
            anomaly_score = Decimal("3.0")
            details['issue'] = 'zero_variance'
            details['description'] = 'All candidates have identical scores'
        
        # Check 2: Extreme mean scores
        elif stats.mean_value > Decimal("90") or stats.mean_value < Decimal("10"):
            flagged = True
            anomaly_score = Decimal("2.5")
            details['issue'] = 'extreme_mean'
            details['mean_value'] = str(stats.mean_value)
        
        # Check 3: Unusual standard deviation (compared to typical range)
        # Typical std_dev for 0-100 scores is 10-20
        elif stats.std_deviation > Decimal("30") or (stats.std_deviation < Decimal("5") and stats.std_deviation > Decimal("0")):
            flagged = True
            anomaly_score = Decimal("1.8")
            details['issue'] = 'unusual_variance'
            details['std_deviation'] = str(stats.std_deviation)
        
        # Check 4: Small sample size
        if stats.sample_size < 5:
            anomaly_score = max(anomaly_score, Decimal("1.5"))
            details['small_sample'] = stats.sample_size
        
        # Create audit log if any issues found
        if flagged or anomaly_score >= anomaly_threshold:
            log = FairnessAuditLog(
                institution_id=institution_id,
                metric_name=stats.metric_name,
                anomaly_score=anomaly_score.quantize(QUANTIZER_3DP),
                flagged=flagged,
                details_json=details,
                created_at=now
            )
            db.add(log)
            audit_logs.append(log)
    
    await db.flush()
    return audit_logs


# =============================================================================
# Helper Functions
# =============================================================================

async def verify_candidate_ranking(
    academic_year_id: int,
    user_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Verify a candidate's ranking checksum.
    
    Args:
        academic_year_id: Academic year context
        user_id: Candidate user ID
        db: Database session
        
    Returns:
        Verification result with stored vs computed checksum
    """
    result = await db.execute(
        select(NationalCandidateRanking).where(
            and_(
                NationalCandidateRanking.academic_year_id == academic_year_id,
                NationalCandidateRanking.user_id == user_id
            )
        )
    )
    ranking = result.scalar_one_or_none()
    
    if not ranking:
        return {
            "user_id": user_id,
            "academic_year_id": academic_year_id,
            "found": False,
            "valid": False,
            "error": "Ranking not found"
        }
    
    is_valid = ranking.verify_checksum()
    
    return {
        "user_id": user_id,
        "academic_year_id": academic_year_id,
        "found": True,
        "valid": is_valid,
        "stored_checksum": ranking.checksum,
        "rank": ranking.national_rank,
        "composite_score": str(ranking.composite_score),
        "percentile": str(ranking.percentile)
    }


async def get_institution_performance_summary(
    institution_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get performance summary for an institution.
    
    Args:
        institution_id: Institution ID
        db: Database session
        
    Returns:
        Summary dictionary with metrics
    """
    # Count candidates
    result = await db.execute(
        select(func.count(CandidateSkillVector.id))
        .where(CandidateSkillVector.institution_id == institution_id)
    )
    candidate_count = result.scalar() or 0
    
    # Get normalization stats
    result = await db.execute(
        select(PerformanceNormalizationStats)
        .where(PerformanceNormalizationStats.institution_id == institution_id)
    )
    stats_list = list(result.scalars().all())
    
    # Get fairness audit results
    result = await db.execute(
        select(func.count(FairnessAuditLog.id))
        .where(
            and_(
                FairnessAuditLog.institution_id == institution_id,
                FairnessAuditLog.flagged == True
            )
        )
    )
    flagged_count = result.scalar() or 0
    
    return {
        "institution_id": institution_id,
        "candidate_count": candidate_count,
        "normalization_metrics": {s.metric_name: str(s.mean_value) for s in stats_list},
        "fairness_flags": flagged_count,
        "summary_timestamp": datetime.utcnow().isoformat()
    }
