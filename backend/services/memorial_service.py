"""
Memorial Service — Phase 1

Pre-oral infrastructure for moot court memorials:
- Memorial submission handling with file integrity
- Evaluation scoring engine with deterministic hashing
- Score freeze for immutability
- Deadline enforcement
- Blind review support

Security:
- All file uploads SHA256 hashed
- No float usage (Decimal only)
- Immutable freeze layer
- Institution-scoped queries
"""
import hashlib
import os
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from backend.orm.moot_problem import (
    MootProblem, MootClarification, MemorialSubmission,
    MemorialEvaluation, MemorialScoreFreeze, MemorialSide,
    generate_internal_filename, compute_file_hash
)
from backend.orm.user import User
from backend.orm.national_network import TournamentTeam


# =============================================================================
# Custom Exceptions
# =============================================================================

class MemorialServiceError(Exception):
    """Base exception for memorial service errors."""
    pass


class FileValidationError(MemorialServiceError):
    """Raised when file validation fails."""
    pass


class SubmissionLockedError(MemorialServiceError):
    """Raised when attempting to modify locked submission."""
    pass


class FreezeExistsError(MemorialServiceError):
    """Raised when freeze already exists for moot problem."""
    pass


class EvaluationBlockedError(MemorialServiceError):
    """Raised when evaluation is blocked by freeze."""
    pass


# =============================================================================
# Constants
# =============================================================================

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
ALLOWED_EXTENSIONS = {'.pdf'}
ALLOWED_CONTENT_TYPES = {'application/pdf'}

QUANTIZER_2DP = Decimal("0.01")


# =============================================================================
# File Security Functions (Streaming)
# =============================================================================

def validate_filename_strict(filename: str) -> None:
    """
    Strict filename validation.
    
    Security:
    - Extracts true extension (last segment only)
    - Rejects files without extension
    - Only allows .pdf
    """
    # Extract true extension using rsplit (handles double extensions safely)
    parts = filename.rsplit(".", 1)
    if len(parts) != 2:
        raise FileValidationError("File must have extension")
    
    ext = parts[1].lower()
    if ext != "pdf":
        raise FileValidationError(f"Only PDF files allowed. Got: .{ext}")
    
    # Check for dangerous characters
    dangerous = ['<', '>', ':', '"', '|', '?', '*', '..', '//', '\\', '\x00']
    for char in dangerous:
        if char in filename:
            raise FileValidationError(f"Invalid character in filename: {repr(char)}")


async def stream_pdf_upload(
    file,
    destination_path: str,
    max_size: int = MAX_FILE_SIZE
) -> Tuple[str, int]:
    """
    Stream file upload with security validation.
    
    Elite Hardening:
    - No full file in memory
    - Magic byte validation (PDF signature)
    - Streaming SHA256 hash computation
    - Real-time size enforcement
    
    Args:
        file: FastAPI UploadFile
        destination_path: Where to save the file
        max_size: Maximum file size in bytes
        
    Returns:
        Tuple of (file_hash, file_size)
        
    Raises:
        HTTPException: If validation fails
    """
    hasher = hashlib.sha256()
    total_size = 0
    first_chunk_checked = False
    chunk_size = 8192  # 8KB chunks
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
    
    with open(destination_path, "wb") as f:
        while chunk := await file.read(chunk_size):
            total_size += len(chunk)
            
            # Real-time size enforcement
            if total_size > max_size:
                # Clean up partial file
                f.close()
                os.remove(destination_path)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {max_size // (1024*1024)}MB limit"
                )
            
            # Magic byte validation (first chunk only)
            if not first_chunk_checked:
                if not chunk.startswith(b"%PDF-"):
                    # Clean up partial file
                    f.close()
                    os.remove(destination_path)
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid PDF signature. File must start with %PDF-"
                    )
                first_chunk_checked = True
            
            # Update hash and write
            hasher.update(chunk)
            f.write(chunk)
    
    return hasher.hexdigest(), total_size


