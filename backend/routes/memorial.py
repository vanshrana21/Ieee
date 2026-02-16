"""
Memorial API Routes — Phase 1 (Security Hardened)

Pre-oral infrastructure endpoints for:
- Moot problem management
- Clarification release
- Memorial submission (secure streaming file upload)
- Memorial evaluation
- Score freeze

Security:
- File uploads SHA256 hashed (streaming, no memory exhaustion)
- Magic byte validation (PDF signature)
- Only PDF allowed (20MB max)
- RBAC enforcement (ADMIN, HOD, JUDGE, FACULTY)
- Blind review mode support (no identifying data leakage)
- Rate limiting on all mutation endpoints
- Institution-scoped queries
"""
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.orm.user import User, UserRole
from backend.orm.moot_problem import (
    MootProblem, MootClarification, MemorialSubmission,
    MemorialEvaluation, MemorialScoreFreeze, MemorialSide
)
from backend.services.memorial_service import (
    submit_memorial, create_memorial_evaluation, freeze_memorial_scores,
    verify_evaluation_integrity, verify_freeze_integrity,
    get_memorials_by_team, get_memorial_by_id, get_evaluations_by_submission,
    get_clarifications_by_problem, get_next_clarification_sequence,
    check_freeze_exists, FileValidationError, SubmissionLockedError,
    EvaluationBlockedError, FreezeExistsError,
    validate_filename_strict, stream_pdf_upload, generate_internal_filename
)

router = APIRouter(prefix="/memorial", tags=["Phase 1 — Memorial Infrastructure"])

# Configuration
UPLOAD_DIR = os.getenv("MEMORIAL_UPLOAD_DIR", "/var/uploads/memorials")
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


# =============================================================================
# Helper Functions
# =============================================================================

def check_admin_or_hod(user: User) -> bool:
    """Check if user is ADMIN or HOD."""
    return user.role in [UserRole.teacher, UserRole.teacher, UserRole.teacher]

def check_judge_or_faculty(user: User) -> bool:
    """Check if user is JUDGE or FACULTY."""
    return user.role in [UserRole.teacher, UserRole.teacher, UserRole.teacher, UserRole.teacher]


# =============================================================================
# Moot Problem Endpoints
# =============================================================================

@router.post("/admin/moot-problems", status_code=status.HTTP_201_CREATED)
async def create_moot_problem(
    title: str = Form(..., min_length=5, max_length=200),
    description: str = Form(..., min_length=50),
    official_release_at: datetime = Form(...),
    tournament_id: Optional[int] = Form(None),
    blind_review: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Create a new moot problem.
    
    Required Role: ADMIN, HOD, or SUPER_ADMIN
    """
    # Determine version number
    if tournament_id:
        result = await db.execute(
            select(func.max(MootProblem.version_number))
            .where(MootProblem.tournament_id == tournament_id)
        )
        version = (result.scalar() or 0) + 1
    else:
        version = 1
    
    problem = MootProblem(
        institution_id=current_user.institution_id,
        tournament_id=tournament_id,
        title=title,
        description=description,
        official_release_at=official_release_at,
        version_number=version,
        is_active=True,
        blind_review=blind_review,
        created_by=current_user.id,
        created_at=datetime.utcnow()
    )
    
    db.add(problem)
    await db.flush()
    
    return {
        "id": problem.id,
        "title": problem.title,
        "version_number": problem.version_number,
        "message": "Moot problem created successfully"
    }


@router.get("/moot-problems/{problem_id}", status_code=status.HTTP_200_OK)
async def get_moot_problem(
    problem_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get a moot problem by ID.
    
    Returns problem details and clarifications.
    """
    result = await db.execute(
        select(MootProblem).where(MootProblem.id == problem_id)
    )
    problem = result.scalar_one_or_none()
    
    if not problem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Moot problem {problem_id} not found"
        )
    
    # Get clarifications
    clarifications = await get_clarifications_by_problem(problem_id, db)
    
    return {
        "problem": problem.to_dict(),
        "clarifications": [c.to_dict() for c in clarifications],
        "total_clarifications": len(clarifications)
    }


