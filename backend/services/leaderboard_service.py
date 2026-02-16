"""
Leaderboard Service — Phase 5 (Immutable Leaderboard Engine)

Production-grade service for freezing and retrieving session leaderboards.

Immutability guarantees:
- Leaderboards are NEVER updated after freeze
- All scores computed server-side from evaluations
- Deterministic tie-breaking rules
- Checksum verification for integrity
"""
import hashlib
import json
import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.session_leaderboard import (
    SessionLeaderboardSnapshot, SessionLeaderboardEntry, SessionLeaderboardAudit, LeaderboardSide
)
from backend.orm.ai_evaluations import AIEvaluation, EvaluationStatus
from backend.orm.classroom_session import ClassroomSession, ClassroomParticipant
from backend.orm.classroom_round import ClassroomRound
from backend.orm.user import User, UserRole
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class LeaderboardError(Exception):
    """Base leaderboard error."""
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(message)


class SessionNotCompleteError(LeaderboardError):
    """Session not in COMPLETED state."""
    def __init__(self, session_id: int):
        super().__init__(
            f"Session {session_id} is not completed",
            "SESSION_NOT_COMPLETE"
        )


class MissingEvaluationsError(LeaderboardError):
    """Some participants missing completed evaluations."""
    def __init__(self, participants: List[int]):
        super().__init__(
            f"Participants without completed evaluations: {participants}",
            "MISSING_EVALUATIONS"
        )


class IncompleteEvaluationError(LeaderboardError):
    """Some evaluations are not in COMPLETED state."""
    def __init__(self, evaluations: List[int], status: str):
        super().__init__(
            f"Evaluations with status {status}: {evaluations}",
            "INCOMPLETE_EVALUATIONS"
        )


class RequiresReviewError(LeaderboardError):
    """Some evaluations require manual review."""
    def __init__(self, evaluations: List[int]):
        super().__init__(
            f"Evaluations requiring review: {evaluations}",
            "REQUIRES_REVIEW"
        )


class AlreadyFrozenError(LeaderboardError):
    """Leaderboard already frozen for this session."""
    def __init__(self, session_id: int, existing_snapshot_id: Optional[int] = None):
        self.existing_snapshot_id = existing_snapshot_id
        super().__init__(
            f"Leaderboard already frozen for session {session_id}",
            "ALREADY_FROZEN"
        )


class UnauthorizedFreezeError(LeaderboardError):
    """User not authorized to freeze leaderboard."""
    def __init__(self):
        super().__init__(
            "Only faculty can freeze leaderboards",
            "UNAUTHORIZED"
        )


class SnapshotNotFoundError(LeaderboardError):
    """No frozen leaderboard found for session."""
    def __init__(self, session_id: int):
        super().__init__(
            f"No frozen leaderboard found for session {session_id}",
            "SNAPSHOT_NOT_FOUND"
        )


# =============================================================================
# Core Service Functions
# =============================================================================

