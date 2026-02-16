"""
Phase 7 — Evidence & Exhibit Management Engine Test Suite

Tests for:
- Exhibit upload with PDF validation
- Deterministic numbering (P-1, P-2, R-1, R-2...)
- State transitions: uploaded → marked → tendered → admitted/rejected
- Presiding judge authority enforcement
- File integrity verification
- Immutability after ruling
- Institution scoping
- Event chain logging
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.live_court import (
    LiveCourtSession, LiveTurn, LiveCourtStatus, LiveTurnState, OralSide, OralTurnType
)
from backend.orm.exhibit import SessionExhibit, ExhibitState
from backend.orm.national_network import Institution
from backend.orm.round_pairing import TournamentRound, RoundType
from backend.services.exhibit_service import (
    upload_exhibit, mark_exhibit, tender_exhibit, rule_exhibit,
    get_exhibits_by_session, verify_exhibit_integrity,
    validate_pdf_magic_bytes, compute_file_hash,
    ExhibitNotFoundError, ExhibitAlreadyRuledError,
    InvalidStateTransitionError, NotPresidingJudgeError,
    SessionNotLiveError, SessionCompletedError, InvalidFileError
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def institution_a(db: AsyncSession) -> Institution:
    """Create test institution."""
    inst = Institution(
        name="Test College A",
        code="TCA001",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(inst)
    await db.flush()
    return inst


@pytest.fixture
async def session_live(
    db: AsyncSession,
    institution_a: Institution
) -> LiveCourtSession:
    """Create a live session."""
    round_obj = TournamentRound(
        tournament_id=1,
        round_number=1,
        round_type=RoundType.SWISS,
        created_at=datetime.utcnow()
    )
    db.add(round_obj)
    await db.flush()

    session = LiveCourtSession(
        round_id=round_obj.id,
        institution_id=institution_a.id,
        status=LiveCourtStatus.LIVE,
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(session)
    await db.flush()
    return session


@pytest.fixture
async def active_turn(
    db: AsyncSession,
    session_live: LiveCourtSession
) -> LiveTurn:
    """Create an active turn."""
    turn = LiveTurn(
        session_id=session_live.id,
        participant_id=1,
        side=OralSide.PETITIONER,
        turn_type=OralTurnType.PRESENTATION,
        allocated_seconds=60,
        state=LiveTurnState.ACTIVE,
        started_at=datetime.utcnow(),
        is_timer_paused=False,
        created_at=datetime.utcnow()
    )
    db.add(turn)
    await db.flush()
    return turn


@pytest.fixture
def sample_pdf_content() -> bytes:
    """Create sample PDF content for testing."""
    # Minimal valid PDF header
    return b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n%%EOF'


# =============================================================================
# Test: PDF Magic Bytes Validation
# =============================================================================

def test_validate_pdf_magic_bytes_valid():
    """Test valid PDF detection."""
    valid_pdf = b'%PDF-1.4 some content'
    assert validate_pdf_magic_bytes(valid_pdf) == True


def test_validate_pdf_magic_bytes_invalid():
    """Test invalid PDF detection."""
    invalid = b'NOT_A_PDF'
    assert validate_pdf_magic_bytes(invalid) == False


def test_validate_pdf_magic_bytes_empty():
    """Test empty file detection."""
    assert validate_pdf_magic_bytes(b'') == False


# =============================================================================
# Test: File Hash Computation
# =============================================================================

def test_compute_file_hash_deterministic():
    """Test file hash is deterministic."""
    content = b'test content for hashing'
    hash1 = compute_file_hash(content)
    hash2 = compute_file_hash(content)
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 hex


def test_compute_file_hash_different_content():
    """Test different content produces different hashes."""
    hash1 = compute_file_hash(b'content1')
    hash2 = compute_file_hash(b'content2')
    assert hash1 != hash2


# =============================================================================
# Test: Upload Exhibit
# =============================================================================

@pytest.mark.asyncio
async def test_upload_exhibit_success(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    sample_pdf_content: bytes
):
    """Test successful exhibit upload."""
    exhibit = await upload_exhibit(
        session_id=session_live.id,
        institution_id=institution_a.id,
        side="petitioner",
        original_filename="test_exhibit.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    assert exhibit.id is not None
    assert exhibit.session_id == session_live.id
    assert exhibit.side == "petitioner"
    assert exhibit.state == ExhibitState.UPLOADED
    assert exhibit.file_hash_sha256 is not None
    assert exhibit.file_path is not None


@pytest.mark.asyncio
async def test_upload_exhibit_invalid_file(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution
):
    """Test upload with invalid file type."""
    invalid_content = b'NOT_A_PDF_FILE'

    with pytest.raises(InvalidFileError):
        await upload_exhibit(
            session_id=session_live.id,
            institution_id=institution_a.id,
            side="petitioner",
            original_filename="test.txt",
            file_content=invalid_content,
            uploaded_by_user_id=1,
            db=db
        )


@pytest.mark.asyncio
async def test_upload_exhibit_after_session_completed(
    db: AsyncSession,
    institution_a: Institution,
    sample_pdf_content: bytes
):
    """Test upload fails after session completed."""
    # Create completed session
    round_obj = TournamentRound(
        tournament_id=1,
        round_number=1,
        round_type=RoundType.SWISS,
        created_at=datetime.utcnow()
    )
    db.add(round_obj)
    await db.flush()

    completed_session = LiveCourtSession(
        round_id=round_obj.id,
        institution_id=institution_a.id,
        status=LiveCourtStatus.COMPLETED,
        started_at=datetime.utcnow() - timedelta(hours=1),
        ended_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(completed_session)
    await db.flush()

    with pytest.raises(SessionCompletedError):
        await upload_exhibit(
            session_id=completed_session.id,
            institution_id=institution_a.id,
            side="petitioner",
            original_filename="test.pdf",
            file_content=sample_pdf_content,
            uploaded_by_user_id=1,
            db=db
        )


# =============================================================================
# Test: Mark Exhibit with Deterministic Numbering
# =============================================================================

@pytest.mark.asyncio
async def test_mark_exhibit_numbering(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    sample_pdf_content: bytes
):
    """Test deterministic exhibit numbering."""
    # Upload exhibits for petitioner
    exhibits = []
    for i in range(3):
        ex = await upload_exhibit(
            session_id=session_live.id,
            institution_id=institution_a.id,
            side="petitioner",
            original_filename=f"exhibit_{i}.pdf",
            file_content=sample_pdf_content,
            uploaded_by_user_id=1,
            db=db
        )
        exhibits.append(ex)

    # Mark exhibits - should get P-1, P-2, P-3
    for i, ex in enumerate(exhibits):
        marked = await mark_exhibit(
            exhibit_id=ex.id,
            marked_by_user_id=1,
            db=db
        )
        assert marked.exhibit_number == i + 1
        assert marked.get_formatted_number() == f"P-{i + 1}"
        assert marked.state == ExhibitState.MARKED
        assert marked.exhibit_hash != "0" * 64


@pytest.mark.asyncio
async def test_mark_exhibit_numbering_per_side(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    sample_pdf_content: bytes
):
    """Test separate numbering for each side."""
    # Upload for petitioner
    p_exhibit = await upload_exhibit(
        session_id=session_live.id,
        institution_id=institution_a.id,
        side="petitioner",
        original_filename="p_exhibit.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    # Upload for respondent
    r_exhibit = await upload_exhibit(
        session_id=session_live.id,
        institution_id=institution_a.id,
        side="respondent",
        original_filename="r_exhibit.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    # Mark both - should both be #1 for their side
    p_marked = await mark_exhibit(p_exhibit.id, 1, db)
    r_marked = await mark_exhibit(r_exhibit.id, 1, db)

    assert p_marked.exhibit_number == 1
    assert r_marked.exhibit_number == 1
    assert p_marked.get_formatted_number() == "P-1"
    assert r_marked.get_formatted_number() == "R-1"


@pytest.mark.asyncio
async def test_mark_exhibit_invalid_state(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    sample_pdf_content: bytes
):
    """Test marking already marked exhibit fails."""
    exhibit = await upload_exhibit(
        session_id=session_live.id,
        institution_id=institution_a.id,
        side="petitioner",
        original_filename="test.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    # Mark once
    await mark_exhibit(exhibit.id, 1, db)

    # Try to mark again
    with pytest.raises(InvalidStateTransitionError):
        await mark_exhibit(exhibit.id, 1, db)


# =============================================================================
# Test: Tender Exhibit
# =============================================================================

@pytest.mark.asyncio
async def test_tender_exhibit_success(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    active_turn: LiveTurn,
    sample_pdf_content: bytes
):
    """Test successful exhibit tender."""
    exhibit = await upload_exhibit(
        session_id=session_live.id,
        institution_id=institution_a.id,
        side="petitioner",
        original_filename="test.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    # Mark first
    marked = await mark_exhibit(exhibit.id, 1, db)

    # Tender
    tendered = await tender_exhibit(
        exhibit_id=marked.id,
        turn_id=active_turn.id,
        tendered_by_user_id=1,
        db=db
    )

    assert tendered.state == ExhibitState.TENDERED
    assert tendered.turn_id == active_turn.id


@pytest.mark.asyncio
async def test_tender_exhibit_wrong_state(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    active_turn: LiveTurn,
    sample_pdf_content: bytes
):
    """Test tendering uploaded (not marked) exhibit fails."""
    exhibit = await upload_exhibit(
        session_id=session_live.id,
        institution_id=institution_a.id,
        side="petitioner",
        original_filename="test.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    # Try to tender without marking
    with pytest.raises(InvalidStateTransitionError):
        await tender_exhibit(exhibit.id, active_turn.id, 1, db)


# =============================================================================
# Test: Rule on Exhibit
# =============================================================================

@pytest.mark.asyncio
async def test_rule_exhibit_admit(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    active_turn: LiveTurn,
    sample_pdf_content: bytes
):
    """Test admitting a tendered exhibit."""
    exhibit = await upload_exhibit(
        session_id=session_live.id,
        institution_id=institution_a.id,
        side="petitioner",
        original_filename="test.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    marked = await mark_exhibit(exhibit.id, 1, db)
    tendered = await tender_exhibit(marked.id, active_turn.id, 1, db)

    ruled = await rule_exhibit(
        exhibit_id=tendered.id,
        decision=ExhibitState.ADMITTED,
        ruling_reason_text="Relevant and authentic",
        ruled_by_user_id=2,
        is_presiding_judge=True,
        db=db
    )

    assert ruled.state == ExhibitState.ADMITTED
    assert ruled.ruled_by_user_id == 2
    assert ruled.ruled_at is not None


@pytest.mark.asyncio
async def test_rule_exhibit_reject(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    active_turn: LiveTurn,
    sample_pdf_content: bytes
):
    """Test rejecting a tendered exhibit."""
    exhibit = await upload_exhibit(
        session_id=session_live.id,
        institution_id=institution_a.id,
        side="petitioner",
        original_filename="test.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    marked = await mark_exhibit(exhibit.id, 1, db)
    tendered = await tender_exhibit(marked.id, active_turn.id, 1, db)

    ruled = await rule_exhibit(
        exhibit_id=tendered.id,
        decision=ExhibitState.REJECTED,
        ruling_reason_text="Irrelevant",
        ruled_by_user_id=2,
        is_presiding_judge=True,
        db=db
    )

    assert ruled.state == ExhibitState.REJECTED


@pytest.mark.asyncio
async def test_rule_exhibit_not_presiding_judge(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    active_turn: LiveTurn,
    sample_pdf_content: bytes
):
    """Test non-presiding judge cannot rule."""
    exhibit = await upload_exhibit(
        session_id=session_live.id,
        institution_id=institution_a.id,
        side="petitioner",
        original_filename="test.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    marked = await mark_exhibit(exhibit.id, 1, db)
    tendered = await tender_exhibit(marked.id, active_turn.id, 1, db)

    with pytest.raises(NotPresidingJudgeError):
        await rule_exhibit(
            exhibit_id=tendered.id,
            decision=ExhibitState.ADMITTED,
            ruling_reason_text="Test",
            ruled_by_user_id=2,
            is_presiding_judge=False,  # Not presiding
            db=db
        )


@pytest.mark.asyncio
async def test_rule_exhibit_twice_idempotent(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    active_turn: LiveTurn,
    sample_pdf_content: bytes
):
    """Test ruling twice fails cleanly."""
    exhibit = await upload_exhibit(
        session_id=session_live.id,
        institution_id=institution_a.id,
        side="petitioner",
        original_filename="test.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    marked = await mark_exhibit(exhibit.id, 1, db)
    tendered = await tender_exhibit(marked.id, active_turn.id, 1, db)

    # First ruling
    await rule_exhibit(
        exhibit_id=tendered.id,
        decision=ExhibitState.ADMITTED,
        ruling_reason_text="Test",
        ruled_by_user_id=2,
        is_presiding_judge=True,
        db=db
    )

    # Second ruling attempt
    with pytest.raises(ExhibitAlreadyRuledError):
        await rule_exhibit(
            exhibit_id=tendered.id,
            decision=ExhibitState.REJECTED,
            ruling_reason_text="Changed mind",
            ruled_by_user_id=2,
            is_presiding_judge=True,
            db=db
        )


# =============================================================================
# Test: Exhibit Hash Verification
# =============================================================================

@pytest.mark.asyncio
async def test_exhibit_hash_computed_correctly(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    sample_pdf_content: bytes
):
    """Test exhibit hash is computed correctly."""
    exhibit = await upload_exhibit(
        session_id=session_live.id,
        institution_id=institution_a.id,
        side="petitioner",
        original_filename="test.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    marked = await mark_exhibit(exhibit.id, 1, db)

    # Hash should be present
    assert marked.exhibit_hash is not None
    assert len(marked.exhibit_hash) == 64  # SHA256 hex

    # Verify hash matches
    assert marked.verify_hash() == True


# =============================================================================
# Test: Query Functions
# =============================================================================

@pytest.mark.asyncio
async def test_get_exhibits_by_session(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    sample_pdf_content: bytes
):
    """Test querying exhibits by session."""
    # Create exhibits
    for i in range(3):
        ex = await upload_exhibit(
            session_id=session_live.id,
            institution_id=institution_a.id,
            side="petitioner",
            original_filename=f"exhibit_{i}.pdf",
            file_content=sample_pdf_content,
            uploaded_by_user_id=1,
            db=db
        )
        if i < 2:
            await mark_exhibit(ex.id, 1, db)

    exhibits = await get_exhibits_by_session(session_live.id, db)
    assert len(exhibits) == 3

    # Filter by state
    marked = await get_exhibits_by_session(session_live.id, db, ExhibitState.MARKED)
    assert len(marked) == 2

    # Filter by side
    p_exhibits = await get_exhibits_by_session(session_live.id, db, side="petitioner")
    assert len(p_exhibits) == 3


# =============================================================================
# Test: Exhibit State Enum
# =============================================================================

def test_exhibit_state_enum_values():
    """Test exhibit state enum values are correct."""
    assert ExhibitState.UPLOADED.value == "uploaded"
    assert ExhibitState.MARKED.value == "marked"
    assert ExhibitState.TENDERED.value == "tendered"
    assert ExhibitState.ADMITTED.value == "admitted"
    assert ExhibitState.REJECTED.value == "rejected"


# =============================================================================
# Test: Exhibit State Helpers
# =============================================================================

@pytest.mark.asyncio
async def test_exhibit_state_helpers(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    active_turn: LiveTurn,
    sample_pdf_content: bytes
):
    """Test exhibit state helper methods."""
    exhibit = await upload_exhibit(
        session_id=session_live.id,
        institution_id=institution_a.id,
        side="petitioner",
        original_filename="test.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    assert exhibit.is_uploaded()
    assert not exhibit.is_marked()
    assert not exhibit.is_tendered()
    assert not exhibit.is_admitted()
    assert not exhibit.is_rejected()
    assert not exhibit.is_ruled()

    marked = await mark_exhibit(exhibit.id, 1, db)
    assert marked.is_marked()


# =============================================================================
# Test: Event Chain Logging
# =============================================================================

@pytest.mark.asyncio
async def test_exhibit_events_logged(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    active_turn: LiveTurn,
    sample_pdf_content: bytes
):
    """Test that exhibit events are logged to event chain."""
    from backend.orm.live_court import LiveEventLog

    exhibit = await upload_exhibit(
        session_id=session_live.id,
        institution_id=institution_a.id,
        side="petitioner",
        original_filename="test.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    # Check events created
    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == session_live.id)
        .order_by(LiveEventLog.event_sequence.desc())
    )
    events = result.scalars().all()

    event_types = [e.event_type for e in events]
    assert "EXHIBIT_UPLOADED" in event_types

    # Mark and check
    await mark_exhibit(exhibit.id, 1, db)

    result = await db.execute(
        select(LiveEventLog)
        .where(LiveEventLog.session_id == session_live.id)
    )
    events = result.scalars().all()
    event_types = [e.event_type for e in events]
    assert "EXHIBIT_MARKED" in event_types
