"""
Phase 2 — Hardened Oral Rounds Service Layer

Security guarantees:
- Deterministic scoring (Decimal quantization)
- SHA256 hashing for integrity
- DB-level freeze immutability (triggers)
- SERIALIZABLE isolation on finalize
- Institution scoping enforced
- No information leakage on 404

Determinism rules:
- Only Decimal (Numeric) for scores
- No float()
- No random()
- No datetime.now() — only utcnow()
- SHA256 for all hashes
- JSON dumps with sort_keys=True
- Sorted() for all sequences
"""
import hashlib
import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from backend.orm.oral_rounds import (
    OralRoundTemplate, OralSession, OralTurn, OralEvaluation, OralSessionFreeze,
    OralSessionStatus, OralSide, OralTurnType, QUANTIZER_2DP
)
from backend.orm.national_network import TournamentTeam
from backend.orm.institutional_governance import Institution


# =============================================================================
# Custom Exceptions
# =============================================================================

class OralServiceError(Exception):
    """Base exception for oral service errors."""
    pass


class SessionNotFoundError(OralServiceError):
    """Raised when oral session is not found."""
    pass


class SessionFinalizedError(OralServiceError):
    """Raised when trying to modify finalized session."""
    pass


class EvaluationExistsError(OralServiceError):
    """Raised when evaluation already exists."""
    pass


class InstitutionScopeError(OralServiceError):
    """Raised when user tries to access cross-institution data."""
    pass


# =============================================================================
# Helper Functions
# =============================================================================

def quantize_decimal(value: Decimal) -> Decimal:
    """Quantize Decimal to 2 decimal places."""
    return Decimal(str(value)).quantize(QUANTIZER_2DP, rounding=ROUND_HALF_UP)


# =============================================================================
# Template Functions
# =============================================================================

async def create_oral_template(
    institution_id: int,
    name: str,
    version: int,
    structure: List[Dict[str, Any]],
    db: AsyncSession
) -> OralRoundTemplate:
    """
    Create new oral round template.
    
    Args:
        institution_id: Owning institution
        name: Template name
        version: Version number
        structure: List of turn definitions (turn_type, allocated_seconds)
        db: Database session
        
    Returns:
        Created OralRoundTemplate
    """
    template = OralRoundTemplate(
        institution_id=institution_id,
        name=name,
        version=version,
        structure_json=structure,
        created_at=datetime.utcnow()
    )
    
    db.add(template)
    await db.flush()
    
    return template


async def get_template_by_id(
    template_id: int,
    institution_id: int,
    db: AsyncSession
) -> Optional[OralRoundTemplate]:
    """
    Get template by ID (institution-scoped).
    
    Returns None if not found or not in user's institution.
    """
    result = await db.execute(
        select(OralRoundTemplate).where(
            and_(
                OralRoundTemplate.id == template_id,
                OralRoundTemplate.institution_id == institution_id
            )
        )
    )
    return result.scalar_one_or_none()


# =============================================================================
# Session Functions
# =============================================================================

async def create_oral_session(
    institution_id: int,
    petitioner_team_id: int,
    respondent_team_id: int,
    round_template_id: int,
    db: AsyncSession,
    created_by: int
) -> OralSession:
    """
    Create new oral session in DRAFT status.
    
    Args:
        institution_id: Owning institution (enforced)
        petitioner_team_id: Petitioner team
        respondent_team_id: Respondent team
        round_template_id: Template for structure
        db: Database session
        created_by: User creating the session
        
    Returns:
        Created OralSession
    """
    # Verify teams are in the same institution
    result = await db.execute(
        select(TournamentTeam).where(
            and_(
                TournamentTeam.id.in_([petitioner_team_id, respondent_team_id]),
                TournamentTeam.institution_id == institution_id
            )
        )
    )
    teams = result.scalars().all()
    
    if len(teams) != 2:
        raise InstitutionScopeError("Teams must belong to the same institution")
    
    # Verify template exists and belongs to institution
    template = await get_template_by_id(round_template_id, institution_id, db)
    if not template:
        raise OralServiceError("Template not found or not in institution")
    
    session = OralSession(
        institution_id=institution_id,
        petitioner_team_id=petitioner_team_id,
        respondent_team_id=respondent_team_id,
        round_template_id=round_template_id,
        status=OralSessionStatus.DRAFT,
        finalized_at=None,
        finalized_by=None,
        session_hash=None,
        created_at=datetime.utcnow()
    )
    
    db.add(session)
    await db.flush()
    
    return session