async def freeze_leaderboard(
    session_id: int,
    faculty_id: int,
    db: AsyncSession
) -> Tuple[SessionLeaderboardSnapshot, bool]:
    """
    Freeze immutable leaderboard for a completed session.
    
    VALIDATION (all must pass):
    1. Session exists and status == COMPLETED
    2. All participants have AIEvaluation.status == COMPLETED
    3. NO evaluation is PROCESSING
    4. NO evaluation is REQUIRES_REVIEW
    5. NO evaluation is PENDING or FAILED
    6. Snapshot for this session does NOT already exist (idempotent)
    
    RANKING ALGORITHM:
    1. Sort by total_score DESC
    2. Tie-breaker 1: highest_single_round_score DESC
    3. Tie-breaker 2: earliest_submission_timestamp ASC
    4. Tie-breaker 3: participant_id ASC (deterministic)
    5. Assign DENSE rank (no gaps)
    
    CONCURRENCY SAFETY:
    - All operations inside single transaction
    - DB-level unique constraint on session_id prevents duplicate snapshots
    - IntegrityError caught and handled gracefully
    
    IDEMPOTENT BEHAVIOR:
    - If leaderboard already frozen, returns existing snapshot with already_frozen=True
    - No error raised for duplicate freeze requests
    
    Args:
        session_id: Classroom session ID
        faculty_id: Faculty user ID requesting freeze
        db: Database session
        
    Returns:
        Tuple of (snapshot, already_frozen)
        - snapshot: The frozen leaderboard snapshot
        - already_frozen: True if returned existing, False if newly created
        
    Raises:
        UnauthorizedFreezeError: If user is not faculty
        SessionNotCompleteError: If session not completed
        MissingEvaluationsError: If any participant missing evaluation
        IncompleteEvaluationError: If any evaluation not COMPLETED
        RequiresReviewError: If any evaluation requires review
    """
    # Verify faculty authorization (outside transaction for early exit)
    faculty_result = await db.execute(
        select(User).where(User.id == faculty_id)
    )
    faculty = faculty_result.scalar_one_or_none()
    if not faculty or faculty.role not in (UserRole.FACULTY, UserRole.ADMIN):
        raise UnauthorizedFreezeError()
    
    # Begin transaction for all subsequent operations
    # PostgreSQL production: Use SERIALIZABLE for strictest consistency
    # SET TRANSACTION ISOLATION LEVEL SERIALIZABLE
    try:
        async with db.begin():
            # PostgreSQL: Enforce SERIALIZABLE isolation for strictest consistency
            if db.bind and hasattr(db.bind, 'dialect') and db.bind.dialect.name == "postgresql":
                from sqlalchemy import text
                await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            
            # Verify session exists and is completed
            session_result = await db.execute(
                select(ClassroomSession).where(ClassroomSession.id == session_id)
            )
            session = session_result.scalar_one_or_none()
            if not session:
                raise LeaderboardError(f"Session {session_id} not found", "SESSION_NOT_FOUND")
            
            # STRICT: Session must be COMPLETED
            session_status = getattr(session, 'status', None)
            if session_status != "COMPLETED":
                raise SessionNotCompleteError(session_id)
            
            # Get all participants
            participants_result = await db.execute(
                select(ClassroomParticipant).where(
                    ClassroomParticipant.session_id == session_id
                )
            )
            participants = participants_result.scalars().all()
            
            if not participants:
                raise LeaderboardError("No participants in session", "NO_PARTICIPANTS")
            
            # STRICT: Verify ALL evaluations are COMPLETED (not processing, not requiring review)
            participant_ids = [p.id for p in participants]
            
            # Query all evaluations for all participants
            all_evals_result = await db.execute(
                select(AIEvaluation).where(
                    AIEvaluation.participant_id.in_(participant_ids)
                )
            )
            all_evaluations = all_evals_result.scalars().all()
            
            # Build lookup map
            eval_map = {e.participant_id: e for e in all_evaluations}
            
            # Track issues
            missing_evals = []
            processing_evals = []
            requires_review_evals = []
            failed_evals = []
            pending_evals = []
            
            participant_scores = []
            
            for participant in participants:
                evaluation = eval_map.get(participant.id)
                
                if not evaluation:
                    missing_evals.append(participant.id)
                elif evaluation.status == EvaluationStatus.PROCESSING:
                    processing_evals.append(evaluation.id)
                elif evaluation.status == EvaluationStatus.REQUIRES_REVIEW:
                    requires_review_evals.append(evaluation.id)
                elif evaluation.status == EvaluationStatus.FAILED:
                    failed_evals.append(evaluation.id)
                elif evaluation.status == EvaluationStatus.PENDING:
                    pending_evals.append(evaluation.id)
                elif evaluation.status != EvaluationStatus.COMPLETED:
                    # Catch-all for any other non-completed status
                    failed_evals.append(evaluation.id)
                else:
                    # COMPLETED - collect score data
                    score_data = await _get_participant_score_data(participant, evaluation)
                    participant_scores.append(score_data)
            
            # Raise specific errors for any issues found
            if processing_evals:
                raise IncompleteEvaluationError(processing_evals, "PROCESSING")
            if requires_review_evals:
                raise RequiresReviewError(requires_review_evals)
            if failed_evals:
                raise IncompleteEvaluationError(failed_evals, "FAILED")
            if pending_evals:
                raise IncompleteEvaluationError(pending_evals, "PENDING")
            if missing_evals:
                raise MissingEvaluationsError(missing_evals)
            
            # All validations passed - proceed with freeze
            
            # Determine rubric version (use first participant's version)
            rubric_version_id = participant_scores[0]["rubric_version_id"]
            
            # Compute deterministic ranking
            ranked_entries = _compute_deterministic_ranking(participant_scores)
            
            # Create snapshot
            snapshot = SessionLeaderboardSnapshot(
                session_id=session_id,
                frozen_by_faculty_id=faculty_id,
                rubric_version_id=rubric_version_id,
                frozen_at=datetime.utcnow(),
                total_participants=len(participants),
                created_at=datetime.utcnow(),
                checksum_hash=""  # Placeholder, computed after entries
            )
            db.add(snapshot)
            await db.flush()  # Get snapshot ID - may raise IntegrityError
            
            # Create leaderboard entries with strict validation
            entry_rows = []
            for rank_data in ranked_entries:
                # STEP 9: Strict enum validation - no silent defaults
                side_value = rank_data.get("side", "")
                if side_value not in LeaderboardSide._value2member_map_:
                    raise LeaderboardError(f"Invalid side value: {side_value}", "INVALID_SIDE")
                side_enum = LeaderboardSide(side_value)
                
                entry = SessionLeaderboardEntry(
                    snapshot_id=snapshot.id,
                    participant_id=rank_data["participant_id"],
                    side=side_enum,
                    speaker_number=rank_data.get("speaker_number"),
                    total_score=Decimal(str(rank_data["total_score"])),
                    tie_breaker_score=Decimal(str(rank_data["tie_breaker_score"])),
                    rank=rank_data["rank"],
                    score_breakdown_json=json.dumps(rank_data.get("score_breakdown", {})),
                    evaluation_ids_json=json.dumps(rank_data.get("evaluation_ids", [])),
                    created_at=datetime.utcnow()
                )
                db.add(entry)
                entry_rows.append(entry)
            
            await db.flush()  # Ensure all entries have IDs
            
            # Compute and store checksum
            checksum = _compute_checksum_from_entries(entry_rows)
            snapshot.checksum_hash = checksum
            
            # Audit log entry
            audit = SessionLeaderboardAudit(
                snapshot_id=snapshot.id,
                action="LEADERBOARD_FROZEN",
                actor_user_id=faculty_id,
                payload_json=json.dumps({
                    "total_participants": len(participants),
                    "checksum": checksum,
                    "rubric_version_id": rubric_version_id
                }),
                created_at=datetime.utcnow()
            )
            db.add(audit)
            
            # Transaction commits automatically at end of async with block
        
        # Refresh to load relationships (outside transaction)
        await db.refresh(snapshot)
        
        logger.info(
            f"Leaderboard frozen: session={session_id}, snapshot={snapshot.id}, "
            f"participants={len(participants)}, checksum={checksum}"
        )
        
        return snapshot, False
        
    except IntegrityError:
        # Another worker created the snapshot concurrently
        # Transaction already rolled back by context manager
        # Fetch and return existing snapshot
        existing_result = await db.execute(
            select(SessionLeaderboardSnapshot).where(
                SessionLeaderboardSnapshot.session_id == session_id
            )
        )
        existing = existing_result.scalar_one()
        
        logger.info(
            f"Leaderboard freeze idempotent: concurrent worker created "
            f"snapshot={existing.id} for session={session_id}"
        )
        
        return existing, True


