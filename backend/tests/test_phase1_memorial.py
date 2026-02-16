"""
Phase 1 — Memorial Infrastructure Test Suite

Comprehensive tests for:
- File upload hash integrity
- Late submission detection
- Double submission increment
- Lock enforcement
- Evaluation hash determinism
- Freeze prevention
- Blind review mode
- Checksum verification
- No forbidden patterns (float, random, datetime.now, hash)
"""
import ast
import hashlib
import inspect
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Tuple

import pytest
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.moot_problem import (
    MootProblem, MootClarification, MemorialSubmission,
    MemorialEvaluation, MemorialScoreFreeze, MemorialSide,
    generate_internal_filename, compute_file_hash
)
from backend.orm.user import User, UserRole
from backend.orm.national_network import TournamentTeam, NationalTournament
from backend.orm.institutional_governance import Institution
from backend.services.memorial_service import (
    submit_memorial, create_memorial_evaluation, freeze_memorial_scores,
    verify_evaluation_integrity, verify_freeze_integrity,
    validate_file_security, store_file_securely, FileValidationError,
    SubmissionLockedError, EvaluationBlockedError, FreezeExistsError,
    MAX_FILE_SIZE, QUANTIZER_2DP
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def institution(db: AsyncSession) -> Institution:
    """Create test institution."""
    inst = Institution(
        name="Test Law College",
        code="TLC001",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(inst)
    await db.flush()
    return inst


@pytest.fixture
async def user(db: AsyncSession, institution: Institution) -> User:
    """Create test user."""
    user = User(
        email="test@lawcollege.edu",
        full_name="Test User",
        password_hash="hashed_password",
        role=UserRole.ADMIN,
        institution_id=institution.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def tournament(db: AsyncSession, institution: Institution) -> NationalTournament:
    """Create test tournament."""
    tournament = NationalTournament(
        name="Test Moot Tournament",
        host_institution_id=institution.id,
        start_date=datetime.utcnow() + timedelta(days=30),
        end_date=datetime.utcnow() + timedelta(days=35),
        registration_deadline=datetime.utcnow() + timedelta(days=15),
        status="draft",
        created_at=datetime.utcnow()
    )
    db.add(tournament)
    await db.flush()
    return tournament


@pytest.fixture
async def tournament_team(db: AsyncSession, tournament: NationalTournament, user: User) -> TournamentTeam:
    """Create test tournament team."""
    team = TournamentTeam(
        tournament_id=tournament.id,
        institution_id=user.institution_id,
        team_code="TEST-001",
        team_name="Test Team",
        registered_by=user.id,
        registration_status="confirmed",
        created_at=datetime.utcnow()
    )
    db.add(team)
    await db.flush()
    return team


@pytest.fixture
async def moot_problem(db: AsyncSession, institution: Institution, user: User, tournament: NationalTournament) -> MootProblem:
    """Create test moot problem."""
    problem = MootProblem(
        institution_id=institution.id,
        tournament_id=tournament.id,
        title="Test Moot Problem",
        description="This is a test moot problem for Phase 1 testing.",
        official_release_at=datetime.utcnow(),
        version_number=1,
        is_active=True,
        blind_review=True,
        created_by=user.id,
        created_at=datetime.utcnow()
    )
    db.add(problem)
    await db.flush()
    return problem


# =============================================================================
# Test: File Security
# =============================================================================

def test_compute_file_hash():
    """Test SHA256 file hash computation."""
    content = b"Test memorial content"
    hash1 = compute_file_hash(content)
    hash2 = compute_file_hash(content)
    
    assert len(hash1) == 64, "SHA256 hash must be 64 characters"
    assert hash1 == hash2, "Same content must produce same hash"
    assert hash1 == hashlib.sha256(content).hexdigest(), "Must match hashlib result"


def test_generate_internal_filename():
    """Test UUID-based filename generation."""
    filename1 = generate_internal_filename()
    filename2 = generate_internal_filename()
    
    assert filename1 != filename2, "Must generate unique filenames"
    assert filename1.endswith('.pdf'), "Must end with .pdf"
    assert len(filename1) == 36 + 4, "UUID (32 hex + 4 dashes) + .pdf"
    assert '/' not in filename1, "Must not contain path separators"
    assert '..' not in filename1, "Must not contain parent directory reference"


def test_validate_file_security_valid():
    """Test file validation with valid PDF."""
    validate_file_security(
        filename="memorial.pdf",
        content_type="application/pdf",
        file_size=1024 * 1024  # 1MB
    )
    # Should not raise


def test_validate_file_security_oversize():
    """Test file validation rejects oversized files."""
    with pytest.raises(FileValidationError, match="exceeds"):
        validate_file_security(
            filename="memorial.pdf",
            content_type="application/pdf",
            file_size=MAX_FILE_SIZE + 1
        )


def test_validate_file_security_empty():
    """Test file validation rejects empty files."""
    with pytest.raises(FileValidationError, match="empty"):
        validate_file_security(
            filename="memorial.pdf",
            content_type="application/pdf",
            file_size=0
        )


def test_validate_file_security_double_extension():
    """Test file validation rejects double extensions."""
    with pytest.raises(FileValidationError, match="Double extensions"):
        validate_file_security(
            filename="memorial.exe.pdf",
            content_type="application/pdf",
            file_size=1024
        )


def test_validate_file_security_non_pdf():
    """Test file validation rejects non-PDF files."""
    with pytest.raises(FileValidationError, match="Only PDF"):
        validate_file_security(
            filename="memorial.docx",
            content_type="application/vnd.openxmlformats",
            file_size=1024
        )


def test_validate_file_security_invalid_content_type():
    """Test file validation rejects invalid content type."""
    with pytest.raises(FileValidationError, match="Invalid content type"):
        validate_file_security(
            filename="memorial.pdf",
            content_type="text/html",
            file_size=1024
        )


def test_validate_file_security_dangerous_chars():
    """Test file validation rejects dangerous characters."""
    with pytest.raises(FileValidationError, match="Invalid character"):
        validate_file_security(
            filename="../etc/passwd.pdf",
            content_type="application/pdf",
            file_size=1024
        )


# =============================================================================
# Test: Memorial Submission
# =============================================================================

@pytest.mark.asyncio
async def test_submit_memorial_success(
    db: AsyncSession, tournament_team: TournamentTeam, moot_problem: MootProblem, user: User
):
    """Test successful memorial submission."""
    file_bytes = b"Test memorial content"
    deadline = datetime.utcnow() + timedelta(days=7)
    
    submission = await submit_memorial(
        tournament_team_id=tournament_team.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_bytes=file_bytes,
        original_filename="memorial.pdf",
        content_type="application/pdf",
        deadline_at=deadline,
        upload_dir="/tmp/test_uploads",
        db=db,
        submitted_by=user.id
    )
    
    assert submission.tournament_team_id == tournament_team.id
    assert submission.moot_problem_id == moot_problem.id
    assert submission.side == MemorialSide.PETITIONER
    assert submission.file_hash_sha256 == compute_file_hash(file_bytes)
    assert submission.file_size_bytes == len(file_bytes)
    assert submission.resubmission_number == 1
    assert submission.is_late == False
    assert submission.is_locked == False


@pytest.mark.asyncio
async def test_submit_memorial_late(
    db: AsyncSession, tournament_team: TournamentTeam, moot_problem: MootProblem, user: User
):
    """Test late memorial submission detection."""
    file_bytes = b"Late memorial content"
    deadline = datetime.utcnow() - timedelta(hours=1)  # Past deadline
    
    submission = await submit_memorial(
        tournament_team_id=tournament_team.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_bytes=file_bytes,
        original_filename="memorial.pdf",
        content_type="application/pdf",
        deadline_at=deadline,
        upload_dir="/tmp/test_uploads",
        db=db,
        submitted_by=user.id
    )
    
    assert submission.is_late == True, "Submission past deadline must be marked late"


@pytest.mark.asyncio
async def test_resubmission_increments_number(
    db: AsyncSession, tournament_team: TournamentTeam, moot_problem: MootProblem, user: User
):
    """Test resubmission increments resubmission_number."""
    file_bytes = b"Original memorial"
    deadline = datetime.utcnow() + timedelta(days=7)
    
    # First submission
    submission1 = await submit_memorial(
        tournament_team_id=tournament_team.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_bytes=file_bytes,
        original_filename="memorial.pdf",
        content_type="application/pdf",
        deadline_at=deadline,
        upload_dir="/tmp/test_uploads",
        db=db,
        submitted_by=user.id
    )
    assert submission1.resubmission_number == 1
    
    # Resubmit
    file_bytes2 = b"Updated memorial"
    submission2 = await submit_memorial(
        tournament_team_id=tournament_team.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_bytes=file_bytes2,
        original_filename="memorial_v2.pdf",
        content_type="application/pdf",
        deadline_at=deadline,
        upload_dir="/tmp/test_uploads",
        db=db,
        submitted_by=user.id
    )
    assert submission2.resubmission_number == 2


@pytest.mark.asyncio
async def test_cannot_resubmit_locked(
    db: AsyncSession, tournament_team: TournamentTeam, moot_problem: MootProblem, user: User
):
    """Test locked submission blocks resubmission."""
    file_bytes = b"Locked memorial"
    deadline = datetime.utcnow() + timedelta(days=7)
    
    # Create submission
    submission = await submit_memorial(
        tournament_team_id=tournament_team.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.RESPONDENT,
        file_bytes=file_bytes,
        original_filename="memorial.pdf",
        content_type="application/pdf",
        deadline_at=deadline,
        upload_dir="/tmp/test_uploads",
        db=db,
        submitted_by=user.id
    )
    
    # Lock it
    from backend.services.memorial_service import lock_memorial_submission
    await lock_memorial_submission(submission.id, db)
    
    # Try to resubmit
    with pytest.raises(SubmissionLockedError):
        await submit_memorial(
            tournament_team_id=tournament_team.id,
            moot_problem_id=moot_problem.id,
            side=MemorialSide.RESPONDENT,
            file_bytes=b"New content",
            original_filename="new.pdf",
            content_type="application/pdf",
            deadline_at=deadline,
            upload_dir="/tmp/test_uploads",
            db=db,
            submitted_by=user.id
        )


# =============================================================================
# Test: Memorial Evaluation
# =============================================================================

@pytest.mark.asyncio
async def test_create_evaluation_success(
    db: AsyncSession, tournament_team: TournamentTeam, moot_problem: MootProblem, user: User
):
    """Test successful memorial evaluation."""
    # Create submission first
    from backend.services.memorial_service import submit_memorial
    submission = await submit_memorial(
        tournament_team_id=tournament_team.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_bytes=b"Test content",
        original_filename="memorial.pdf",
        content_type="application/pdf",
        deadline_at=datetime.utcnow() + timedelta(days=7),
        upload_dir="/tmp/test_uploads",
        db=db,
        submitted_by=user.id
    )
    
    # Create evaluation
    evaluation = await create_memorial_evaluation(
        memorial_submission_id=submission.id,
        judge_id=user.id,
        legal_analysis_score=Decimal("85.50"),
        research_depth_score=Decimal("78.25"),
        clarity_score=Decimal("90.00"),
        citation_format_score=Decimal("82.75"),
        db=db
    )
    
    # Verify scores
    assert evaluation.legal_analysis_score == Decimal("85.50")
    assert evaluation.research_depth_score == Decimal("78.25")
    assert evaluation.clarity_score == Decimal("90.00")
    assert evaluation.citation_format_score == Decimal("82.75")
    
    # Verify total computed correctly
    expected_total = Decimal("85.50") + Decimal("78.25") + Decimal("90.00") + Decimal("82.75")
    assert evaluation.total_score == expected_total
    
    # Verify hash exists
    assert len(evaluation.evaluation_hash) == 64
    assert evaluation.verify_hash() == True


@pytest.mark.asyncio
async def test_evaluation_blocked_by_freeze(
    db: AsyncSession, tournament_team: TournamentTeam, moot_problem: MootProblem, user: User
):
    """Test evaluation blocked when scores frozen."""
    # Create submission
    from backend.services.memorial_service import submit_memorial
    submission = await submit_memorial(
        tournament_team_id=tournament_team.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_bytes=b"Test content",
        original_filename="memorial.pdf",
        content_type="application/pdf",
        deadline_at=datetime.utcnow() + timedelta(days=7),
        upload_dir="/tmp/test_uploads",
        db=db,
        submitted_by=user.id
    )
    
    # Create one evaluation
    await create_memorial_evaluation(
        memorial_submission_id=submission.id,
        judge_id=user.id,
        legal_analysis_score=Decimal("80.00"),
        research_depth_score=Decimal("80.00"),
        clarity_score=Decimal("80.00"),
        citation_format_score=Decimal("80.00"),
        db=db
    )
    
    # Freeze scores
    await freeze_memorial_scores(moot_problem.id, user.id, db)
    
    # Try to create another evaluation
    with pytest.raises(EvaluationBlockedError):
        await create_memorial_evaluation(
            memorial_submission_id=submission.id,
            judge_id=user.id,
            legal_analysis_score=Decimal("70.00"),
            research_depth_score=Decimal("70.00"),
            clarity_score=Decimal("70.00"),
            citation_format_score=Decimal("70.00"),
            db=db
        )


# =============================================================================
# Test: Score Freeze
# =============================================================================

@pytest.mark.asyncio
async def test_freeze_memorial_scores(
    db: AsyncSession, tournament_team: TournamentTeam, moot_problem: MootProblem, user: User
):
    """Test memorial score freeze."""
    # Create submission and evaluation
    from backend.services.memorial_service import submit_memorial
    submission = await submit_memorial(
        tournament_team_id=tournament_team.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_bytes=b"Test content",
        original_filename="memorial.pdf",
        content_type="application/pdf",
        deadline_at=datetime.utcnow() + timedelta(days=7),
        upload_dir="/tmp/test_uploads",
        db=db,
        submitted_by=user.id
    )
    
    await create_memorial_evaluation(
        memorial_submission_id=submission.id,
        judge_id=user.id,
        legal_analysis_score=Decimal("85.00"),
        research_depth_score=Decimal("85.00"),
        clarity_score=Decimal("85.00"),
        citation_format_score=Decimal("85.00"),
        db=db
    )
    
    # Freeze
    freeze = await freeze_memorial_scores(moot_problem.id, user.id, db)
    
    assert freeze.moot_problem_id == moot_problem.id
    assert freeze.frozen_by == user.id
    assert freeze.is_final == True
    assert freeze.total_evaluations == 1
    assert len(freeze.checksum) == 64
    
    # Verify submission is locked
    result = await db.execute(
        select(MemorialSubmission).where(MemorialSubmission.id == submission.id)
    )
    locked_submission = result.scalar_one()
    assert locked_submission.is_locked == True


@pytest.mark.asyncio
async def test_freeze_already_exists(
    db: AsyncSession, tournament_team: TournamentTeam, moot_problem: MootProblem, user: User
):
    """Test cannot create duplicate freeze."""
    # Create and freeze once
    from backend.services.memorial_service import submit_memorial
    submission = await submit_memorial(
        tournament_team_id=tournament_team.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_bytes=b"Test content",
        original_filename="memorial.pdf",
        content_type="application/pdf",
        deadline_at=datetime.utcnow() + timedelta(days=7),
        upload_dir="/tmp/test_uploads",
        db=db,
        submitted_by=user.id
    )
    
    await create_memorial_evaluation(
        memorial_submission_id=submission.id,
        judge_id=user.id,
        legal_analysis_score=Decimal("80.00"),
        research_depth_score=Decimal("80.00"),
        clarity_score=Decimal("80.00"),
        citation_format_score=Decimal("80.00"),
        db=db
    )
    
    await freeze_memorial_scores(moot_problem.id, user.id, db)
    
    # Try to freeze again
    with pytest.raises(FreezeExistsError):
        await freeze_memorial_scores(moot_problem.id, user.id, db)


# =============================================================================
# Test: Integrity Verification
# =============================================================================

@pytest.mark.asyncio
async def test_verify_evaluation_integrity(
    db: AsyncSession, tournament_team: TournamentTeam, moot_problem: MootProblem, user: User
):
    """Test evaluation integrity verification."""
    # Create submission and evaluation
    from backend.services.memorial_service import submit_memorial
    submission = await submit_memorial(
        tournament_team_id=tournament_team.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_bytes=b"Test content",
        original_filename="memorial.pdf",
        content_type="application/pdf",
        deadline_at=datetime.utcnow() + timedelta(days=7),
        upload_dir="/tmp/test_uploads",
        db=db,
        submitted_by=user.id
    )
    
    evaluation = await create_memorial_evaluation(
        memorial_submission_id=submission.id,
        judge_id=user.id,
        legal_analysis_score=Decimal("90.00"),
        research_depth_score=Decimal("85.00"),
        clarity_score=Decimal("88.00"),
        citation_format_score=Decimal("92.00"),
        db=db
    )
    
    # Verify
    result = await verify_evaluation_integrity(evaluation.id, db)
    
    assert result["found"] == True
    assert result["valid"] == True
    assert result["evaluation_id"] == evaluation.id


@pytest.mark.asyncio
async def test_verify_freeze_integrity(
    db: AsyncSession, tournament_team: TournamentTeam, moot_problem: MootProblem, user: User
):
    """Test freeze integrity verification."""
    # Create and freeze
    from backend.services.memorial_service import submit_memorial
    submission = await submit_memorial(
        tournament_team_id=tournament_team.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_bytes=b"Test content",
        original_filename="memorial.pdf",
        content_type="application/pdf",
        deadline_at=datetime.utcnow() + timedelta(days=7),
        upload_dir="/tmp/test_uploads",
        db=db,
        submitted_by=user.id
    )
    
    await create_memorial_evaluation(
        memorial_submission_id=submission.id,
        judge_id=user.id,
        legal_analysis_score=Decimal("85.00"),
        research_depth_score=Decimal("85.00"),
        clarity_score=Decimal("85.00"),
        citation_format_score=Decimal("85.00"),
        db=db
    )
    
    freeze = await freeze_memorial_scores(moot_problem.id, user.id, db)
    
    # Verify
    result = await verify_freeze_integrity(freeze.id, db)
    
    assert result["found"] == True
    assert result["valid"] == True
    assert result["freeze_id"] == freeze.id
    assert result["moot_problem_id"] == moot_problem.id


# =============================================================================
# Test: Blind Review Mode
# =============================================================================

@pytest.mark.asyncio
async def test_blind_review_hides_institution(
    db: AsyncSession, tournament_team: TournamentTeam, moot_problem: MootProblem, user: User
):
    """Test blind review mode hides sensitive data."""
    from backend.services.memorial_service import submit_memorial
    submission = await submit_memorial(
        tournament_team_id=tournament_team.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_bytes=b"Test content",
        original_filename="memorial.pdf",
        content_type="application/pdf",
        deadline_at=datetime.utcnow() + timedelta(days=7),
        upload_dir="/tmp/test_uploads",
        db=db,
        submitted_by=user.id
    )
    
    # Non-blind mode
    data_full = submission.to_dict(include_file_path=False, blind_mode=False)
    assert data_full["tournament_team_id"] == tournament_team.id
    
    # Blind mode
    data_blind = submission.to_dict(include_file_path=False, blind_mode=True)
    assert data_blind["tournament_team_id"] is None


# =============================================================================
# Test: Determinism Audit
# =============================================================================

def scan_for_forbidden_patterns(source_code: str, module_name: str) -> List[Tuple[str, str]]:
    """Scan source code for forbidden patterns."""
    violations = []
    
    tree = ast.parse(source_code)
    lines = source_code.split('\n')
    
    for node in ast.walk(tree):
        line_num = getattr(node, 'lineno', 0)
        line_content = lines[line_num - 1].strip() if 0 < line_num <= len(lines) else ""
        
        # Skip comments
        if line_content.startswith('#') or line_content.startswith('"""'):
            continue
        
        # Check for float()
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'float':
                if 'hashlib' not in line_content and 'sha256' not in line_content:
                    violations.append((module_name, f"float() usage: {line_content[:60]}"))
        
        # Check for random
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if (isinstance(node.func.value, ast.Name) and 
                    node.func.value.id in ['random', 'np', 'numpy']):
                    violations.append((module_name, f"random usage: {line_content[:60]}"))
        
        # Check for datetime.now()
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == 'now' and 'utcnow' not in line_content:
                    violations.append((module_name, f"datetime.now() usage: {line_content[:60]}"))
        
        # Check for hash() (not hashlib)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'hash':
                if 'hashlib' not in line_content:
                    violations.append((module_name, f"hash() usage: {line_content[:60]}"))
    
    return violations


def test_no_float_in_service():
    """Verify memorial_service.py has no float() usage."""
    import backend.services.memorial_service as svc
    source = inspect.getsource(svc)
    violations = scan_for_forbidden_patterns(source, 'memorial_service')
    
    float_violations = [v for v in violations if 'float()' in v[1]]
    assert len(float_violations) == 0, f"float() violations: {float_violations}"


def test_no_random_in_service():
    """Verify memorial_service.py has no random() usage."""
    import backend.services.memorial_service as svc
    source = inspect.getsource(svc)
    violations = scan_for_forbidden_patterns(source, 'memorial_service')
    
    random_violations = [v for v in violations if 'random' in v[1]]
    assert len(random_violations) == 0, f"random violations: {random_violations}"


def test_no_datetime_now_in_service():
    """Verify memorial_service.py uses utcnow() only."""
    import backend.services.memorial_service as svc
    source = inspect.getsource(svc)
    
    # Check for datetime.now() patterns
    assert 'datetime.now()' not in source, "Must not use datetime.now()"
    assert 'datetime.utcnow()' in source, "Must use datetime.utcnow()"


def test_no_python_hash_in_service():
    """Verify memorial_service.py uses hashlib only."""
    import backend.services.memorial_service as svc
    source = inspect.getsource(svc)
    
    # Should use hashlib.sha256, not built-in hash()
    assert 'hashlib.sha256' in source, "Must use hashlib.sha256"
    
    violations = scan_for_forbidden_patterns(source, 'memorial_service')
    hash_violations = [v for v in violations if 'hash()' in v[1]]
    assert len(hash_violations) == 0, f"hash() violations: {hash_violations}"


def test_decimal_columns_in_orm():
    """Verify all numeric columns use Numeric/Decimal."""
    # Check MemorialEvaluation scores
    score_columns = [
        'legal_analysis_score', 'research_depth_score',
        'clarity_score', 'citation_format_score', 'total_score'
    ]
    
    for col_name in score_columns:
        column = MemorialEvaluation.__table__.columns[col_name]
        assert str(column.type).startswith('NUMERIC'), \
            f"{col_name} must be NUMERIC, found {column.type}"


# =============================================================================
# Test: Clarification Immutability
# =============================================================================

@pytest.mark.asyncio
async def test_clarification_cannot_be_updated(
    db: AsyncSession, moot_problem: MootProblem, user: User
):
    """Test clarifications are immutable after creation."""
    clarification = MootClarification(
        moot_problem_id=moot_problem.id,
        question_text="What is the applicable law?",
        official_response="The law of the jurisdiction applies.",
        released_at=datetime.utcnow(),
        release_sequence=1,
        created_by=user.id,
        created_at=datetime.utcnow()
    )
    db.add(clarification)
    await db.flush()
    
    # Try to update (should raise)
    with pytest.raises(Exception):
        clarification.official_response = "Changed response"
        await db.flush()


# =============================================================================
# Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_full_memorial_workflow(
    db: AsyncSession, tournament_team: TournamentTeam, moot_problem: MootProblem, user: User
):
    """Test complete memorial workflow from submission to freeze."""
    from backend.services.memorial_service import submit_memorial
    
    # 1. Submit memorial
    submission = await submit_memorial(
        tournament_team_id=tournament_team.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_bytes=b"Complete memorial content",
        original_filename="final_memorial.pdf",
        content_type="application/pdf",
        deadline_at=datetime.utcnow() + timedelta(days=1),
        upload_dir="/tmp/test_uploads",
        db=db,
        submitted_by=user.id
    )
    
    # 2. Evaluate
    evaluation = await create_memorial_evaluation(
        memorial_submission_id=submission.id,
        judge_id=user.id,
        legal_analysis_score=Decimal("88.50"),
        research_depth_score=Decimal("85.25"),
        clarity_score=Decimal("90.00"),
        citation_format_score=Decimal("87.75"),
        db=db
    )
    
    # 3. Verify evaluation integrity
    eval_check = await verify_evaluation_integrity(evaluation.id, db)
    assert eval_check["valid"] == True
    
    # 4. Freeze
    freeze = await freeze_memorial_scores(moot_problem.id, user.id, db)
    assert freeze.is_final == True
    
    # 5. Verify freeze integrity
    freeze_check = await verify_freeze_integrity(freeze.id, db)
    assert freeze_check["valid"] == True
    
    # 6. Verify submission locked
    result = await db.execute(
        select(MemorialSubmission).where(MemorialSubmission.id == submission.id)
    )
    locked = result.scalar_one()
    assert locked.is_locked == True


def test_memorial_side_enum_values():
    """Test MemorialSide enum values."""
    assert MemorialSide.PETITIONER == "petitioner"
    assert MemorialSide.RESPONDENT == "respondent"