def validate_file_security_legacy(
    filename: str,
    content_type: str,
    file_size: int
) -> None:
    """
    DEPRECATED: Legacy validation for backward compatibility.
    Use validate_filename_strict() + stream_pdf_upload() instead.
    """
    # Check file size
    if file_size > MAX_FILE_SIZE:
        raise FileValidationError(
            f"File size {file_size} exceeds maximum {MAX_FILE_SIZE} bytes (20MB)"
        )
    
    if file_size == 0:
        raise FileValidationError("File cannot be empty")
    
    # Check extension
    filename_lower = filename.lower()
    
    # Reject double extensions (security risk)
    if filename_lower.count('.') > 1:
        raise FileValidationError("Double extensions not allowed for security")
    
    # Must end with .pdf
    if not any(filename_lower.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise FileValidationError(f"Only PDF files allowed. Got: {filename}")
    
    # Validate content type
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise FileValidationError(
            f"Invalid content type: {content_type}. Only application/pdf allowed."
        )
    
    # Check for dangerous characters in filename
    dangerous = ['<', '>', ':', '"', '|', '?', '*', '..', '//', '\\', '\x00']
    for char in dangerous:
        if char in filename:
            raise FileValidationError(f"Invalid character in filename: {repr(char)}")


# Alias for backward compatibility
validate_file_security = validate_file_security_legacy


def store_file_securely(
    file_bytes: bytes,
    original_filename: str,
    upload_dir: str
) -> Tuple[str, str, int]:
    """
    Store file with security measures.
    
    Returns:
        Tuple of (file_path, internal_filename, file_hash)
    """
    # Compute hash before storage
    file_hash = compute_file_hash(file_bytes)
    
    # Generate secure internal filename
    internal_filename = generate_internal_filename()
    
    # Create full path
    file_path = os.path.join(upload_dir, internal_filename)
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Write file
    with open(file_path, 'wb') as f:
        f.write(file_bytes)
    
    return file_path, internal_filename, file_hash


def delete_file_if_exists(file_path: str) -> None:
    """Delete file if it exists (for cleanup on errors)."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass  # Best effort cleanup


# =============================================================================
# Memorial Submission Functions
# =============================================================================

async def submit_memorial(
    tournament_team_id: int,
    moot_problem_id: int,
    side: MemorialSide,
    file_bytes: bytes,
    original_filename: str,
    content_type: str,
    deadline_at: datetime,
    upload_dir: str,
    db: AsyncSession,
    submitted_by: int
) -> MemorialSubmission:
    """
    Submit a memorial with full security validation.
    
    Elite Hardening:
    - File hash computed and stored
    - File size validated
    - Only PDF allowed
    - Late status computed automatically
    - Resubmission number incremented if exists
    
    Args:
        tournament_team_id: ID of submitting team
        moot_problem_id: ID of moot problem
        side: PETITIONER or RESPONDENT
        file_bytes: Raw file bytes
        original_filename: Original filename from user
        content_type: MIME type
        deadline_at: Submission deadline
        upload_dir: Directory for file storage
        db: Database session
        submitted_by: User ID submitting
        
    Returns:
        Created MemorialSubmission
        
    Raises:
        FileValidationError: If file validation fails
        SubmissionLockedError: If previous submission is locked
    """
    file_size = len(file_bytes)
    
    # Validate file security
    validate_file_security(original_filename, content_type, file_size)
    
    # Check for existing submission
    result = await db.execute(
        select(MemorialSubmission).where(
            and_(
                MemorialSubmission.tournament_team_id == tournament_team_id,
                MemorialSubmission.moot_problem_id == moot_problem_id,
                MemorialSubmission.side == side
            )
        ).order_by(MemorialSubmission.resubmission_number.desc())
    )
    existing = result.scalar_one_or_none()
    
    # Determine resubmission number
    if existing:
        if existing.is_locked:
            raise SubmissionLockedError(
                "Cannot resubmit: previous submission is locked"
            )
        resubmission_number = existing.resubmission_number + 1
        
        # Delete old file (best effort)
        delete_file_if_exists(existing.file_path)
    else:
        resubmission_number = 1
    
    # Store file securely
    file_path, internal_filename, file_hash = store_file_securely(
        file_bytes, original_filename, upload_dir
    )
    
    # Compute late status
    submitted_at = datetime.utcnow()
    is_late = submitted_at > deadline_at
    
    # Create submission record
    submission = MemorialSubmission(
        tournament_team_id=tournament_team_id,
        moot_problem_id=moot_problem_id,
        side=side,
        file_path=file_path,
        file_hash_sha256=file_hash,
        file_size_bytes=file_size,
        original_filename=original_filename,
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
    
    return submission


async def lock_memorial_submission(
    submission_id: int,
    db: AsyncSession
) -> MemorialSubmission:
    """
    Lock a memorial submission to prevent further modifications.
    
    Args:
        submission_id: ID of submission to lock
        db: Database session
        
    Returns:
        Locked MemorialSubmission
    """
    result = await db.execute(
        select(MemorialSubmission).where(MemorialSubmission.id == submission_id)
    )
    submission = result.scalar_one_or_none()
    
    if not submission:
        raise MemorialServiceError(f"Submission {submission_id} not found")
    
    submission.is_locked = True
    await db.flush()
    
    return submission


# =============================================================================
# Memorial Evaluation Functions
# =============================================================================

async def create_memorial_evaluation(
    memorial_submission_id: int,
    judge_id: int,
    legal_analysis_score: Decimal,
    research_depth_score: Decimal,
    clarity_score: Decimal,
    citation_format_score: Decimal,
    rubric_version_id: Optional[int] = None,
    db: AsyncSession = None
) -> MemorialEvaluation:
    """
    Create a memorial evaluation with deterministic scoring.
    
    Elite Hardening:
    - All scores use Decimal
    - Total computed server-side (not trusted from client)
    - Evaluation hash computed for integrity
    - Freeze check prevents post-freeze evaluations
    - No float usage
    
    Total Formula:
        total = legal + research + clarity + citation
    
    Hash Formula:
        SHA256("legal|research|clarity|citation|total")
    
    Args:
        memorial_submission_id: ID of submission being evaluated
        judge_id: ID of evaluating judge
        legal_analysis_score: Legal analysis score (0-100)
        research_depth_score: Research depth score (0-100)
        clarity_score: Clarity score (0-100)
        citation_format_score: Citation format score (0-100)
        rubric_version_id: Optional AI rubric version
        db: Database session
        
    Returns:
        Created MemorialEvaluation
        
    Raises:
        EvaluationBlockedError: If freeze exists for this problem
    """
    # Get submission
    result = await db.execute(
        select(MemorialSubmission).where(
            MemorialSubmission.id == memorial_submission_id
        )
    )
    submission = result.scalar_one_or_none()
    
    if not submission:
        raise MemorialServiceError(
            f"Submission {memorial_submission_id} not found"
        )
    
    # Check for freeze
    result = await db.execute(
        select(MemorialScoreFreeze).where(
            MemorialScoreFreeze.moot_problem_id == submission.moot_problem_id
        )
    )
    freeze = result.scalar_one_or_none()
    
    if freeze:
        raise EvaluationBlockedError(
            f"Evaluations blocked: scores frozen at {freeze.frozen_at}"
        )
    
    # Convert to Decimal and quantize
    legal = Decimal(str(legal_analysis_score)).quantize(QUANTIZER_2DP, rounding=ROUND_HALF_UP)
    research = Decimal(str(research_depth_score)).quantize(QUANTIZER_2DP, rounding=ROUND_HALF_UP)
    clarity = Decimal(str(clarity_score)).quantize(QUANTIZER_2DP, rounding=ROUND_HALF_UP)
    citation = Decimal(str(citation_format_score)).quantize(QUANTIZER_2DP, rounding=ROUND_HALF_UP)
    
    # Compute total server-side (never trust client)
    total = (legal + research + clarity + citation).quantize(QUANTIZER_2DP, rounding=ROUND_HALF_UP)
    
    # Create evaluation object
    evaluation = MemorialEvaluation(
        memorial_submission_id=memorial_submission_id,
        judge_id=judge_id,
        rubric_version_id=rubric_version_id,
        legal_analysis_score=legal,
        research_depth_score=research,
        clarity_score=clarity,
        citation_format_score=citation,
        total_score=total,
        evaluation_hash="",  # Will be computed next
        evaluated_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    
    # Compute hash
    evaluation.evaluation_hash = evaluation.compute_evaluation_hash()
    
    db.add(evaluation)
    await db.flush()
    
    return evaluation


async def verify_evaluation_integrity(
    evaluation_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Verify the integrity of a memorial evaluation.
    
    Args:
        evaluation_id: ID of evaluation to verify
        db: Database session
        
    Returns:
        Verification result dictionary
    """
    result = await db.execute(
        select(MemorialEvaluation).where(MemorialEvaluation.id == evaluation_id)
    )
    evaluation = result.scalar_one_or_none()
    
    if not evaluation:
        return {
            "evaluation_id": evaluation_id,
            "found": False,
            "valid": False,
            "error": "Evaluation not found"
        }
    
    is_valid = evaluation.verify_hash()
    
    return {
        "evaluation_id": evaluation_id,
        "found": True,
        "valid": is_valid,
        "stored_hash": evaluation.evaluation_hash,
        "computed_hash": evaluation.compute_evaluation_hash(),
        "scores": {
            "legal_analysis": str(evaluation.legal_analysis_score),
            "research_depth": str(evaluation.research_depth_score),
            "clarity": str(evaluation.clarity_score),
            "citation_format": str(evaluation.citation_format_score),
            "total": str(evaluation.total_score)
        }
    }


# =============================================================================
# Memorial Score Freeze Functions
# =============================================================================

async def freeze_memorial_scores(
    moot_problem_id: int,
    frozen_by: int,
    db: AsyncSession
) -> MemorialScoreFreeze:
    """
    Freeze all memorial scores for a moot problem.
    
    Elite Hardening:
    - SERIALIZABLE isolation for atomic freeze
    - Collects all evaluation hashes
    - Computes deterministic checksum
    - Blocks future evaluations
    - Immutable after creation
    
    Freeze Process:
    1. Set SERIALIZABLE isolation
    2. Collect all memorial submissions for problem
    3. Collect all evaluations for those submissions
    4. Sort evaluation hashes by submission_id
    5. Compute checksum: SHA256(sorted_hashes.joined)
    6. Create freeze record
    
    Args:
        moot_problem_id: ID of moot problem to freeze
        frozen_by: User ID applying freeze
        db: Database session
        
    Returns:
        Created MemorialScoreFreeze
        
    Raises:
        FreezeExistsError: If freeze already exists
    """
    # Set SERIALIZABLE isolation
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    
    # Check for existing freeze
    result = await db.execute(
        select(MemorialScoreFreeze).where(
            MemorialScoreFreeze.moot_problem_id == moot_problem_id
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        raise FreezeExistsError(
            f"Freeze already exists for moot problem {moot_problem_id}"
        )
    
    # Get all submissions for this problem
    result = await db.execute(
        select(MemorialSubmission.id).where(
            MemorialSubmission.moot_problem_id == moot_problem_id
        )
    )
    submission_ids = [row[0] for row in result.all()]
    
    if not submission_ids:
        raise MemorialServiceError(
            f"No memorial submissions found for moot problem {moot_problem_id}"
        )
    
    # Get all evaluations for these submissions
    result = await db.execute(
        select(
            MemorialEvaluation.memorial_submission_id,
            MemorialEvaluation.evaluation_hash
        ).where(
            MemorialEvaluation.memorial_submission_id.in_(submission_ids)
        ).order_by(
            MemorialEvaluation.memorial_submission_id.asc()
        )
    )
    evaluations = result.all()
    
    if not evaluations:
        raise MemorialServiceError(
            f"No evaluations found for moot problem {moot_problem_id}"
        )
    
    # Collect hashes in deterministic order (sorted by submission_id)
    evaluation_hashes = [eval_hash for _, eval_hash in evaluations]
    
    # Build immutable snapshot for tamper detection
    evaluation_snapshot = [
        {
            "evaluation_id": eval_id,
            "hash": eval_hash
        }
        for eval_id, eval_hash in evaluations
    ]
    
    # Compute freeze checksum
    freeze = MemorialScoreFreeze(
        moot_problem_id=moot_problem_id,
        frozen_at=datetime.utcnow(),
        frozen_by=frozen_by,
        checksum="",  # Will compute
        is_final=True,
        total_evaluations=len(evaluations),
        evaluation_snapshot_json=evaluation_snapshot,
        created_at=datetime.utcnow()
    )
    
    freeze.checksum = freeze.compute_freeze_checksum(evaluation_hashes)
    
    db.add(freeze)
    
    # Lock all submissions
    for submission_id in submission_ids:
        await lock_memorial_submission(submission_id, db)
    
    await db.flush()
    
    return freeze


async def verify_freeze_integrity(
    freeze_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Verify the integrity of a memorial score freeze.
    
    Checks stored snapshot against current evaluation data to detect tampering.
    
    Args:
        freeze_id: ID of freeze to verify
        db: Database session
        
    Returns:
        Verification result dictionary
    """
    result = await db.execute(
        select(MemorialScoreFreeze).where(MemorialScoreFreeze.id == freeze_id)
    )
    freeze = result.scalar_one_or_none()
    
    if not freeze:
        return {
            "freeze_id": freeze_id,
            "found": False,
            "valid": False,
            "error": "Freeze not found"
        }
    
    # Get all evaluations for this problem
    result = await db.execute(
        select(MemorialSubmission.id).where(
            MemorialSubmission.moot_problem_id == freeze.moot_problem_id
        )
    )
    submission_ids = [row[0] for row in result.all()]
    
    # Get all current evaluations with their hashes
    result = await db.execute(
        select(MemorialEvaluation.id, MemorialEvaluation.evaluation_hash)
        .where(
            MemorialEvaluation.memorial_submission_id.in_(submission_ids)
        )
        .order_by(MemorialEvaluation.memorial_submission_id.asc())
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
        "freeze_id": freeze_id,
        "moot_problem_id": freeze.moot_problem_id,
        "found": True,
        "valid": is_valid,
        "stored_checksum": freeze.checksum,
        "total_evaluations": freeze.total_evaluations,
        "frozen_at": freeze.frozen_at.isoformat() if freeze.frozen_at else None,
        "tampered_evaluations": tampered_evaluations if tampered_evaluations else None,
        "new_evaluations_added": new_evaluations if new_evaluations else None,
        "tamper_detected": len(tampered_evaluations) > 0 or len(new_evaluations) > 0
    }


# =============================================================================
# Query Functions (Institution-Scoped)
# =============================================================================

async def get_memorials_by_team(
    tournament_team_id: int,
    institution_id: int,
    db: AsyncSession
) -> List[MemorialSubmission]:
    """
    Get all memorial submissions for a team (institution-scoped).
    
    Args:
        tournament_team_id: ID of the team
        institution_id: Institution ID for scoping (security)
        db: Database session
        
    Returns:
        List of MemorialSubmission objects
    """
    result = await db.execute(
        select(MemorialSubmission)
        .join(TournamentTeam, MemorialSubmission.tournament_team_id == TournamentTeam.id)
        .where(
            and_(
                MemorialSubmission.tournament_team_id == tournament_team_id,
                TournamentTeam.institution_id == institution_id
            )
        )
        .order_by(MemorialSubmission.created_at.desc())
    )
    return list(result.scalars().all())


async def get_memorial_by_id(
    submission_id: int,
    institution_id: int,
    db: AsyncSession
) -> Optional[MemorialSubmission]:
    """
    Get memorial submission by ID (institution-scoped).
    
    Returns None if not found or if user doesn't have access to this institution.
    """
    result = await db.execute(
        select(MemorialSubmission)
        .join(TournamentTeam, MemorialSubmission.tournament_team_id == TournamentTeam.id)
        .where(
            and_(
                MemorialSubmission.id == submission_id,
                TournamentTeam.institution_id == institution_id
            )
        )
    )
    return result.scalar_one_or_none()


async def get_evaluations_by_submission(
    memorial_submission_id: int,
    institution_id: int,
    db: AsyncSession
) -> List[MemorialEvaluation]:
    """
    Get all evaluations for a memorial submission (institution-scoped).
    """
    result = await db.execute(
        select(MemorialEvaluation)
        .join(MemorialSubmission, MemorialEvaluation.memorial_submission_id == MemorialSubmission.id)
        .join(TournamentTeam, MemorialSubmission.tournament_team_id == TournamentTeam.id)
        .where(
            and_(
                MemorialEvaluation.memorial_submission_id == memorial_submission_id,
                TournamentTeam.institution_id == institution_id
            )
        )
        .order_by(MemorialEvaluation.evaluated_at.desc())
    )
    return list(result.scalars().all())


async def get_clarifications_by_problem(
    moot_problem_id: int,
    db: AsyncSession
) -> List[MootClarification]:
    """Get all clarifications for a moot problem in release order."""
    result = await db.execute(
        select(MootClarification)
        .where(MootClarification.moot_problem_id == moot_problem_id)
        .order_by(MootClarification.release_sequence.asc())
    )
    return list(result.scalars().all())


async def get_next_clarification_sequence(
    moot_problem_id: int,
    db: AsyncSession
) -> int:
    """Get the next sequence number for a clarification."""
    result = await db.execute(
        select(func.max(MootClarification.release_sequence))
        .where(MootClarification.moot_problem_id == moot_problem_id)
    )
    max_seq = result.scalar() or 0
    return max_seq + 1


async def check_freeze_exists(
    moot_problem_id: int,
    db: AsyncSession
) -> Optional[MemorialScoreFreeze]:
    """Check if a freeze exists for a moot problem."""
    result = await db.execute(
        select(MemorialScoreFreeze)
        .where(MemorialScoreFreeze.moot_problem_id == moot_problem_id)
    )
    return result.scalar_one_or_none()