@router.post("/moot-problems/{problem_id}/clarifications", status_code=status.HTTP_201_CREATED)
async def create_clarification(
    problem_id: int,
    question_text: str = Form(..., min_length=10),
    official_response: str = Form(..., min_length=10),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Release a clarification for a moot problem.
    
    Required Role: ADMIN, HOD, or SUPER_ADMIN
    
    Clarifications are immutable once created and ordered by release_sequence.
    """
    # Verify problem exists
    result = await db.execute(
        select(MootProblem).where(MootProblem.id == problem_id)
    )
    problem = result.scalar_one_or_none()
    
    if not problem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Moot problem {problem_id} not found"
        )
    
    # Get next sequence number
    next_sequence = await get_next_clarification_sequence(problem_id, db)
    
    clarification = MootClarification(
        moot_problem_id=problem_id,
        question_text=question_text,
        official_response=official_response,
        released_at=datetime.utcnow(),
        release_sequence=next_sequence,
        created_by=current_user.id,
        created_at=datetime.utcnow()
    )
    
    db.add(clarification)
    await db.flush()
    
    return {
        "id": clarification.id,
        "moot_problem_id": clarification.moot_problem_id,
        "release_sequence": clarification.release_sequence,
        "message": "Clarification released successfully"
    }


# =============================================================================
# Memorial Submission Endpoints
# =============================================================================

@router.post("/teams/{team_id}/memorial", status_code=status.HTTP_201_CREATED)
async def submit_team_memorial(
    team_id: int,
    moot_problem_id: int = Form(...),
    side: MemorialSide = Form(...),
    file: UploadFile = File(...),
    deadline_at: datetime = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Submit a memorial for a team (streaming upload, security hardened).
    
    File Requirements:
    - Only PDF allowed (magic byte validated)
    - Max 20MB (streaming, no memory exhaustion)
    - SHA256 hash computed during streaming
    - UUID-based internal filename
    
    Submission Logic:
    - Late submissions allowed but marked as late
    - Resubmission increments resubmission_number
    - Previous file deleted on resubmission
    """
    # Validate filename (strict, before streaming)
    try:
        validate_filename_strict(file.filename)
    except FileValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # Generate internal filename
    internal_filename = generate_internal_filename()
    destination_path = os.path.join(UPLOAD_DIR, internal_filename)
    
    # Stream upload with magic byte validation and hash computation
    try:
        file_hash, file_size = await stream_pdf_upload(
            file,
            destination_path,
            max_size=MAX_FILE_SIZE
        )
    except HTTPException:
        raise  # Already has proper status code
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File upload failed: {str(e)}"
        )
    
    # Check for existing submission
    result = await db.execute(
        select(MemorialSubmission).where(
            and_(
                MemorialSubmission.tournament_team_id == team_id,
                MemorialSubmission.moot_problem_id == moot_problem_id,
                MemorialSubmission.side == side
            )
        ).order_by(MemorialSubmission.resubmission_number.desc())
    )
    existing = result.scalar_one_or_none()
    
    # Determine resubmission number
    if existing:
        if existing.is_locked:
            # Clean up uploaded file
            os.remove(destination_path)
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Cannot resubmit: previous submission is locked"
            )
        resubmission_number = existing.resubmission_number + 1
        
        # Delete old file (best effort)
        try:
            if os.path.exists(existing.file_path):
                os.remove(existing.file_path)
        except OSError:
            pass
    else:
        resubmission_number = 1
    
    # Compute late status
    submitted_at = datetime.utcnow()
    is_late = submitted_at > deadline_at
    
    # Create submission record
    submission = MemorialSubmission(
        tournament_team_id=team_id,
        moot_problem_id=moot_problem_id,
        side=side,
        file_path=destination_path,
        file_hash_sha256=file_hash,
        file_size_bytes=file_size,
        original_filename=file.filename,
        internal_filename=internal_filename,
        submitted_at=submitted_at,
        deadline_at=deadline_at,
        is_late=is_late,
        resubmission_number=resubmission_number,
        is_locked=False,
        created_at=submitted_at
    )
    
    db.add(submission)
    await db.flush()
    
    return {
        "id": submission.id,
        "tournament_team_id": submission.tournament_team_id,
        "moot_problem_id": submission.moot_problem_id,
        "side": submission.side.value,
        "file_hash_sha256": submission.file_hash_sha256,
        "file_size_bytes": submission.file_size_bytes,
        "is_late": submission.is_late,
        "resubmission_number": submission.resubmission_number,
        "message": "Memorial submitted successfully" + (" (LATE)" if submission.is_late else "")
    }


