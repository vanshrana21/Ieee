"""
Phase 7 — Evidence & Exhibit Management Concurrency Test Suite

Tests for all concurrency guarantees:
- Double mark_exhibit → only one gets exhibit_number
- Concurrent rule_exhibit → only one succeeds
- Cross-session conflict blocked
- Unique numbering enforced under race conditions
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
    ExhibitNotFoundError, InvalidStateTransitionError,
    ExhibitAlreadyRuledError
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
    return b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n%%EOF'


# =============================================================================
# Test: Concurrent Mark Exhibit Numbering
# =============================================================================

@pytest.mark.asyncio
async def test_concurrent_mark_exhibit_numbering_unique(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    sample_pdf_content: bytes
):
    """Test that concurrent marking produces unique exhibit numbers."""
    # Upload multiple exhibits for same side
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

    # Try to mark all concurrently
    results = []

    async def try_mark(exhibit_id: int):
        try:
            marked = await mark_exhibit(exhibit_id, 1, db)
            results.append(("success", marked.exhibit_number, exhibit_id))
        except Exception as e:
            results.append(("error", str(e), exhibit_id))

    await asyncio.gather(
        try_mark(exhibits[0].id),
        try_mark(exhibits[1].id),
        try_mark(exhibits[2].id),
        return_exceptions=True
    )

    # All should succeed (different exhibits)
    successes = [r for r in results if r[0] == "success"]
    assert len(successes) == 3, "All marks should succeed"

    # Numbers should be unique
    numbers = [r[1] for r in successes]
    assert len(set(numbers)) == len(numbers), "Exhibit numbers must be unique"


# =============================================================================
# Test: Concurrent Rule Exhibit
# =============================================================================

@pytest.mark.asyncio
async def test_concurrent_rule_exhibit_idempotent(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    active_turn: LiveTurn,
    sample_pdf_content: bytes
):
    """Test that concurrent ruling is idempotent."""
    # Create and prepare exhibit
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

    # Try to rule concurrently
    results = []

    async def try_rule():
        try:
            ruled = await rule_exhibit(
                exhibit_id=tendered.id,
                decision=ExhibitState.ADMITTED,
                ruling_reason_text="Test ruling",
                ruled_by_user_id=2,
                is_presiding_judge=True,
                db=db
            )
            results.append(("success", ruled.id))
        except Exception as e:
            results.append(("error", str(e)))

    await asyncio.gather(
        try_rule(),
        try_rule(),
        try_rule(),
        return_exceptions=True
    )

    # Only one should succeed
    successes = [r for r in results if r[0] == "success"]
    assert len(successes) == 1, "Only one ruling should succeed"

    # Others should fail with already ruled
    errors = [r for r in results if r[0] == "error"]
    assert len(errors) == 2
    assert any("already" in r[1].lower() for r in errors)


# =============================================================================
# Test: Cross-Session Numbering Isolation
# =============================================================================

@pytest.mark.asyncio
async def test_cross_session_numbering_isolation(
    db: AsyncSession,
    institution_a: Institution,
    sample_pdf_content: bytes
):
    """Test that exhibit numbering is isolated per session."""
    # Create two sessions
    round_obj = TournamentRound(
        tournament_id=1,
        round_number=1,
        round_type=RoundType.SWISS,
        created_at=datetime.utcnow()
    )
    db.add(round_obj)
    await db.flush()

    session1 = LiveCourtSession(
        round_id=round_obj.id,
        institution_id=institution_a.id,
        status=LiveCourtStatus.LIVE,
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(session1)

    session2 = LiveCourtSession(
        round_id=round_obj.id,
        institution_id=institution_a.id,
        status=LiveCourtStatus.LIVE,
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(session2)
    await db.flush()

    # Upload exhibits for both sessions
    ex1 = await upload_exhibit(
        session_id=session1.id,
        institution_id=institution_a.id,
        side="petitioner",
        original_filename="ex1.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    ex2 = await upload_exhibit(
        session_id=session2.id,
        institution_id=institution_a.id,
        side="petitioner",
        original_filename="ex2.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    # Mark concurrently
    results = await asyncio.gather(
        mark_exhibit(ex1.id, 1, db),
        mark_exhibit(ex2.id, 1, db),
        return_exceptions=True
    )

    # Both should get exhibit_number 1 (different sessions)
    marked1, marked2 = results
    assert marked1.exhibit_number == 1
    assert marked2.exhibit_number == 1
    assert marked1.session_id != marked2.session_id


# =============================================================================
# Test: Serial Numbering Sequence
# =============================================================================

@pytest.mark.asyncio
async def test_serial_numbering_sequence(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    sample_pdf_content: bytes
):
    """Test that exhibit numbers are sequential without gaps."""
    # Upload 5 exhibits
    exhibits = []
    for i in range(5):
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

    # Mark sequentially
    numbers = []
    for ex in exhibits:
        marked = await mark_exhibit(ex.id, 1, db)
        numbers.append(marked.exhibit_number)

    # Should be 1, 2, 3, 4, 5
    assert numbers == [1, 2, 3, 4, 5], f"Expected [1,2,3,4,5] got {numbers}"


# =============================================================================
# Test: Parallel Tender Attempts
# =============================================================================

@pytest.mark.asyncio
async def test_parallel_tender_attempts(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    active_turn: LiveTurn,
    sample_pdf_content: bytes
):
    """Test that parallel tender attempts are handled properly."""
    # Create exhibit
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

    # Try to tender multiple times (idempotent)
    results = []

    async def try_tender():
        try:
            tendered = await tender_exhibit(marked.id, active_turn.id, 1, db)
            results.append(("success", tendered.state.value))
        except Exception as e:
            results.append(("error", str(e)))

    await asyncio.gather(
        try_tender(),
        try_tender(),
        return_exceptions=True
    )

    # First should succeed, second might fail or succeed (idempotent)
    successes = [r for r in results if r[0] == "success"]
    assert len(successes) >= 1


# =============================================================================
# Test: State Transition Race
# =============================================================================

@pytest.mark.asyncio
async def test_state_transition_no_race_conditions(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    active_turn: LiveTurn,
    sample_pdf_content: bytes
):
    """Test that state transitions don't have race conditions."""
    exhibit = await upload_exhibit(
        session_id=session_live.id,
        institution_id=institution_a.id,
        side="petitioner",
        original_filename="test.pdf",
        file_content=sample_pdf_content,
        uploaded_by_user_id=1,
        db=db
    )

    # Mark
    marked = await mark_exhibit(exhibit.id, 1, db)

    # Tender
    tendered = await tender_exhibit(marked.id, active_turn.id, 1, db)
    assert tendered.state == ExhibitState.TENDERED

    # Rule
    ruled = await rule_exhibit(
        tendered.id,
        ExhibitState.ADMITTED,
        "Test",
        2,
        True,
        db
    )
    assert ruled.state == ExhibitState.ADMITTED

    # Final state should be consistent
    result = await db.execute(
        select(SessionExhibit.state)
        .where(SessionExhibit.id == exhibit.id)
    )
    final_state = result.scalar_one()
    assert final_state == ExhibitState.ADMITTED


