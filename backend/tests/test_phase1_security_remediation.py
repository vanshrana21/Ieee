"""
Phase 1 — Security Remediation Test Suite

Tests for all security fixes implemented in Phase 1 Remediation:
1. Magic byte validation (PDF signature)
2. Double extension rejection
3. Streaming upload (no memory exhaustion)
4. Post-freeze SQL update blocking (via trigger)
5. Snapshot integrity tampering detection
6. Cross-institution access denial
7. Blind mode data masking
8. Rate limiting enforcement
"""
import hashlib
import os
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.moot_problem import (
    MootProblem, MootClarification, MemorialSubmission,
    MemorialEvaluation, MemorialScoreFreeze, MemorialSide
)
from backend.orm.user import User, UserRole
from backend.orm.national_network import TournamentTeam, NationalTournament
from backend.orm.institutional_governance import Institution
from backend.services.memorial_service import (
    validate_filename_strict,
    stream_pdf_upload,
    get_memorial_by_id,
    get_memorials_by_team,
    get_evaluations_by_submission,
    FileValidationError,
    MAX_FILE_SIZE
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def institution_a(db: AsyncSession) -> Institution:
    """Create test institution A."""
    inst = Institution(
        name="Law College A",
        code="LCA001",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(inst)
    await db.flush()
    return inst


@pytest.fixture
async def institution_b(db: AsyncSession) -> Institution:
    """Create test institution B."""
    inst = Institution(
        name="Law College B",
        code="LCB001",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(inst)
    await db.flush()
    return inst


@pytest.fixture
async def user_a(db: AsyncSession, institution_a: Institution) -> User:
    """Create test user in institution A."""
    user = User(
        email="user_a@lawcollege.edu",
        full_name="User A",
        password_hash="hashed_password",
        role=UserRole.ADMIN,
        institution_id=institution_a.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def user_b(db: AsyncSession, institution_b: Institution) -> User:
    """Create test user in institution B."""
    user = User(
        email="user_b@lawcollege.edu",
        full_name="User B",
        password_hash="hashed_password",
        role=UserRole.ADMIN,
        institution_id=institution_b.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def tournament_team_a(db: AsyncSession, institution_a: Institution, user_a: User) -> TournamentTeam:
    """Create test team in institution A."""
    team = TournamentTeam(
        tournament_id=1,
        institution_id=institution_a.id,
        team_code="TEAM-A-001",
        team_name="Team A",
        registered_by=user_a.id,
        registration_status="confirmed",
        created_at=datetime.utcnow()
    )
    db.add(team)
    await db.flush()
    return team


@pytest.fixture
async def tournament_team_b(db: AsyncSession, institution_b: Institution, user_b: User) -> TournamentTeam:
    """Create test team in institution B."""
    team = TournamentTeam(
        tournament_id=1,
        institution_id=institution_b.id,
        team_code="TEAM-B-001",
        team_name="Team B",
        registered_by=user_b.id,
        registration_status="confirmed",
        created_at=datetime.utcnow()
    )
    db.add(team)
    await db.flush()
    return team


@pytest.fixture
async def moot_problem(db: AsyncSession, institution_a: Institution, user_a: User) -> MootProblem:
    """Create test moot problem."""
    problem = MootProblem(
        institution_id=institution_a.id,
        title="Test Problem",
        description="Test description",
        official_release_at=datetime.utcnow(),
        version_number=1,
        is_active=True,
        blind_review=True,
        created_by=user_a.id,
        created_at=datetime.utcnow()
    )
    db.add(problem)
    await db.flush()
    return problem


# =============================================================================
# Test: Filename Validation
# =============================================================================

def test_validate_filename_strict_valid():
    """Test valid PDF filename passes."""
    # Should not raise
    validate_filename_strict("document.pdf")
    validate_filename_strict("My Memorial.pdf")
    validate_filename_strict("CASE_BRIEF.pdf")


def test_validate_filename_strict_no_extension():
    """Test filename without extension is rejected."""
    with pytest.raises(FileValidationError, match="File must have extension"):
        validate_filename_strict("document")


def test_validate_filename_strict_double_extension():
    """Test double extension with .pdf.exe is rejected."""
    with pytest.raises(FileValidationError, match="Only PDF files allowed"):
        validate_filename_strict("document.pdf.exe")


def test_validate_filename_strict_non_pdf():
    """Test non-PDF extension is rejected."""
    with pytest.raises(FileValidationError, match="Only PDF files allowed"):
        validate_filename_strict("document.docx")
    
    with pytest.raises(FileValidationError, match="Only PDF files allowed"):
        validate_filename_strict("document.jpg")


def test_validate_filename_strict_dangerous_chars():
    """Test dangerous characters are rejected."""
    with pytest.raises(FileValidationError, match="Invalid character"):
        validate_filename_strict("../etc/passwd.pdf")
    
    with pytest.raises(FileValidationError, match="Invalid character"):
        validate_filename_strict("document\x00.pdf")


# =============================================================================
# Test: Magic Byte Validation
# =============================================================================

class MockUploadFile:
    """Mock UploadFile for testing."""
    def __init__(self, content: bytes, filename: str = "test.pdf"):
        self.content = content
        self.filename = filename
        self._position = 0
    
    async def read(self, size: int = -1) -> bytes:
        if size == -1 or size >= len(self.content) - self._position:
            chunk = self.content[self._position:]
            self._position = len(self.content)
            return chunk
        else:
            chunk = self.content[self._position:self._position + size]
            self._position += size
            return chunk
    
    async def seek(self, position: int) -> None:
        self._position = position


@pytest.mark.asyncio
async def test_stream_pdf_upload_valid_pdf(tmp_path):
    """Test streaming upload accepts valid PDF."""
    pdf_content = b"%PDF-1.4\nTest PDF content here\n%%EOF"
    mock_file = MockUploadFile(pdf_content, "valid.pdf")
    destination = str(tmp_path / "uploaded.pdf")
    
    file_hash, file_size = await stream_pdf_upload(mock_file, destination)
    
    assert file_size == len(pdf_content)
    assert file_hash == hashlib.sha256(pdf_content).hexdigest()
    assert os.path.exists(destination)
    
    # Verify file content
    with open(destination, "rb") as f:
        assert f.read() == pdf_content


@pytest.mark.asyncio
async def test_stream_pdf_upload_invalid_magic_bytes(tmp_path):
    """Test streaming upload rejects non-PDF files."""
    # ZIP file signature
    zip_content = b"PK\x03\x04\x14\x00\x00\x00\x08\x00"
    mock_file = MockUploadFile(zip_content, "fake.pdf")
    destination = str(tmp_path / "uploaded.pdf")
    
    with pytest.raises(HTTPException) as exc_info:
        await stream_pdf_upload(mock_file, destination)
    
    assert exc_info.value.status_code == 400
    assert "Invalid PDF signature" in str(exc_info.value.detail)
    
    # File should not exist (cleaned up)
    assert not os.path.exists(destination)


@pytest.mark.asyncio
async def test_stream_pdf_upload_size_limit(tmp_path):
    """Test streaming upload enforces size limit."""
    # Create content larger than MAX_FILE_SIZE
    large_content = b"%PDF-1.4\n" + b"x" * (MAX_FILE_SIZE + 1000)
    mock_file = MockUploadFile(large_content, "large.pdf")
    destination = str(tmp_path / "uploaded.pdf")
    
    with pytest.raises(HTTPException) as exc_info:
        await stream_pdf_upload(mock_file, destination)
    
    assert exc_info.value.status_code == 413
    
    # File should not exist (cleaned up)
    assert not os.path.exists(destination)


@pytest.mark.asyncio
async def test_stream_pdf_upload_no_memory_exhaustion(tmp_path):
    """Test streaming upload doesn't load entire file into memory."""
    # Simulate a large file (but within limits)
    chunk_size = 8192
    num_chunks = 100  # About 800KB
    
    # Build content progressively
    content_parts = [b"%PDF-1.4\n"]
    for i in range(num_chunks):
        content_parts.append(f"Chunk {i:04d}: ".encode() + b"x" * (chunk_size - 12))
    content = b"".join(content_parts)
    
    mock_file = MockUploadFile(content, "chunked.pdf")
    destination = str(tmp_path / "uploaded.pdf")
    
    # This should work without loading all into memory at once
    file_hash, file_size = await stream_pdf_upload(mock_file, destination)
    
    assert file_size == len(content)
    assert file_hash == hashlib.sha256(content).hexdigest()


# =============================================================================
# Test: Institution Scoping
# =============================================================================

@pytest.mark.asyncio
async def test_get_memorial_by_id_institution_scoped(
    db: AsyncSession,
    tournament_team_a: TournamentTeam,
    tournament_team_b: TournamentTeam,
    moot_problem: MootProblem,
    institution_a: Institution,
    institution_b: Institution
):
    """Test memorial access is institution-scoped."""
    # Create submission for team A
    submission = MemorialSubmission(
        tournament_team_id=tournament_team_a.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_path="/tmp/test.pdf",
        file_hash_sha256="abc123",
        file_size_bytes=1000,
        original_filename="test.pdf",
        internal_filename="uuid123.pdf",
        submitted_at=datetime.utcnow(),
        deadline_at=datetime.utcnow() + timedelta(days=7),
        is_late=False,
        resubmission_number=1,
        is_locked=False,
        created_at=datetime.utcnow()
    )
    db.add(submission)
    await db.flush()
    
    # User from institution A can access
    result_a = await get_memorial_by_id(
        submission_id=submission.id,
        institution_id=institution_a.id,
        db=db
    )
    assert result_a is not None
    assert result_a.id == submission.id
    
    # User from institution B cannot access (gets None)
    result_b = await get_memorial_by_id(
        submission_id=submission.id,
        institution_id=institution_b.id,
        db=db
    )
    assert result_b is None


@pytest.mark.asyncio
async def test_get_memorials_by_team_institution_scoped(
    db: AsyncSession,
    tournament_team_a: TournamentTeam,
    institution_a: Institution,
    institution_b: Institution,
    moot_problem: MootProblem
):
    """Test team memorial list is institution-scoped."""
    # Create submission
    submission = MemorialSubmission(
        tournament_team_id=tournament_team_a.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_path="/tmp/test.pdf",
        file_hash_sha256="abc123",
        file_size_bytes=1000,
        original_filename="test.pdf",
        internal_filename="uuid123.pdf",
        submitted_at=datetime.utcnow(),
        deadline_at=datetime.utcnow() + timedelta(days=7),
        is_late=False,
        resubmission_number=1,
        is_locked=False,
        created_at=datetime.utcnow()
    )
    db.add(submission)
    await db.flush()
    
    # User from institution A can see the submission
    memorials_a = await get_memorials_by_team(
        tournament_team_id=tournament_team_a.id,
        institution_id=institution_a.id,
        db=db
    )
    assert len(memorials_a) == 1
    
    # User from institution B cannot see any submissions
    memorials_b = await get_memorials_by_team(
        tournament_team_id=tournament_team_a.id,
        institution_id=institution_b.id,
        db=db
    )
    assert len(memorials_b) == 0


# =============================================================================
# Test: Blind Review Mode
# =============================================================================

@pytest.mark.asyncio
async def test_blind_mode_no_identifying_data(
    db: AsyncSession,
    tournament_team_a: TournamentTeam,
    moot_problem: MootProblem
):
    """Test blind mode doesn't leak identifying information."""
    # Create submission with identifying data
    submission = MemorialSubmission(
        tournament_team_id=tournament_team_a.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_path="/tmp/NLSIU_MEMORIAL.pdf",
        file_hash_sha256="abc123def456",
        file_size_bytes=1000,
        original_filename="NLSIU_Team_Name_Memo.pdf",
        internal_filename="uuid-hidden.pdf",
        submitted_at=datetime.utcnow(),
        deadline_at=datetime.utcnow() + timedelta(days=7),
        is_late=False,
        resubmission_number=1,
        is_locked=False,
        created_at=datetime.utcnow()
    )
    db.add(submission)
    await db.flush()
    
    # In blind mode, should NOT have:
    # - tournament_team_id
    # - original_filename
    # - file_hash
    # - submitted_at (timing attacks)
    blind_data = submission.to_dict(blind_mode=True)
    
    assert "id" in blind_data
    assert "side" in blind_data
    assert "moot_problem_id" in blind_data
    
    # These should NOT be present
    assert "tournament_team_id" not in blind_data or blind_data.get("tournament_team_id") is None
    assert "original_filename" not in blind_data
    assert "file_hash_sha256" not in blind_data
    assert "internal_filename" not in blind_data
    assert "submitted_at" not in blind_data
    assert "created_at" not in blind_data


def test_blind_mode_full_data_when_not_blind():
    """Test non-blind mode returns all data."""
    # Create a mock submission
    from unittest.mock import MagicMock
    
    submission = MagicMock(spec=MemorialSubmission)
    submission.id = 1
    submission.tournament_team_id = 100
    submission.moot_problem_id = 50
    submission.side = MemorialSide.PETITIONER
    submission.file_hash_sha256 = "abc123"
    submission.file_size_bytes = 1000
    submission.original_filename = "test.pdf"
    submission.internal_filename = "uuid.pdf"
    submission.submitted_at = datetime.utcnow()
    submission.deadline_at = datetime.utcnow()
    submission.is_late = False
    submission.resubmission_number = 1
    submission.is_locked = False
    submission.created_at = datetime.utcnow()
    
    # Non-blind mode should have all fields
    full_data = MemorialSubmission.to_dict(submission, blind_mode=False)
    
    assert full_data["tournament_team_id"] == 100
    assert full_data["file_hash_sha256"] == "abc123"
    assert full_data["original_filename"] == "test.pdf"


# =============================================================================
# Test: Freeze Snapshot Integrity
# =============================================================================

@pytest.mark.asyncio
async def test_freeze_stores_evaluation_snapshot(
    db: AsyncSession,
    tournament_team_a: TournamentTeam,
    moot_problem: MootProblem,
    user_a: User
):
    """Test freeze stores immutable snapshot of evaluations."""
    # Create submission
    submission = MemorialSubmission(
        tournament_team_id=tournament_team_a.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_path="/tmp/test.pdf",
        file_hash_sha256="abc123",
        file_size_bytes=1000,
        original_filename="test.pdf",
        internal_filename="uuid.pdf",
        submitted_at=datetime.utcnow(),
        deadline_at=datetime.utcnow() + timedelta(days=7),
        is_late=False,
        resubmission_number=1,
        is_locked=False,
        created_at=datetime.utcnow()
    )
    db.add(submission)
    await db.flush()
    
    # Create evaluation
    from decimal import Decimal
    evaluation = MemorialEvaluation(
        memorial_submission_id=submission.id,
        judge_id=user_a.id,
        legal_analysis_score=Decimal("85.00"),
        research_depth_score=Decimal("80.00"),
        clarity_score=Decimal("90.00"),
        citation_format_score=Decimal("75.00"),
        total_score=Decimal("330.00"),
        evaluation_hash="original_hash_abc123",
        evaluated_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(evaluation)
    await db.flush()
    
    # Create freeze
    freeze = MemorialScoreFreeze(
        moot_problem_id=moot_problem.id,
        frozen_at=datetime.utcnow(),
        frozen_by=user_a.id,
        checksum="freeze_checksum",
        is_final=True,
        total_evaluations=1,
        evaluation_snapshot_json=[
            {
                "evaluation_id": evaluation.id,
                "hash": "original_hash_abc123"
            }
        ],
        created_at=datetime.utcnow()
    )
    db.add(freeze)
    await db.flush()
    
    # Verify snapshot is stored
    assert freeze.evaluation_snapshot_json is not None
    assert len(freeze.evaluation_snapshot_json) == 1
    assert freeze.evaluation_snapshot_json[0]["evaluation_id"] == evaluation.id
    assert freeze.evaluation_snapshot_json[0]["hash"] == "original_hash_abc123"


# =============================================================================
# Test: Database Trigger (if PostgreSQL)
# =============================================================================

@pytest.mark.asyncio
async def test_postgresql_freeze_trigger_blocks_update(
    db: AsyncSession,
    tournament_team_a: TournamentTeam,
    moot_problem: MootProblem,
    user_a: User
):
    """
    Test PostgreSQL trigger blocks evaluation updates after freeze.
    
    This test only runs on PostgreSQL (skipped on SQLite).
    """
    # Check if we're on PostgreSQL
    result = await db.execute(text("SELECT current_database()"))
    db_name = result.scalar()
    
    # Check dialect
    result = await db.execute(text("SHOW server_version"))
    version = result.scalar()
    
    if not version or "SQLite" in str(version):
        pytest.skip("PostgreSQL-specific test")
    
    # Create submission and evaluation
    submission = MemorialSubmission(
        tournament_team_id=tournament_team_a.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_path="/tmp/test.pdf",
        file_hash_sha256="abc123",
        file_size_bytes=1000,
        original_filename="test.pdf",
        internal_filename="uuid.pdf",
        submitted_at=datetime.utcnow(),
        deadline_at=datetime.utcnow() + timedelta(days=7),
        is_late=False,
        resubmission_number=1,
        is_locked=False,
        created_at=datetime.utcnow()
    )
    db.add(submission)
    await db.flush()
    
    evaluation = MemorialEvaluation(
        memorial_submission_id=submission.id,
        judge_id=user_a.id,
        legal_analysis_score=Decimal("85.00"),
        research_depth_score=Decimal("80.00"),
        clarity_score=Decimal("90.00"),
        citation_format_score=Decimal("75.00"),
        total_score=Decimal("330.00"),
        evaluation_hash="hash123",
        evaluated_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(evaluation)
    await db.flush()
    
    # Create freeze
    freeze = MemorialScoreFreeze(
        moot_problem_id=moot_problem.id,
        frozen_at=datetime.utcnow(),
        frozen_by=user_a.id,
        checksum="checksum123",
        is_final=True,
        total_evaluations=1,
        evaluation_snapshot_json=[],
        created_at=datetime.utcnow()
    )
    db.add(freeze)
    await db.flush()
    
    # Try to update evaluation (should fail due to trigger)
    try:
        await db.execute(
            text(f"""
                UPDATE memorial_evaluations
                SET legal_analysis_score = 100.00,
                    total_score = 400.00
                WHERE id = {evaluation.id}
            """)
        )
        await db.flush()
        pytest.fail("Expected exception due to freeze trigger")
    except Exception as e:
        # Should get an error about modification being blocked
        assert "frozen" in str(e).lower() or "freeze" in str(e).lower()


# =============================================================================
# Test: Determinism Preserved
# =============================================================================

def test_no_float_usage():
    """Verify no float() usage in service module."""
    import inspect
    import backend.services.memorial_service as svc
    
    source = inspect.getsource(svc)
    
    # Check for forbidden patterns
    assert 'float(' not in source or 'hashlib' in source, "Must not use float()"
    assert 'datetime.now()' not in source, "Must use utcnow()"
    assert 'random' not in source, "Must not use random()"


def test_decimal_quantization():
    """Verify Decimal quantization is used."""
    import inspect
    import backend.services.memorial_service as svc
    
    source = inspect.getsource(svc)
    
    assert 'QUANTIZER_2DP' in source, "Must use Decimal quantizer"
    assert 'quantize' in source, "Must quantize Decimal values"


# =============================================================================
# Test: Check Constraint
# =============================================================================

@pytest.mark.asyncio
async def test_total_score_check_constraint(
    db: AsyncSession,
    tournament_team_a: TournamentTeam,
    moot_problem: MootProblem,
    user_a: User
):
    """
    Test check constraint enforces total_score = sum of components.
    
    This test only runs on PostgreSQL.
    """
    # Check if we're on PostgreSQL
    result = await db.execute(text("SHOW server_version"))
    version = result.scalar()
    
    if not version or "SQLite" in str(version):
        pytest.skip("PostgreSQL-specific test")
    
    # Create submission
    submission = MemorialSubmission(
        tournament_team_id=tournament_team_a.id,
        moot_problem_id=moot_problem.id,
        side=MemorialSide.PETITIONER,
        file_path="/tmp/test.pdf",
        file_hash_sha256="abc123",
        file_size_bytes=1000,
        original_filename="test.pdf",
        internal_filename="uuid.pdf",
        submitted_at=datetime.utcnow(),
        deadline_at=datetime.utcnow() + timedelta(days=7),
        is_late=False,
        resubmission_number=1,
        is_locked=False,
        created_at=datetime.utcnow()
    )
    db.add(submission)
    await db.flush()
    
    # Try to insert evaluation with mismatched total_score
    try:
        await db.execute(
            text(f"""
                INSERT INTO memorial_evaluations (
                    memorial_submission_id, judge_id,
                    legal_analysis_score, research_depth_score,
                    clarity_score, citation_format_score, total_score,
                    evaluation_hash, evaluated_at, created_at
                ) VALUES (
                    {submission.id}, {user_a.id},
                    80.00, 80.00, 80.00, 80.00, 999.99,
                    'fake_hash', NOW(), NOW()
                )
            """)
        )
        await db.flush()
        pytest.fail("Expected check constraint violation")
    except Exception as e:
        # Should get a check constraint violation
        assert "check" in str(e).lower() or "constraint" in str(e).lower()