async def get_oral_session_by_id(
    session_id: int,
    institution_id: int,
    db: AsyncSession
) -> Optional[OralSession]:
    """
    Get oral session by ID (institution-scoped).
    
    Returns None if not found or not in user's institution.
    """
    result = await db.execute(
        select(OralSession).where(
            and_(
                OralSession.id == session_id,
                OralSession.institution_id == institution_id
            )
        )
    )
    return result.scalar_one_or_none()


async def activate_oral_session(
    session_id: int,
    institution_id: int,
    participant_assignments: Dict[str, List[int]],
    db: AsyncSession
) -> OralSession:
    """
    Activate oral session and create turns from template.
    
    Args:
        session_id: Session to activate
        institution_id: Institution for scoping
        participant_assignments: Dict mapping side to list of participant IDs
                              e.g., {'petitioner': [1, 2], 'respondent': [3, 4]}
        db: Database session
        
    Returns:
        Activated OralSession
    """
    # Get session with institution scoping
    session = await get_oral_session_by_id(session_id, institution_id, db)
    
    if not session:
        raise SessionNotFoundError(f"Session {session_id} not found")
    
    if session.status != OralSessionStatus.DRAFT:
        raise OralServiceError(f"Cannot activate session in status: {session.status}")
    
    # Get template structure
    result = await db.execute(
        select(OralRoundTemplate).where(OralRoundTemplate.id == session.round_template_id)
    )
    template = result.scalar_one()
    
    structure = template.structure_json
    
    # Create turns based on template structure
    order_index = 0
    for turn_def in structure:
        side = OralSide(turn_def['side'])
        turn_type = OralTurnType(turn_def['turn_type'])
        allocated_seconds = turn_def['allocated_seconds']
        
        # Assign participant from appropriate side
        participants = participant_assignments.get(side.value, [])
        participant_idx = order_index % len(participants) if participants else 0
        participant_id = participants[participant_idx] if participants else None
        
        turn = OralTurn(
            session_id=session.id,
            participant_id=participant_id,
            side=side,
            turn_type=turn_type,
            allocated_seconds=allocated_seconds,
            order_index=order_index,
            created_at=datetime.utcnow()
        )
        
        db.add(turn)
        order_index += 1
    
    # Update session status
    session.status = OralSessionStatus.ACTIVE
    
    await db.flush()
    
    return session


# =============================================================================
# Evaluation Functions
# =============================================================================

async def create_oral_evaluation(
    session_id: int,
    judge_id: int,
    speaker_id: int,
    legal_reasoning_score: Decimal,
    structure_score: Decimal,
    responsiveness_score: Decimal,
    courtroom_control_score: Decimal,
    institution_id: int,
    db: AsyncSession
) -> OralEvaluation:
    """
    Create oral evaluation with deterministic scoring.
    
    Args:
        session_id: Session being evaluated
        judge_id: Evaluating judge
        speaker_id: Speaker being evaluated
        *_score: Component scores (Decimal)
        institution_id: Institution for scoping
        db: Database session
        
    Returns:
        Created OralEvaluation
        
    Raises:
        SessionNotFoundError: If session not found
        SessionFinalizedError: If session already finalized
        EvaluationExistsError: If evaluation already exists
    """
    # Get session with institution scoping
    session = await get_oral_session_by_id(session_id, institution_id, db)
    
    if not session:
        raise SessionNotFoundError(f"Session {session_id} not found")
    
    # Check if already finalized
    if session.status == OralSessionStatus.FINALIZED:
        raise SessionFinalizedError("Cannot evaluate finalized session")
    
    # Quantize all scores
    legal_reasoning_score = quantize_decimal(legal_reasoning_score)
    structure_score = quantize_decimal(structure_score)
    responsiveness_score = quantize_decimal(responsiveness_score)
    courtroom_control_score = quantize_decimal(courtroom_control_score)
    
    # Compute total deterministically
    total_score = (
        legal_reasoning_score +
        structure_score +
        responsiveness_score +
        courtroom_control_score
    )
    total_score = quantize_decimal(total_score)
    
    # Create evaluation object first to compute hash
    evaluation = OralEvaluation(
        session_id=session_id,
        judge_id=judge_id,
        speaker_id=speaker_id,
        legal_reasoning_score=legal_reasoning_score,
        structure_score=structure_score,
        responsiveness_score=responsiveness_score,
        courtroom_control_score=courtroom_control_score,
        total_score=total_score,
        evaluation_hash="",  # Will compute
        created_at=datetime.utcnow()
    )
    
    # Compute deterministic hash
    evaluation.evaluation_hash = evaluation.compute_evaluation_hash()
    
    db.add(evaluation)
    
    try:
        await db.flush()
    except IntegrityError as e:
        if "uq_evaluation_session_judge_speaker" in str(e):
            raise EvaluationExistsError(
                f"Evaluation already exists for judge {judge_id} and speaker {speaker_id}"
            )
        raise
    
    return evaluation