async def get_leaderboard(
    session_id: int,
    db: AsyncSession
) -> Optional[SessionLeaderboardSnapshot]:
    """
    Retrieve frozen leaderboard for a session.
    
    Args:
        session_id: Classroom session ID
        db: Database session
        
    Returns:
        Frozen snapshot or None if not frozen
    """
    result = await db.execute(
        select(SessionLeaderboardSnapshot).where(
            SessionLeaderboardSnapshot.session_id == session_id
        )
    )
    return result.scalar_one_or_none()


async def get_leaderboard_with_integrity_check(
    session_id: int,
    db: AsyncSession
) -> Tuple[Optional[SessionLeaderboardSnapshot], bool]:
    """
    Retrieve leaderboard and verify integrity.
    
    Args:
        session_id: Classroom session ID
        db: Database session
        
    Returns:
        Tuple of (snapshot, integrity_valid)
        integrity_valid is False if checksum mismatch detected
    """
    snapshot = await get_leaderboard(session_id, db)
    if not snapshot:
        return None, False
    
    # Load entries if not loaded
    if not snapshot.entries:
        result = await db.execute(
            select(SessionLeaderboardEntry).where(
                SessionLeaderboardEntry.snapshot_id == snapshot.id
            ).order_by(SessionLeaderboardEntry.rank)
        )
        entries = result.scalars().all()
    else:
        entries = snapshot.entries
    
    # Verify checksum
    computed = _compute_checksum_from_entries(entries)
    is_valid = computed == snapshot.checksum_hash
    
    if not is_valid:
        logger.error(
            f"Leaderboard integrity check FAILED: session={session_id}, "
            f"stored={snapshot.checksum_hash}, computed={computed}"
        )
    
    return snapshot, is_valid