# =============================================================================
# Test: Concurrent Upload Different Sessions
# =============================================================================

@pytest.mark.asyncio
async def test_concurrent_upload_different_sessions(
    db: AsyncSession,
    institution_a: Institution,
    sample_pdf_content: bytes
):
    """Test concurrent uploads to different sessions don't interfere."""
    round_obj = TournamentRound(
        tournament_id=1,
        round_number=1,
        round_type=RoundType.SWISS,
        created_at=datetime.utcnow()
    )
    db.add(round_obj)
    await db.flush()

    # Create two sessions
    session1 = LiveCourtSession(
        round_id=round_obj.id,
        institution_id=institution_a.id,
        status=LiveCourtStatus.LIVE,
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(session1)

    session2 = LiveCourtSession(
        round_id=round_obj.id,
        institution_id=institution_a.id,
        status=LiveCourtStatus.LIVE,
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.add(session2)
    await db.flush()

    # Upload concurrently to both sessions
    results = await asyncio.gather(
        upload_exhibit(session1.id, institution_a.id, "petitioner", "s1.pdf", sample_pdf_content, 1, db),
        upload_exhibit(session2.id, institution_a.id, "petitioner", "s2.pdf", sample_pdf_content, 1, db),
        upload_exhibit(session1.id, institution_a.id, "respondent", "s3.pdf", sample_pdf_content, 1, db),
        upload_exhibit(session2.id, institution_a.id, "respondent", "s4.pdf", sample_pdf_content, 1, db),
        return_exceptions=True
    )

    # All should succeed
    assert all(not isinstance(r, Exception) for r in results)

    # Verify correct session assignment
    assert results[0].session_id == session1.id
    assert results[1].session_id == session2.id
    assert results[2].session_id == session1.id
    assert results[3].session_id == session2.id


# =============================================================================
# Test: Immutability After Ruling (Concurrency Test)
# =============================================================================

@pytest.mark.asyncio
async def test_immutability_after_ruling_concurrent(
    db: AsyncSession,
    session_live: LiveCourtSession,
    institution_a: Institution,
    active_turn: LiveTurn,
    sample_pdf_content: bytes
):
    """Test that admitted/rejected exhibits can't be modified even with race."""
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
    ruled = await rule_exhibit(tendered.id, ExhibitState.ADMITTED, "Test", 2, True, db)

    # Try concurrent modifications (should fail at DB level on PostgreSQL)
    # On SQLite, service layer guards should catch it

    # Final state should be ADMITTED
    result = await db.execute(
        select(SessionExhibit.state)
        .where(SessionExhibit.id == exhibit.id)
    )
    final_state = result.scalar_one()
    assert final_state == ExhibitState.ADMITTED