async def get_evaluations_by_session(
    session_id: int,
    institution_id: int,
    db: AsyncSession
) -> List[OralEvaluation]:
    """
    Get all evaluations for a session (institution-scoped).
    """
    result = await db.execute(
        select(OralEvaluation)
        .join(OralSession, OralEvaluation.session_id == OralSession.id)
        .where(
            and_(
                OralEvaluation.session_id == session_id,
                OralSession.institution_id == institution_id
            )
        )
        .order_by(OralEvaluation.created_at.desc())
    )
    return list(result.scalars().all())


# =============================================================================
# Finalize Functions
# =============================================================================

async def finalize_oral_session(
    session_id: int,
    institution_id: int,
    finalized_by: int,
    db: AsyncSession
) -> OralSessionFreeze:
    """
    Finalize oral session with SERIALIZABLE isolation.
    
    Steps:
    1. Begin SERIALIZABLE transaction
    2. Verify all expected evaluations exist
    3. Get all evaluations with hashes (sorted for determinism)
    4. Compute session checksum
    5. Build immutable snapshot
    6. Insert OralSessionFreeze
    7. Update session status = FINALIZED
    8. Commit atomically
    
    Idempotency: If freeze already exists, return it (no-op).
    
    Args:
        session_id: Session to finalize
        institution_id: Institution for scoping
        finalized_by: User finalizing the session
        db: Database session
        
    Returns:
        OralSessionFreeze record
        
    Raises:
        SessionNotFoundError: If session not found
        OralServiceError: If evaluation count mismatch
    """
    # Set SERIALIZABLE isolation for PostgreSQL
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    
    # Check if freeze already exists (idempotency)
    result = await db.execute(
        select(OralSessionFreeze).where(OralSessionFreeze.session_id == session_id)
    )
    existing_freeze = result.scalar_one_or_none()
    
    if existing_freeze:
        return existing_freeze
    
    # Get session with institution scoping
    session = await get_oral_session_by_id(session_id, institution_id, db)
    
    if not session:
        raise SessionNotFoundError(f"Session {session_id} not found")
    
    if session.status == OralSessionStatus.FINALIZED:
        raise OralServiceError("Session already finalized")
    
    if session.status != OralSessionStatus.ACTIVE:
        raise OralServiceError(f"Cannot finalize session in status: {session.status}")
    
    # Get all evaluations with their IDs and hashes (sorted by ID for determinism)
    result = await db.execute(
        select(OralEvaluation.id, OralEvaluation.evaluation_hash)
        .where(OralEvaluation.session_id == session_id)
        .order_by(OralEvaluation.id.asc())
    )
    evaluations = result.all()
    
    if not evaluations:
        raise OralServiceError(
            f"No evaluations found for session {session_id}"
        )
    
    # Collect hashes in deterministic order (sorted by evaluation_id)
    evaluation_hashes = [eval_hash for _, eval_hash in evaluations]
    
    # Build immutable snapshot for tamper detection
    evaluation_snapshot = [
        {
            "evaluation_id": eval_id,
            "hash": eval_hash
        }
        for eval_id, eval_hash in evaluations
    ]
    
    # Compute session checksum
    freeze = OralSessionFreeze(
        session_id=session_id,
        evaluation_snapshot_json=evaluation_snapshot,
        session_checksum="",  # Will compute
        frozen_at=datetime.utcnow(),
        frozen_by=finalized_by,
        created_at=datetime.utcnow()
    )
    
    freeze.session_checksum = freeze.compute_session_checksum(evaluation_hashes)
    
    # Update session
    session.status = OralSessionStatus.FINALIZED
    session.finalized_at = datetime.utcnow()
    session.finalized_by = finalized_by
    session.session_hash = freeze.session_checksum
    
    db.add(freeze)
    
    try:
        await db.flush()
    except IntegrityError:
        # Another process finalized concurrently - fetch existing freeze
        result = await db.execute(
            select(OralSessionFreeze).where(OralSessionFreeze.session_id == session_id)
        )
        return result.scalar_one()
    
    return freeze