async def can_freeze_leaderboard(
    session_id: int,
    db: AsyncSession
) -> Tuple[bool, str]:
    """
    Check if leaderboard can be frozen for this session.
    
    Returns:
        Tuple of (can_freeze, reason)
    """
    # Check if already frozen
    existing = await get_leaderboard(session_id, db)
    if existing:
        return False, "Leaderboard already frozen"
    
    # Check session status
    session_result = await db.execute(
        select(ClassroomSession).where(ClassroomSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()
    if not session:
        return False, "Session not found"
    
    if hasattr(session, 'status') and session.status != "COMPLETED":
        return False, "Session not completed"
    
    # Check for completed evaluations
    participants_result = await db.execute(
        select(ClassroomParticipant).where(
            ClassroomParticipant.session_id == session_id
        )
    )
    participants = participants_result.scalars().all()
    
    if not participants:
        return False, "No participants in session"
    
    # Check evaluations
    for participant in participants:
        eval_result = await db.execute(
            select(AIEvaluation).where(
                AIEvaluation.participant_id == participant.id,
                AIEvaluation.status == EvaluationStatus.COMPLETED
            )
        )
        if not eval_result.scalar_one_or_none():
            return False, f"Participant {participant.id} missing completed evaluation"
    
    return True, "Ready to freeze"


# =============================================================================
# Helper Functions
# =============================================================================

async def _get_participant_score_data(
    participant: ClassroomParticipant,
    evaluation: AIEvaluation
) -> Dict[str, Any]:
    """
    Extract score data for a participant from their evaluation.
    
    Returns dict with all data needed for ranking and entry creation.
    Uses Decimal for precision, never float.
    Uses evaluation_epoch (INTEGER) for deterministic tie-breaking.
    """
    # Load evaluation breakdown
    score_breakdown = {}
    if evaluation.score_breakdown:
        score_breakdown = json.loads(evaluation.score_breakdown)
    
    # Get highest single round score for tie-breaking
    highest_round_score = Decimal("0")
    if score_breakdown:
        round_scores = [Decimal(str(v)) for v in score_breakdown.values()]
        highest_round_score = max(round_scores) if round_scores else Decimal("0")
    
    # Total score as Decimal
    total_score = Decimal(str(evaluation.final_score)) if evaluation.final_score else Decimal("0")
    
    # Use evaluation_epoch (INTEGER) for deterministic tie-breaking
    # No ISO timestamp parsing - pure integer comparison
    evaluation_epoch = evaluation.evaluation_epoch or 0
    
    return {
        "participant_id": participant.id,
        "user_id": participant.user_id,
        "side": participant.side if hasattr(participant, 'side') else "petitioner",
        "speaker_number": participant.speaker_number if hasattr(participant, 'speaker_number') else None,
        "total_score": total_score,
        "highest_round_score": highest_round_score,
        "evaluation_epoch": evaluation_epoch,  # INTEGER for deterministic ranking
        "rubric_version_id": evaluation.rubric_version_id,
        "evaluation_ids": [evaluation.id],
        "score_breakdown": score_breakdown
    }


def _compute_deterministic_ranking(
    participant_scores: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Compute deterministic ranking with explicit tie-breaking.
    
    RANKING RULES (in order):
    1. total_score DESC (primary)
    2. highest_round_score DESC (tie-breaker 1)
    3. evaluation_epoch ASC (earlier = better, tie-breaker 2)
    4. participant_id ASC (deterministic final tie-breaker 3)
    
    DENSE RANK: No gaps in rank numbers
    - If scores equal: same rank
    - Next rank = previous rank + 1
    
    Returns ranked entries with dense rank and tie_breaker_score assigned.
    
    NOTE: Uses evaluation_epoch (INTEGER) for pure deterministic comparison.
    No ISO timestamp parsing - eliminates datetime parsing overhead and non-determinism.
    """
    # Sort by ranking criteria using tuple comparison
    # Higher total_score first, higher highest_round_score first,
    # earlier epoch first (lower integer), lower participant_id first
    sorted_participants = sorted(
        participant_scores,
        key=lambda p: (
            -p["total_score"],  # Higher score first (descending)
            -p["highest_round_score"],  # Higher single round first (descending)
            p["evaluation_epoch"],  # Earlier epoch first (ascending - lower int)
            p["participant_id"]  # Lower ID first (ascending, deterministic)
        )
    )
    
    # Assign DENSE rank based on FULL ranking tuple
    # This ensures ties are broken consistently with the sort order
    ranked = []
    current_rank = 1
    previous_key = None
    
    for entry in sorted_participants:
        # Build full ranking key tuple (must match sort order)
        current_key = (
            entry["total_score"],
            entry["highest_round_score"],
            entry["evaluation_epoch"],
            entry["participant_id"]
        )
        
        if previous_key is None:
            entry["rank"] = current_rank
        elif current_key != previous_key:
            current_rank += 1
            entry["rank"] = current_rank
        else:
            entry["rank"] = current_rank
        
        previous_key = current_key
        
        # Compute tie_breaker_score as explicit numeric value
        # Higher value = ranked higher
        # Format: highest_round_score * 10000 + epoch_factor + participant_id_factor
        tie_breaker = entry["highest_round_score"] * Decimal("10000")
        
        # Add epoch factor (earlier epochs get higher values)
        # Use a small fraction that won't overlap with round score
        evaluation_epoch = entry.get("evaluation_epoch", 0)
        # Earlier epochs should get higher tie-breaker
        # Large base minus small fraction of epoch
        tie_breaker += (Decimal("1000000000") - Decimal(evaluation_epoch)) / Decimal("1000000000000")
        
        # Add participant_id factor (lower ID = higher tie-breaker for same scores)
        # This ensures deterministic tie-breaking even with identical scores/epochs
        tie_breaker += (Decimal("1000000") - Decimal(str(entry["participant_id"]))) / Decimal("1000000000000000")
        
        entry["tie_breaker_score"] = tie_breaker
        ranked.append(entry)
    
    return ranked


def _compute_checksum_from_entries(
    entries: List[SessionLeaderboardEntry]
) -> str:
    """
    Compute SHA256 checksum of ordered leaderboard data.
    
    FORMAT:
    - Sort entries by rank ASC, then participant_id ASC
    - Format each entry: participant_id|rank|total_score|tie_breaker_score
    - Use fixed decimal formatting (2 places for score, 4 for tie-breaker)
    - Concatenate with newline separator
    - Compute SHA256 hash
    
    DETERMINISM:
    - Never use float
    - Always use Decimal quantize
    - Always same sort order
    - Always same string format
    """
    parts = []
    
    # Sort by rank, then participant_id for deterministic order
    sorted_entries = sorted(entries, key=lambda e: (e.rank, e.participant_id))
    
    for entry in sorted_entries:
        # Use Decimal quantize for fixed precision
        total_score = Decimal(str(entry.total_score)).quantize(Decimal("0.01"))
        tie_breaker = Decimal(str(entry.tie_breaker_score)).quantize(Decimal("0.0001"))
        
        # Format: participant_id|rank|total_score|tie_breaker_score
        part = f"{entry.participant_id}|{entry.rank}|{total_score:.2f}|{tie_breaker:.4f}"
        parts.append(part)
    
    # Join with newline separator
    combined = "\n".join(parts)
    
    # Compute SHA256
    return hashlib.sha256(combined.encode()).hexdigest()


# =============================================================================
# Admin Operations (Rarely Used)
# =============================================================================

async def invalidate_leaderboard(
    session_id: int,
    admin_id: int,
    reason: str,
    db: AsyncSession
) -> bool:
    """
    Invalidate a frozen leaderboard (admin-only compliance operation).
    
    COMPLIANCE MODE: Snapshots are NEVER physically deleted.
    This function marks the snapshot as invalidated with a reason,
    preserving full audit trail for compliance and legal requirements.
    
    Invalidation is permanent and cannot be undone.
    
    Args:
        session_id: Session ID
        admin_id: Admin user ID performing invalidation
        reason: Detailed reason for invalidation (required for compliance)
        db: Database session
        
    Returns:
        True if invalidated, False if no snapshot existed
        
    Raises:
        UnauthorizedFreezeError: If user is not admin
        LeaderboardError: If reason is not provided
    """
    # Verify admin authorization
    user_result = await db.execute(
        select(User).where(User.id == admin_id)
    )
    user = user_result.scalar_one_or_none()
    if not user or user.role != UserRole.ADMIN:
        raise UnauthorizedFreezeError()
    
    if not reason or not reason.strip():
        raise LeaderboardError("Invalidation reason is required for compliance", "INVALIDATION_REASON_REQUIRED")
    
    async with db.begin():
        # Get snapshot
        snapshot_result = await db.execute(
            select(SessionLeaderboardSnapshot).where(
                SessionLeaderboardSnapshot.session_id == session_id,
                SessionLeaderboardSnapshot.is_invalidated == False
            )
        )
        snapshot = snapshot_result.scalar_one_or_none()
        
        if not snapshot:
            return False
        
        snapshot_id = snapshot.id
        checksum = snapshot.checksum_hash
        
        # Mark as invalidated (soft delete)
        snapshot.is_invalidated = True
        snapshot.invalidated_reason = reason
        snapshot.invalidated_at = datetime.utcnow()
        snapshot.invalidated_by = admin_id
        
        # Audit log entry for invalidation
        audit = SessionLeaderboardAudit(
            snapshot_id=snapshot_id,
            action="LEADERBOARD_INVALIDATED",
            actor_user_id=admin_id,
            payload_json=json.dumps({
                "session_id": session_id,
                "checksum": checksum,
                "reason": reason,
                "invalidated_at": datetime.utcnow().isoformat()
            }),
            created_at=datetime.utcnow()
        )
        db.add(audit)
        
        # Transaction commits automatically
    
    logger.warning(
        f"Leaderboard INVALIDATED by admin: session={session_id}, "
        f"admin={admin_id}, reason={reason}, snapshot={snapshot_id}"
    )
    
    return True


# Keep delete_leaderboard as alias to invalidate_leaderboard for backward compatibility
# but it now performs soft delete only
async def delete_leaderboard(
    session_id: int,
    admin_id: int,
    reason: str,
    db: AsyncSession
) -> bool:
    """
    DEPRECATED: Use invalidate_leaderboard() instead.
    
    This function now delegates to invalidate_leaderboard() for compliance.
    Snapshots are NEVER physically deleted - only marked as invalidated.
    """
    return await invalidate_leaderboard(session_id, admin_id, reason, db)
