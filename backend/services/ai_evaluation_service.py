"""
AI Evaluation Service — Phase 4 (Production-Grade Refactored)

Core evaluation logic with deterministic output, full audit trail,
faculty oversight, and production-safe guarantees.

ARCHITECTURAL GUARANTEES:
1. NO asyncio.Lock - uses DB-level idempotency
2. LLM calls OUTSIDE transactions (3-step pattern)
3. EXPLICIT status transitions (never inferred)
4. Server-side score computation only
5. Frozen rubric snapshots
6. DB-enforced idempotency (uq_round_participant_evaluation)
7. PostgreSQL-compatible (ENUM types, proper locking)
"""
import hashlib
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.ai_rubrics import AIRubric, AIRubricVersion
from backend.orm.ai_evaluations import (
    AIEvaluation, AIEvaluationAttempt, FacultyOverride, 
    AIEvaluationAudit, EvaluationStatus, ParseStatus
)
from backend.orm.classroom_session import ClassroomSession, ClassroomParticipant
from backend.orm.classroom_round import ClassroomRound
from backend.orm.classroom_turn import ClassroomTurn
from backend.services.ai_judge_llm import call_llm_with_retry
from backend.services.ai_judge_validator import (
    validate_llm_json, validate_rubric_definition, 
    extract_criteria_summary, ValidationResult
)

logger = logging.getLogger(__name__)

# NO GLOBAL LOCKS - DB handles concurrency via unique constraint