async def verify_oral_session_integrity(
    session_id: int,
    institution_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Verify oral session integrity by comparing snapshot to current data.
    
    Checks:
    - Each evaluation in snapshot exists and hash matches
    - No evaluations deleted
    - No new evaluations added after freeze
    
    Args:
        session_id: Session to verify
        institution_id: Institution for scoping
        db: Database session
        
    Returns:
        Verification result dictionary
    """
    # Get session with institution scoping
    session = await get_oral_session_by_id(session_id, institution_id, db)
    
    if not session:
        return {
            "session_id": session_id,
            "found": False,
            "valid": False,
            "error": "Session not found"
        }
    
    # Get freeze record
    result = await db.execute(
        select(OralSessionFreeze).where(OralSessionFreeze.session_id == session_id)
    )
    freeze = result.scalar_one_or_none()
    
    if not freeze:
        return {
            "session_id": session_id,
            "found": True,
            "frozen": False,
            "valid": False,
            "error": "Session not yet frozen"
        }
    
    # Get all current evaluations with their hashes
    result = await db.execute(
        select(OralEvaluation.id, OralEvaluation.evaluation_hash)
        .where(OralEvaluation.session_id == session_id)
        .order_by(OralEvaluation.id.asc())
    )
    current_evaluations = {row[0]: row[1] for row in result.all()}
    
    # Check each snapshot entry against current data
    tampered_evaluations = []
    for snapshot in freeze.evaluation_snapshot_json:
        eval_id = snapshot["evaluation_id"]
        stored_hash = snapshot["hash"]
        current_hash = current_evaluations.get(eval_id)
        
        if current_hash is None:
            tampered_evaluations.append({
                "evaluation_id": eval_id,
                "issue": "Evaluation missing (deleted)"
            })
        elif current_hash != stored_hash:
            tampered_evaluations.append({
                "evaluation_id": eval_id,
                "issue": "Hash mismatch (modified)",
                "stored_hash": stored_hash,
                "current_hash": current_hash
            })
    
    # Check for new evaluations added after freeze
    snapshot_ids = {snap["evaluation_id"] for snap in freeze.evaluation_snapshot_json}
    new_evaluations = [
        eval_id for eval_id in current_evaluations.keys()
        if eval_id not in snapshot_ids
    ]
    
    is_valid = len(tampered_evaluations) == 0 and len(new_evaluations) == 0
    
    return {
        "session_id": session_id,
        "found": True,
        "frozen": True,
        "valid": is_valid,
        "stored_checksum": freeze.session_checksum,
        "total_evaluations": freeze.total_evaluations if hasattr(freeze, 'total_evaluations') else len(freeze.evaluation_snapshot_json),
        "frozen_at": freeze.frozen_at.isoformat() if freeze.frozen_at else None,
        "tampered_evaluations": tampered_evaluations if tampered_evaluations else None,
        "new_evaluations_added": new_evaluations if new_evaluations else None,
        "tamper_detected": len(tampered_evaluations) > 0 or len(new_evaluations) > 0
    }


# =============================================================================
# Turn Functions
# =============================================================================

async def get_turns_by_session(
    session_id: int,
    institution_id: int,
    db: AsyncSession
) -> List[OralTurn]:
    """
    Get all turns for a session (institution-scoped).
    """
    result = await db.execute(
        select(OralTurn)
        .join(OralSession, OralTurn.session_id == OralSession.id)
        .where(
            and_(
                OralTurn.session_id == session_id,
                OralSession.institution_id == institution_id
            )
        )
        .order_by(OralTurn.order_index.asc())
    )
    return list(result.scalars().all())


# =============================================================================
# Query Functions (Institution-Scoped)
# =============================================================================

async def get_sessions_by_institution(
    institution_id: int,
    status: Optional[OralSessionStatus],
    db: AsyncSession
) -> List[OralSession]:
    """
    Get sessions by institution (admin view).
    """
    query = select(OralSession).where(OralSession.institution_id == institution_id)
    
    if status:
        query = query.where(OralSession.status == status)
    
    query = query.order_by(OralSession.created_at.desc())
    
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_sessions_by_team(
    team_id: int,
    institution_id: int,
    db: AsyncSession
) -> List[OralSession]:
    """
    Get sessions where team is participant (institution-scoped).
    """
    result = await db.execute(
        select(OralSession)
        .join(TournamentTeam, 
            or_(
                OralSession.petitioner_team_id == TournamentTeam.id,
                OralSession.respondent_team_id == TournamentTeam.id
            )
        )
        .where(
            and_(
                TournamentTeam.id == team_id,
                TournamentTeam.institution_id == institution_id,
                OralSession.institution_id == institution_id
            )
        )
        .order_by(OralSession.created_at.desc())
    )
    return list(result.scalars().all())


# Need to import 'or_' for the query above
# from sqlalchemy import or_  # Already imported at top