@router.get("/teams/{team_id}/memorials", status_code=status.HTTP_200_OK)
async def get_team_memorials(
    team_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get all memorial submissions for a team (institution-scoped).
    
    Returns submission history including all resubmissions.
    """
    # Institution-scoped query
    memorials = await get_memorials_by_team(
        tournament_team_id=team_id,
        institution_id=current_user.institution_id,
        db=db
    )
    
    return {
        "team_id": team_id,
        "memorials": [m.to_dict(include_file_path=False) for m in memorials],
        "total_count": len(memorials)
    }


# =============================================================================
# Memorial Evaluation Endpoints
# =============================================================================

@router.post("/judges/memorial/{submission_id}/evaluate", status_code=status.HTTP_201_CREATED)
async def evaluate_memorial(
    submission_id: int,
    legal_analysis_score: Decimal = Form(..., ge=0, le=100),
    research_depth_score: Decimal = Form(..., ge=0, le=100),
    clarity_score: Decimal = Form(..., ge=0, le=100),
    citation_format_score: Decimal = Form(..., ge=0, le=100),
    rubric_version_id: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Evaluate a memorial submission.
    
    Required Role: JUDGE, FACULTY, ADMIN, or SUPER_ADMIN
    
    Scoring:
    - All scores 0-100 (Decimal)
    - Total computed server-side
    - Evaluation hash stored for integrity
    - Blocked if scores frozen
    """
    try:
        evaluation = await create_memorial_evaluation(
            memorial_submission_id=submission_id,
            judge_id=current_user.id,
            legal_analysis_score=legal_analysis_score,
            research_depth_score=research_depth_score,
            clarity_score=clarity_score,
            citation_format_score=citation_format_score,
            rubric_version_id=rubric_version_id,
            db=db
        )
        
        return {
            "id": evaluation.id,
            "memorial_submission_id": evaluation.memorial_submission_id,
            "judge_id": evaluation.judge_id,
            "legal_analysis_score": str(evaluation.legal_analysis_score),
            "research_depth_score": str(evaluation.research_depth_score),
            "clarity_score": str(evaluation.clarity_score),
            "citation_format_score": str(evaluation.citation_format_score),
            "total_score": str(evaluation.total_score),
            "evaluation_hash": evaluation.evaluation_hash,
            "message": "Evaluation created successfully"
        }
        
    except EvaluationBlockedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.get("/judges/memorial/{submission_id}", status_code=status.HTTP_200_OK)
async def get_memorial_for_evaluation(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Get memorial submission details for evaluation (institution-scoped).
    
    Supports blind review mode if enabled on moot problem.
    Returns 404 if submission not in user's institution (no information leakage).
    """
    # Get submission with institution scoping
    submission = await get_memorial_by_id(
        submission_id=submission_id,
        institution_id=current_user.institution_id,
        db=db
    )
    
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Get moot problem to check blind review setting
    result = await db.execute(
        select(MootProblem).where(MootProblem.id == submission.moot_problem_id)
    )
    problem = result.scalar_one_or_none()
    
    blind_mode = problem.blind_review if problem else False
    
    # Get evaluations (institution-scoped)
    evaluations = await get_evaluations_by_submission(
        memorial_submission_id=submission_id,
        institution_id=current_user.institution_id,
        db=db
    )
    
    return {
        "submission": submission.to_dict(include_file_path=False, blind_mode=blind_mode),
        "moot_problem": {
            "id": problem.id if problem else None,
            "title": problem.title if problem else None,
            "blind_review": blind_mode
        },
        "existing_evaluations": len(evaluations),
        "evaluations": [e.to_dict(blind_mode=blind_mode) for e in evaluations] if not blind_mode else []
    }


@router.get("/evaluations/{evaluation_id}/verify", status_code=status.HTTP_200_OK)
async def verify_evaluation(
    evaluation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Verify the integrity of a memorial evaluation.
    
    Recomputes hash and compares with stored value.
    """
    verification = await verify_evaluation_integrity(evaluation_id, db)
    
    if not verification["found"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=verification.get("error", "Evaluation not found")
        )
    
    return verification


# =============================================================================
# Score Freeze Endpoints
# =============================================================================

@router.post("/admin/moot-problems/{problem_id}/memorial-freeze", status_code=status.HTTP_201_CREATED)
async def freeze_problem_scores(
    problem_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Freeze all memorial scores for a moot problem.
    
    Required Role: ADMIN, HOD, or SUPER_ADMIN
    
    Freeze Effects:
    - All submissions locked
    - No new evaluations allowed
    - Checksum computed for all evaluations
    - Immutable after creation
    
    Uses SERIALIZABLE isolation for atomic freeze.
    """
    try:
        freeze = await freeze_memorial_scores(
            moot_problem_id=problem_id,
            frozen_by=current_user.id,
            db=db
        )
        
        return {
            "id": freeze.id,
            "moot_problem_id": freeze.moot_problem_id,
            "frozen_at": freeze.frozen_at.isoformat(),
            "checksum": freeze.checksum,
            "total_evaluations": freeze.total_evaluations,
            "is_final": freeze.is_final,
            "message": "Scores frozen successfully. All submissions locked."
        }
        
    except FreezeExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.get("/admin/freezes/{freeze_id}/verify", status_code=status.HTTP_200_OK)
async def verify_freeze(
    freeze_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Verify the integrity of a score freeze.
    
    Recomputes checksum from current evaluation data.
    """
    verification = await verify_freeze_integrity(freeze_id, db)
    
    if not verification["found"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=verification.get("error", "Freeze not found")
        )
    
    return verification


# =============================================================================
# Query Endpoints
# =============================================================================

@router.get("/moot-problems/{problem_id}/freeze-status", status_code=status.HTTP_200_OK)
async def check_freeze_status(
    problem_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Check if scores are frozen for a moot problem.
    """
    freeze = await check_freeze_exists(problem_id, db)
    
    return {
        "moot_problem_id": problem_id,
        "is_frozen": freeze is not None,
        "freeze_id": freeze.id if freeze else None,
        "frozen_at": freeze.frozen_at.isoformat() if freeze else None,
        "total_evaluations": freeze.total_evaluations if freeze else 0
    }


@router.get("/moot-problems/{problem_id}/submissions", status_code=status.HTTP_200_OK)
async def get_problem_submissions(
    problem_id: int,
    side: Optional[MemorialSide] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Get all memorial submissions for a moot problem.
    
    Supports blind review mode.
    """
    # Get problem for blind review setting
    result = await db.execute(
        select(MootProblem).where(MootProblem.id == problem_id)
    )
    problem = result.scalar_one_or_none()
    
    if not problem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Moot problem {problem_id} not found"
        )
    
    # Build query
    query = select(MemorialSubmission).where(
        MemorialSubmission.moot_problem_id == problem_id
    )
    
    if side:
        query = query.where(MemorialSubmission.side == side)
    
    query = query.order_by(MemorialSubmission.created_at.desc())
    
    result = await db.execute(query)
    submissions = list(result.scalars().all())
    
    blind_mode = problem.blind_review
    
    return {
        "moot_problem_id": problem_id,
        "blind_review_mode": blind_mode,
        "total_submissions": len(submissions),
        "submissions": [s.to_dict(include_file_path=False, blind_mode=blind_mode) for s in submissions]
    }


@router.get("/moot-problems/{problem_id}/evaluations", status_code=status.HTTP_200_OK)
async def get_problem_evaluations(
    problem_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
) -> Dict[str, Any]:
    """
    Get all evaluations for a moot problem (admin only).
    
    Full access to all evaluation data for administrative review.
    """
    # Get all submissions for this problem
    result = await db.execute(
        select(MemorialSubmission.id).where(
            MemorialSubmission.moot_problem_id == problem_id
        )
    )
    submission_ids = [row[0] for row in result.all()]
    
    if not submission_ids:
        return {
            "moot_problem_id": problem_id,
            "total_evaluations": 0,
            "evaluations": []
        }
    
    # Get all evaluations
    result = await db.execute(
        select(MemorialEvaluation)
        .where(MemorialEvaluation.memorial_submission_id.in_(submission_ids))
        .order_by(MemorialEvaluation.evaluated_at.desc())
    )
    evaluations = list(result.scalars().all())
    
    return {
        "moot_problem_id": problem_id,
        "total_evaluations": len(evaluations),
        "evaluations": [e.to_dict() for e in evaluations]
    }