class AIJudgeError(Exception):
    """Base exception for AI Judge errors."""
    def __init__(self, message: str, code: str = "AI_JUDGE_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class EvaluationNotFoundError(AIJudgeError):
    def __init__(self, evaluation_id: int):
        super().__init__(f"Evaluation {evaluation_id} not found", "EVALUATION_NOT_FOUND")


class RubricNotFoundError(AIJudgeError):
    def __init__(self, rubric_version_id: int):
        super().__init__(f"Rubric version {rubric_version_id} not found", "RUBRIC_NOT_FOUND")


class UnauthorizedEvaluationError(AIJudgeError):
    def __init__(self):
        super().__init__("Not authorized to perform evaluation", "UNAUTHORIZED")


class DuplicateEvaluationError(AIJudgeError):
    def __init__(self, round_id: int, participant_id: int):
        super().__init__(f"Evaluation already exists for round {round_id}, participant {participant_id}", "DUPLICATE_EVALUATION")


class InvalidStateError(AIJudgeError):
    def __init__(self, message: str):
        super().__init__(message, "INVALID_STATE")


# NO asyncio.Lock - DB enforces idempotency via unique constraint


# ============================================================================
# Rubric Management
# ============================================================================

async def create_rubric(
    name: str,
    description: Optional[str],
    rubric_type: str,
    definition: Dict[str, Any],
    created_by_faculty_id: int,
    db: AsyncSession,
    institution_id: Optional[int] = None
) -> AIRubric:
    """
    Create a new rubric with validation.
    
    Automatically creates the first frozen version.
    """
    # Validate definition
    is_valid, errors = validate_rubric_definition(definition)
    if not is_valid:
        raise AIJudgeError(f"Invalid rubric definition: {'; '.join(errors)}", "INVALID_RUBRIC")
    
    # Create rubric
    rubric = AIRubric(
        name=name,
        description=description,
        rubric_type=rubric_type,
        definition_json=json.dumps(definition),
        current_version=1,
        created_by_faculty_id=created_by_faculty_id,
        institution_id=institution_id,
        created_at=datetime.utcnow(),
        is_active=1
    )
    db.add(rubric)
    await db.flush()  # Get rubric ID
    
    # Create frozen version
    version = AIRubricVersion(
        rubric_id=rubric.id,
        version_number=1,
        name=f"{name} v1",
        frozen_json=json.dumps(definition),
        criteria_summary=extract_criteria_summary(definition),
        created_at=datetime.utcnow()
    )
    db.add(version)
    await db.flush()
    
    return rubric


async def get_rubric_version(
    rubric_version_id: int,
    db: AsyncSession
) -> Optional[AIRubricVersion]:
    """Get a rubric version by ID."""
    result = await db.execute(
        select(AIRubricVersion).where(AIRubricVersion.id == rubric_version_id)
    )
    return result.scalar_one_or_none()


async def list_rubrics(
    db: AsyncSession,
    rubric_type: Optional[str] = None,
    institution_id: Optional[int] = None,
    is_active: bool = True
) -> List[AIRubric]:
    """List rubrics with optional filtering."""
    query = select(AIRubric)
    
    if rubric_type:
        query = query.where(AIRubric.rubric_type == rubric_type)
    if institution_id is not None:
        query = query.where(AIRubric.institution_id == institution_id)
    if is_active:
        query = query.where(AIRubric.is_active == 1)
    
    query = query.order_by(AIRubric.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


# ============================================================================
# Core Evaluation Logic
# ============================================================================

async def evaluate(
    session_id: int,
    round_id: int,
    participant_id: int,
    rubric_version_id: int,
    db: AsyncSession,
    user_id: int,
    is_faculty: bool = False,
    turn_id: Optional[int] = None,
    transcript_text: Optional[str] = None,
    ai_model: str = "gemini-1.5-pro"
) -> Dict[str, Any]:
    """
    Execute AI evaluation with full audit trail and production safety.
    
    ARCHITECTURE (3-Step Pattern):
    1. STEP 1: Create evaluation row (PROCESSING) + attempt row - COMMIT
    2. STEP 2: Call LLM (NO DB TRANSACTION HELD)
    3. STEP 3: Update evaluation with results in new transaction - COMMIT
    
    IDEMPOTENCY:
    - DB unique constraint uq_round_participant_evaluation prevents duplicates
    - If evaluation exists and is finalized, return it (no re-evaluation)
    - If evaluation is processing (<5 min), return "processing" status
    
    Args:
        session_id: Classroom session ID
        round_id: Round being evaluated
        participant_id: Participant being evaluated
        rubric_version_id: Rubric version to use (FROZEN snapshot)
        db: Database session
        user_id: User triggering evaluation
        is_faculty: Whether user has faculty privileges
        turn_id: Optional specific turn ID
        transcript_text: Optional override transcript
        ai_model: LLM model to use
        
    Returns:
        Dict with evaluation_id, status, score, etc.
    """
    if not is_faculty:
        raise UnauthorizedEvaluationError()
    
    # STEP 0: Validate state and get rubric (read-only)
    await _validate_evaluation_state(session_id, round_id, participant_id, db)
    
    rubric_version = await get_rubric_version(rubric_version_id, db)
    if not rubric_version:
        raise RubricNotFoundError(rubric_version_id)
    
    # Load FROZEN rubric definition - never access mutable rubric
    rubric_definition = json.loads(rubric_version.frozen_json)
    
    # Get transcript
    if transcript_text is None:
        transcript_text = await _get_transcript(participant_id, round_id, turn_id, db)
    
    if not transcript_text:
        raise InvalidStateError("No transcript available for evaluation")
    
    # Build deterministic prompt
    prompt = _build_evaluation_prompt(transcript_text, rubric_definition, session_id, round_id)
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    
    # STEP 1: Create or get evaluation with idempotency check
    evaluation = await _create_or_get_evaluation_with_idempotency(
        session_id=session_id,
        round_id=round_id,
        participant_id=participant_id,
        turn_id=turn_id,
        rubric_version_id=rubric_version_id,
        ai_model=ai_model,
        db=db
    )
    
    # If already finalized, return cached result (idempotent)
    if evaluation.is_finalized:
        return {
            "evaluation_id": evaluation.id,
            "status": evaluation.status.value,
            "score": float(evaluation.final_score) if evaluation.final_score else None,
            "breakdown": json.loads(evaluation.score_breakdown) if evaluation.score_breakdown else None,
            "message": "Evaluation already completed",
            "from_cache": True
        }
    
    # If processing and not stale, return status
    if evaluation.is_processing:
        return {
            "evaluation_id": evaluation.id,
            "status": "processing",
            "message": "Evaluation in progress",
            "started_at": evaluation.processing_started_at.isoformat() if evaluation.processing_started_at else None
        }
    
    # Create first attempt record and mark PROCESSING
    attempt = AIEvaluationAttempt(
        evaluation_id=evaluation.id,
        attempt_number=1,
        prompt_sent=prompt,
        prompt_hash=prompt_hash,
        parse_status=ParseStatus.OK,
        ai_model=ai_model,
        created_at=datetime.utcnow()
    )
    db.add(attempt)
    
    # Mark as PROCESSING with explicit timestamp
    evaluation.status = EvaluationStatus.PROCESSING
    evaluation.processing_started_at = datetime.utcnow()
    
    # Audit log: STARTED
    await _create_audit_entry(
        db, evaluation.id, attempt.id, "AI_EVALUATION_STARTED",
        user_id, {
            "attempt_number": 1,
            "prompt_hash": prompt_hash,
            "ai_model": ai_model,
            "rubric_version_id": rubric_version_id
        }
    )
    
    # COMMIT STEP 1 - Release all DB locks before LLM call
    await db.commit()
    
    # STEP 2: Call LLM (NO DB TRANSACTION - safe for multi-worker)
    llm_response, _ = await call_llm_with_retry(
        prompt=prompt,
        model=ai_model,
        max_retries=0,
        timeout_seconds=30.0
    )
    
    # STEP 3: Process result in NEW transaction
    async with db.begin():
        # Re-fetch evaluation and attempt (fresh state)
        result = await db.execute(
            select(AIEvaluation).where(AIEvaluation.id == evaluation.id)
        )
        evaluation = result.scalar_one()
        
        result = await db.execute(
            select(AIEvaluationAttempt).where(AIEvaluationAttempt.id == attempt.id)
        )
        attempt = result.scalar_one()
        
        # Update attempt with LLM response
        attempt.llm_raw_response = llm_response.raw_text
        attempt.llm_latency_ms = llm_response.latency_ms
        attempt.llm_token_usage_input = llm_response.token_usage_input
        attempt.llm_token_usage_output = llm_response.token_usage_output
        attempt.ai_model_version = llm_response.model_version
        attempt.completed_at = datetime.utcnow()
        
        if not llm_response.success:
            # LLM call failed (timeout or error)
            attempt.parse_status = ParseStatus.TIMEOUT if "timeout" in (llm_response.error or "").lower() else ParseStatus.ERROR
            
            # Update evaluation status
            evaluation.status = EvaluationStatus.REQUIRES_REVIEW
            evaluation.processing_completed_at = datetime.utcnow()
            
            # Audit log: FAILED
            await _create_audit_entry(
                db, evaluation.id, attempt.id, "AI_EVALUATION_FAILED",
                user_id, {"error": llm_response.error, "parse_status": attempt.parse_status.value}
            )
            
            return {
                "evaluation_id": evaluation.id,
                "status": "requires_review",
                "message": f"LLM call failed: {llm_response.error}",
                "requires_manual_review": True
            }
        
        # Validate LLM response against strict schema
        validation = validate_llm_json(llm_response.raw_text, rubric_definition)
        
        if validation.is_valid:
            # SUCCESS - compute score SERVER-SIDE from FROZEN rubric
            scores = validation.parsed_data.get("scores", {})
            weights = {c["id"]: c["weight"] for c in rubric_definition.get("criteria", [])}
            
            # NEVER trust LLM total - always compute server-side
            computed_score, score_breakdown = _compute_final_score_server_side(scores, weights)
            
            # Update attempt as canonical
            attempt.parse_status = ParseStatus.OK
            attempt.parsed_json = json.dumps(validation.parsed_data)
            attempt.is_canonical = 1
            
            # Update evaluation with COMPLETED status
            evaluation.status = EvaluationStatus.COMPLETED
            evaluation.canonical_attempt_id = attempt.id
            evaluation.final_score = computed_score
            evaluation.score_breakdown = json.dumps(score_breakdown)
            evaluation.weights_used = json.dumps(weights)
            evaluation.ai_model_version = llm_response.model_version
            evaluation.processing_completed_at = datetime.utcnow()
            
            # Audit log: COMPLETED
            await _create_audit_entry(
                db, evaluation.id, attempt.id, "AI_EVALUATION_COMPLETED",
                user_id, {
                    "score": float(computed_score),
                    "breakdown": score_breakdown,
                    "ai_model_version": llm_response.model_version
                }
            )
            
            return {
                "evaluation_id": evaluation.id,
                "status": "completed",
                "score": float(computed_score),
                "breakdown": score_breakdown,
                "ai_model": ai_model,
                "ai_model_version": llm_response.model_version
            }
        else:
            # VALIDATION FAILED
            attempt.parse_status = ParseStatus.MALFORMED
            attempt.parse_errors = json.dumps(validation.errors)
            
            # Update evaluation
            evaluation.status = EvaluationStatus.REQUIRES_REVIEW
            evaluation.processing_completed_at = datetime.utcnow()
            
            # Audit log: REQUIRES_REVIEW
            await _create_audit_entry(
                db, evaluation.id, attempt.id, "AI_EVALUATION_REQUIRES_REVIEW",
                user_id, {
                    "reason": "Validation failed",
                    "errors": validation.errors,
                    "parse_status": "malformed"
                }
            )
            
            return {
                "evaluation_id": evaluation.id,
                "status": "requires_review",
                "message": "LLM response validation failed",
                "errors": validation.errors,
                "requires_manual_review": True
            }


async def _validate_evaluation_state(
    session_id: int,
    round_id: int,
    participant_id: int,
    db: AsyncSession
):
    """Verify session, round, and participant are in valid state for evaluation."""
    # Check session exists
    session_result = await db.execute(
        select(ClassroomSession).where(ClassroomSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise InvalidStateError(f"Session {session_id} not found")
    
    # Check round exists and is completed
    round_result = await db.execute(
        select(ClassroomRound).where(
            ClassroomRound.id == round_id,
            ClassroomRound.session_id == session_id
        )
    )
    round_obj = round_result.scalar_one_or_none()
    if not round_obj:
        raise InvalidStateError(f"Round {round_id} not found in session {session_id}")
    
    # Check participant exists
    participant_result = await db.execute(
        select(ClassroomParticipant).where(
            ClassroomParticipant.id == participant_id,
            ClassroomParticipant.session_id == session_id
        )
    )
    participant = participant_result.scalar_one_or_none()
    if not participant:
        raise InvalidStateError(f"Participant {participant_id} not found in session {session_id}")
    
    # Check round is in appropriate state (completed or active)
    if round_obj.status not in ("COMPLETED", "ACTIVE"):
        raise InvalidStateError(f"Round status is {round_obj.status}, expected COMPLETED or ACTIVE")


async def _create_or_get_evaluation_with_idempotency(
    session_id: int,
    round_id: int,
    participant_id: int,
    turn_id: Optional[int],
    rubric_version_id: int,
    ai_model: str,
    db: AsyncSession
) -> AIEvaluation:
    """
    Create evaluation with DB-enforced idempotency.
    
    Uses unique constraint uq_round_participant_evaluation to prevent duplicates.
    If evaluation exists and is finalized, return it.
    If evaluation is processing, check if stale (>5 min).
    """
    # Check for existing evaluation first
    existing_result = await db.execute(
        select(AIEvaluation).where(
            AIEvaluation.round_id == round_id,
            AIEvaluation.participant_id == participant_id
        )
    )
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        # Check if stale processing evaluation
        if existing.status == EvaluationStatus.PROCESSING:
            if existing.processing_started_at:
                stale_threshold = datetime.utcnow() - existing.processing_started_at
                if stale_threshold.total_seconds() < 300:  # 5 minutes
                    # Still processing, return existing
                    return existing
        # Return existing evaluation (finalized or stale processing)
        return existing
    
    # Create new evaluation
    new_evaluation = AIEvaluation(
        session_id=session_id,
        round_id=round_id,
        participant_id=participant_id,
        turn_id=turn_id,
        rubric_version_id=rubric_version_id,
        ai_model=ai_model,
        status=EvaluationStatus.PENDING,
        created_at=datetime.utcnow()
    )
    db.add(new_evaluation)
    
    try:
        await db.flush()
        return new_evaluation
    except IntegrityError:
        # Race condition: another worker created it
        await db.rollback()
        
        # Fetch the evaluation that was just created
        result = await db.execute(
            select(AIEvaluation).where(
                AIEvaluation.round_id == round_id,
                AIEvaluation.participant_id == participant_id
            )
        )
        return result.scalar_one()


def _compute_final_score_server_side(
    scores: Dict[str, float],
    weights: Dict[str, float]
) -> tuple[Decimal, Dict[str, float]]:
    """
    Compute weighted final score SERVER-SIDE ONLY.
    
    NEVER trust LLM-provided total.
    Formula: Σ(score_i × weight_i)
    """
    total = Decimal("0")
    breakdown = {}
    
    for criterion_id, score in scores.items():
        weight = Decimal(str(weights.get(criterion_id, 0)))
        weighted_score = Decimal(str(score)) * weight
        total += weighted_score
        breakdown[criterion_id] = float(weighted_score)
    
    # Round to 2 decimal places
    final_score = total.quantize(Decimal("0.01"))
    
    return final_score, breakdown


async def _get_transcript(
    participant_id: int,
    round_id: int,
    turn_id: Optional[int],
    db: AsyncSession
) -> Optional[str]:
    """Get transcript for evaluation."""
    if turn_id:
        # Get specific turn transcript
        turn_result = await db.execute(
            select(ClassroomTurn).where(
                ClassroomTurn.id == turn_id,
                ClassroomTurn.participant_id == participant_id
            )
        )
        turn = turn_result.scalar_one_or_none()
        return turn.transcript if turn else None
    else:
        # Get all turns for participant in round, concatenate
        turns_result = await db.execute(
            select(ClassroomTurn).where(
                ClassroomTurn.round_id == round_id,
                ClassroomTurn.participant_id == participant_id,
                ClassroomTurn.is_submitted == True
            ).order_by(ClassroomTurn.turn_order)
        )
        turns = turns_result.scalars().all()
        
        if not turns:
            return None
        
        transcripts = [t.transcript for t in turns if t.transcript]
        return "\n\n---\n\n".join(transcripts) if transcripts else None


def _build_evaluation_prompt(
    transcript: str,
    rubric_definition: Dict[str, Any],
    session_id: int,
    round_id: int
) -> str:
    """Build canonical evaluation prompt."""
    criteria_list = rubric_definition.get("criteria", [])
    instructions = rubric_definition.get("instructions_for_llm", "")
    
    criteria_str = "\n".join([
        f"- {c['id']} ({c['label']}): weight {c['weight']}, scale {c['scale']}"
        for c in criteria_list
    ])
    
    prompt = f"""You are an expert moot court judge evaluating an oral argument.

TRANSCRIPT TO EVALUATE:
{transcript}

EVALUATION CRITERIA:
{criteria_str}

{instructions}

Provide your evaluation as valid JSON only."""
    
    return prompt


async def _create_audit_entry(
    db: AsyncSession,
    evaluation_id: int,
    attempt_id: Optional[int],
    action: str,
    actor_user_id: int,
    payload: Dict[str, Any]
):
    """Create audit log entry (append-only, no flush - caller handles transaction)."""
    audit = AIEvaluationAudit(
        evaluation_id=evaluation_id,
        attempt_id=attempt_id,
        action=action,
        actor_user_id=actor_user_id,
        payload_json=json.dumps(payload) if payload else None,
        created_at=datetime.utcnow()
    )
    db.add(audit)
    # NOTE: No db.flush() here - caller manages transaction


# ============================================================================
# Faculty Override
# ============================================================================

async def create_override(
    evaluation_id: int,
    new_score: Decimal,
    new_breakdown: Dict[str, float],
    reason: str,
    faculty_id: int,
    db: AsyncSession,
    is_faculty: bool = False
) -> FacultyOverride:
    """
    Faculty override of AI evaluation.
    
    NOTE: Evaluation is mutated intentionally to reflect faculty-finalized score.
    This creates a FacultyOverride record AND updates the evaluation to reflect
    the override. The leaderboard freeze will reject any override attempts after freeze.
    
    SECURITY: Cannot override after leaderboard freeze.
    """
    if not is_faculty:
        raise UnauthorizedEvaluationError()
    
    # Get evaluation
    result = await db.execute(
        select(AIEvaluation).where(AIEvaluation.id == evaluation_id)
    )
    evaluation = result.scalar_one_or_none()
    
    if not evaluation:
        raise EvaluationNotFoundError(evaluation_id)
    
    # LOCK: Check if leaderboard already frozen for this session
    from backend.orm.session_leaderboard import SessionLeaderboardSnapshot
    existing_snapshot = await db.execute(
        select(SessionLeaderboardSnapshot).where(
            SessionLeaderboardSnapshot.session_id == evaluation.session_id
        )
    )
    if existing_snapshot.scalar_one_or_none():
        raise InvalidStateError("Cannot override evaluation after leaderboard freeze")
    
    # Create override record
    override = FacultyOverride(
        ai_evaluation_id=evaluation_id,
        previous_score=evaluation.final_score or Decimal("0"),
        new_score=new_score,
        previous_breakdown=evaluation.score_breakdown,
        new_breakdown=json.dumps(new_breakdown),
        faculty_id=faculty_id,
        reason=reason,
        created_at=datetime.utcnow()
    )
    db.add(override)
    
    # Update evaluation status and final score - use Enum directly
    evaluation.status = EvaluationStatus.OVERRIDDEN
    evaluation.final_score = new_score
    evaluation.score_breakdown = json.dumps(new_breakdown)
    evaluation.finalized_by_faculty_id = faculty_id
    evaluation.finalized_at = datetime.utcnow()
    
    await db.flush()
    
    # Log audit - no await since we're in transaction
    await _create_audit_entry(
        db, evaluation_id, None, "AI_EVALUATION_OVERRIDDEN",
        faculty_id, {
            "previous_score": str(override.previous_score),
            "new_score": str(new_score),
            "override_id": override.id,
            "reason": reason
        }
    )
    
    return override


# ============================================================================
# Queries
# ============================================================================

async def get_evaluation(
    evaluation_id: int,
    db: AsyncSession
) -> Optional[AIEvaluation]:
    """Get evaluation by ID."""
    result = await db.execute(
        select(AIEvaluation).where(AIEvaluation.id == evaluation_id)
    )
    return result.scalar_one_or_none()


async def get_evaluation_with_details(
    evaluation_id: int,
    db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """Get evaluation with attempts, overrides, and audit."""
    evaluation = await get_evaluation(evaluation_id, db)
    if not evaluation:
        return None
    
    # Get attempts
    attempts_result = await db.execute(
        select(AIEvaluationAttempt).where(
            AIEvaluationAttempt.evaluation_id == evaluation_id
        ).order_by(AIEvaluationAttempt.attempt_number)
    )
    attempts = attempts_result.scalars().all()
    
    # Get overrides
    overrides_result = await db.execute(
        select(FacultyOverride).where(
            FacultyOverride.ai_evaluation_id == evaluation_id
        ).order_by(FacultyOverride.created_at)
    )
    overrides = overrides_result.scalars().all()
    
    # Get audit
    audit_result = await db.execute(
        select(AIEvaluationAudit).where(
            AIEvaluationAudit.evaluation_id == evaluation_id
        ).order_by(AIEvaluationAudit.created_at)
    )
    audit_entries = audit_result.scalars().all()
    
    return {
        "evaluation": evaluation,
        "attempts": attempts,
        "overrides": overrides,
        "audit_entries": audit_entries
    }


async def list_evaluations_for_session(
    session_id: int,
    db: AsyncSession,
    status: Optional[EvaluationStatus] = None
) -> List[AIEvaluation]:
    """List all evaluations for a session."""
    query = select(AIEvaluation).where(AIEvaluation.session_id == session_id)
    
    if status:
        query = query.where(AIEvaluation.status == status)
    
    query = query.order_by(AIEvaluation.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_session_leaderboard(
    session_id: int,
    db: AsyncSession
) -> List[Dict[str, Any]]:
    """
    Generate leaderboard for session.
    
    Returns participants ranked by final score.
    """
    from sqlalchemy import func
    
    # Get all evaluations for session
    evaluations_result = await db.execute(
        select(
            AIEvaluation.participant_id,
            ClassroomParticipant.user_id,
            ClassroomParticipant.side,
            ClassroomParticipant.speaker_number,
            AIEvaluation.final_score,
            AIEvaluation.status,
            func.count(AIEvaluation.id).over(partition_by=AIEvaluation.participant_id).label('eval_count')
        )
        .join(ClassroomParticipant, AIEvaluation.participant_id == ClassroomParticipant.id)
        .where(
            AIEvaluation.session_id == session_id,
            AIEvaluation.status.in_([EvaluationStatus.COMPLETED, EvaluationStatus.OVERRIDDEN])
        )
    )
    
    rows = evaluations_result.all()
    
    # Aggregate by participant (average scores)
    participant_scores: Dict[int, Dict[str, Any]] = {}
    
    for row in rows:
        pid = row.participant_id
        if pid not in participant_scores:
            participant_scores[pid] = {
                "participant_id": pid,
                "user_id": row.user_id,
                "side": row.side,
                "speaker_number": row.speaker_number,
                "scores": [],
                "has_override": False
            }
        
        if row.final_score:
            participant_scores[pid]["scores"].append(Decimal(str(row.final_score)))
        if row.status == EvaluationStatus.OVERRIDDEN:
            participant_scores[pid]["has_override"] = True
    
    # Calculate averages and rank using Decimal
    entries = []
    for pid, data in participant_scores.items():
        if data["scores"]:
            avg_score = sum(data["scores"]) / len(data["scores"])
            avg_score = avg_score.quantize(Decimal("0.01"))
        else:
            avg_score = Decimal("0.00")
        entries.append({
            "participant_id": pid,
            "user_id": data["user_id"],
            "side": data["side"],
            "speaker_number": data["speaker_number"],
            "final_score": str(avg_score),
            "evaluations_count": len(data["scores"]),
            "has_override": data["has_override"]
        })
    
    # Sort by score descending
    entries.sort(key=lambda x: x["final_score"], reverse=True)
    
    # Add rank
    for i, entry in enumerate(entries, 1):
        entry["rank"] = i
    
    return entries


# ============================================================================
# PHASE 2: Background Task Processing for AI Evaluation
# ============================================================================

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
import os

logger = logging.getLogger(__name__)

# Timeout configuration
EVALUATION_TIMEOUT_SECONDS = 60


async def process_ai_evaluation_background(
    evaluation_id: int,
    db_url: str
):
    """
    Background task to process AI evaluation asynchronously.
    
    This function:
    1. Creates a fresh database session
    2. Calls LLM with timeout protection
    3. Validates JSON response strictly
    4. Updates evaluation with results
    5. Handles errors safely without crashing
    
    Args:
        evaluation_id: ID of the evaluation record
        db_url: Database URL for creating new session
    """
    start_time = datetime.utcnow()
    
    # Create fresh database session for background task
    engine = create_async_engine(db_url, echo=False)
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with AsyncSessionLocal() as db:
        try:
            # Fetch the evaluation record
            result = await db.execute(
                select(AIEvaluation).where(AIEvaluation.id == evaluation_id)
            )
            evaluation = result.scalar_one_or_none()
            
            if not evaluation:
                logger.error(f"[BG Task] Evaluation {evaluation_id} not found")
                return
            
            # Check timeout
            if evaluation.processing_started_at:
                elapsed = (datetime.utcnow() - evaluation.processing_started_at).total_seconds()
                if elapsed > EVALUATION_TIMEOUT_SECONDS:
                    evaluation.status = EvaluationStatus.FAILED
                    evaluation.error_message = "Evaluation timeout (>60s)"
                    await db.commit()
                    logger.error(f"[BG Task] Evaluation {evaluation_id} timeout")
                    return
            
            # Get rubric
            rubric_version = await get_rubric_version(evaluation.rubric_version_id, db)
            if not rubric_version:
                evaluation.status = EvaluationStatus.FAILED
                evaluation.error_message = f"Rubric version {evaluation.rubric_version_id} not found"
                await db.commit()
                logger.error(f"[BG Task] Rubric not found for eval {evaluation_id}")
                return
            
            rubric_definition = json.loads(rubric_version.frozen_json)
            
            # Get transcript
            transcript_text = await _get_transcript(
                evaluation.participant_id, 
                evaluation.round_id, 
                evaluation.turn_id, 
                db
            )
            
            if not transcript_text:
                evaluation.status = EvaluationStatus.FAILED
                evaluation.error_message = "No transcript available for evaluation"
                await db.commit()
                logger.error(f"[BG Task] No transcript for eval {evaluation_id}")
                return
            
            # Build prompt
            prompt = _build_evaluation_prompt(
                transcript_text, 
                rubric_definition, 
                evaluation.session_id, 
                evaluation.round_id
            )
            
            # Call LLM with timeout protection
            try:
                llm_response, metadata = await _call_llm_with_timeout(
                    prompt=prompt,
                    model="gpt-4",
                    timeout_seconds=EVALUATION_TIMEOUT_SECONDS
                )
            except TimeoutError:
                evaluation.status = EvaluationStatus.FAILED
                evaluation.error_message = "LLM call timeout (>60s)"
                await db.commit()
                logger.error(f"[BG Task] LLM timeout for eval {evaluation_id}")
                return
            
            # Strict JSON validation
            validation_result = _strict_json_validation(llm_response, rubric_definition)
            
            if not validation_result["valid"]:
                evaluation.status = EvaluationStatus.REQUIRES_REVIEW
                evaluation.error_message = f"JSON validation failed: {validation_result['errors']}"
                await db.commit()
                logger.error(f"[BG Task] Validation failed for eval {evaluation_id}")
                return
            
            # Extract validated scores
            scores = validation_result["scores"]
            total_score = sum(scores.values()) / len(scores) if scores else 0.0
            
            # Update evaluation with results
            evaluation.status = EvaluationStatus.COMPLETED
            evaluation.final_score = Decimal(str(total_score))
            evaluation.score_breakdown = json.dumps(scores)
            evaluation.processing_completed_at = datetime.utcnow()
            evaluation.is_finalized = True
            
            # Calculate duration
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            await db.commit()
            
            logger.info(
                f"[BG Task] Evaluation {evaluation_id} completed",
                extra={
                    "evaluation_id": evaluation_id,
                    "duration_ms": duration_ms,
                    "total_score": total_score,
                    "success": True
                }
            )
            
        except Exception as e:
            logger.exception(f"[BG Task] Unexpected error for evaluation {evaluation_id}")
            try:
                # Try to mark as failed
                evaluation.status = EvaluationStatus.FAILED
                evaluation.error_message = str(e)[:500]
                await db.commit()
            except:
                pass  # Fail silently if commit fails


async def _call_llm_with_timeout(prompt: str, model: str, timeout_seconds: int = 60):
    """
    Call LLM with timeout protection.
    
    Args:
        prompt: Prompt to send to LLM
        model: Model to use
        timeout_seconds: Maximum time to wait
        
    Returns:
        Tuple of (response_text, metadata)
        
    Raises:
        TimeoutError: If call exceeds timeout
    """
    # Create task for LLM call
    llm_task = asyncio.create_task(call_llm_with_retry(prompt=prompt, model=model))
    
    try:
        result = await asyncio.wait_for(llm_task, timeout=timeout_seconds)
        return result
    except asyncio.TimeoutError:
        llm_task.cancel()
        raise TimeoutError(f"LLM call exceeded {timeout_seconds} seconds")


def _strict_json_validation(llm_response: str, rubric_definition: dict) -> Dict[str, Any]:
    """
    Strictly validate LLM JSON response against rubric.
    
    Rules:
    - All required fields must exist
    - All scores must be integers
    - Score range: 1-5 only
    - Out of range -> mark validation failed (no clamping)
    - Missing fields -> mark validation failed
    
    Args:
        llm_response: Raw LLM response text
        rubric_definition: Rubric definition with criteria
        
    Returns:
        Dict with 'valid' (bool), 'scores' (dict), 'errors' (list)
    """
    errors = []
    scores = {}
    
    try:
        # Parse JSON
        data = json.loads(llm_response)
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "scores": {},
            "errors": [f"Invalid JSON: {str(e)}"]
        }
    
    # Get criteria from rubric
    criteria = rubric_definition.get("criteria", [])
    
    for criterion in criteria:
        criterion_id = criterion.get("id")
        if not criterion_id:
            continue
        
        # Check field exists
        if criterion_id not in data:
            errors.append(f"Missing required field: {criterion_id}")
            continue
        
        value = data[criterion_id]
        
        # Check type is int
        if not isinstance(value, int):
            errors.append(f"Field {criterion_id} must be int, got {type(value).__name__}")
            continue
        
        # Check range (strict - no clamping, mark as error)
        if value < 1 or value > 5:
            errors.append(f"Field {criterion_id} out of range (1-5): {value}")
            continue
        
        scores[criterion_id] = value
    
    return {
        "valid": len(errors) == 0,
        "scores": scores,
        "errors": errors
    }


async def get_evaluation_status(evaluation_id: int, db: AsyncSession) -> Dict[str, Any]:
    """
    Get current status of an evaluation for polling.
    
    Args:
        evaluation_id: Evaluation ID
        db: Database session
        
    Returns:
        Dict with status, score, feedback, error
    """
    result = await db.execute(
        select(AIEvaluation).where(AIEvaluation.id == evaluation_id)
    )
    evaluation = result.scalar_one_or_none()
    
    if not evaluation:
        return {
            "status": "not_found",
            "total_score": None,
            "feedback_text": None,
            "error": "Evaluation not found"
        }
    
    return {
        "status": evaluation.status.value if hasattr(evaluation.status, 'value') else str(evaluation.status),
        "total_score": float(evaluation.final_score) if evaluation.final_score else None,
        "feedback_text": evaluation.feedback_text,
        "error": evaluation.error_message
    }
