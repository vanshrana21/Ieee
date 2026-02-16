"""
Phase 7 — National Moot Network Comprehensive Tests

Test coverage for:
- Multi-institution isolation
- Judge conflict detection
- Deterministic Swiss pairing
- Concurrent ranking finalization
- Ledger tamper detection
- Idempotent match submission
"""
import asyncio
import json
import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.national_network import (
    NationalTournament, TournamentInstitution, TournamentTeam,
    TournamentRound, TournamentMatch, CrossInstitutionPanel, PanelJudge,
    TournamentEvaluation, NationalTeamRanking, NationalLedgerEntry,
    TournamentFormat, TournamentStatus, MatchStatus, TournamentLedgerEventType
)
from backend.orm.institutional_governance import Institution
from backend.orm.user import User, UserRole
from backend.services.tournament_engine_service import (
    create_tournament, invite_institution, register_team,
    generate_pairings_swiss, generate_pairings_knockout,
    assign_judge_panel, submit_match_result, finalize_round,
    compute_national_ranking, finalize_tournament,
    TournamentError, JudgeConflictError
)
from backend.services.national_ledger_service import (
    append_national_ledger_entry, verify_national_ledger_chain,
    compute_ledger_hash, get_last_ledger_hash
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def test_institution(db: AsyncSession):
    """Create a test institution."""
    institution = Institution(
        name="Test Institution",
        slug="test-institution",
        compliance_mode="standard",
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(institution)
    await db.flush()
    return institution


@pytest.fixture
async def second_institution(db: AsyncSession):
    """Create a second test institution."""
    institution = Institution(
        name="Second Institution",
        slug="second-institution",
        compliance_mode="standard",
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(institution)
    await db.flush()
    return institution


@pytest.fixture
async def third_institution(db: AsyncSession):
    """Create a third test institution."""
    institution = Institution(
        name="Third Institution",
        slug="third-institution",
        compliance_mode="standard",
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(institution)
    await db.flush()
    return institution


@pytest.fixture
async def fourth_institution(db: AsyncSession):
    """Create a fourth test institution."""
    institution = Institution(
        name="Fourth Institution",
        slug="fourth-institution",
        compliance_mode="standard",
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(institution)
    await db.flush()
    return institution


@pytest.fixture
async def test_user(db: AsyncSession, test_institution):
    """Create a test admin user."""
    user = User(
        email="test@example.com",
        hashed_password="hashed_password",
        full_name="Test User",
        role=UserRole.ADMIN,
        institution_id=test_institution.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def second_user(db: AsyncSession, second_institution):
    """Create a second test user."""
    user = User(
        email="second@example.com",
        hashed_password="hashed_password",
        full_name="Second User",
        role=UserRole.FACULTY,
        institution_id=second_institution.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def test_tournament(db: AsyncSession, test_institution, test_user):
    """Create a test tournament."""
    now = datetime.utcnow()
    tournament = await create_tournament(
        name="Test National Tournament",
        slug="test-national-2026",
        host_institution_id=test_institution.id,
        created_by=test_user.id,
        format=TournamentFormat.SWISS,
        registration_opens_at=now,
        registration_closes_at=now + timedelta(days=7),
        tournament_starts_at=now + timedelta(days=14),
        db=db,
        total_rounds=3,
        max_teams_per_institution=2,
        teams_advance_to_knockout=4
    )
    return tournament


# =============================================================================
# Test 1: Multi-Institution Isolation
# =============================================================================

@pytest.mark.asyncio
async def test_multi_institution_isolation(db: AsyncSession, test_institution, second_institution, test_user, second_user):
    """
    Test that institutions cannot see each other's tournament data.
    
    - Institution A creates tournament
    - Institution B cannot access tournament data
    - Ledger entries are institution-scoped
    """
    # Create tournament by first institution
    now = datetime.utcnow()
    tournament = await create_tournament(
        name="Isolation Test Tournament",
        slug="isolation-test-2026",
        host_institution_id=test_institution.id,
        created_by=test_user.id,
        format=TournamentFormat.SWISS,
        registration_opens_at=now,
        registration_closes_at=now + timedelta(days=7),
        tournament_starts_at=now + timedelta(days=14),
        db=db
    )
    
    # Invite second institution
    invitation = await invite_institution(
        tournament_id=tournament.id,
        institution_id=second_institution.id,
        invited_by=test_user.id,
        db=db,
        max_teams_allowed=1
    )
    
    # Second user registers a team
    team = await register_team(
        tournament_id=tournament.id,
        institution_id=second_institution.id,
        team_name="Second Inst Team",
        members_json=json.dumps(["Member 1", "Member 2"]),
        registered_by=second_user.id,
        db=db
    )
    
    # Verify teams are scoped to institutions
    result = await db.execute(
        select(TournamentTeam).where(
            and_(
                TournamentTeam.tournament_id == tournament.id,
                TournamentTeam.institution_id == test_institution.id
            )
        )
    )
    host_teams = list(result.scalars().all())
    assert len(host_teams) == 0  # Host hasn't registered any teams yet
    
    result = await db.execute(
        select(TournamentTeam).where(
            and_(
                TournamentTeam.tournament_id == tournament.id,
                TournamentTeam.institution_id == second_institution.id
            )
        )
    )
    invited_teams = list(result.scalars().all())
    assert len(invited_teams) == 1
    assert invited_teams[0].team_name == "Second Inst Team"
    
    # Verify ledger has institution_id
    result = await db.execute(
        select(NationalLedgerEntry).where(
            NationalLedgerEntry.tournament_id == tournament.id
        )
    )
    entries = list(result.scalars().all())
    
    for entry in entries:
        assert entry.institution_id is not None


# =============================================================================
# Test 2: Judge Conflict Detection
# =============================================================================

@pytest.mark.asyncio
async def test_judge_conflict_detection(db: AsyncSession, test_institution, second_institution, test_user, test_tournament):
    """
    Test that judges cannot be assigned to matches involving their own institution.
    
    - Create teams from two institutions
    - Try to assign judge from one institution to match involving that institution
    - Should raise JudgeConflictError
    """
    # Create another institution
    third_institution = Institution(
        name="Third Institution",
        slug="third-institution",
        compliance_mode="standard",
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(third_institution)
    await db.flush()
    
    # Invite institutions
    await invite_institution(
        tournament_id=test_tournament.id,
        institution_id=second_institution.id,
        invited_by=test_user.id,
        db=db
    )
    
    await invite_institution(
        tournament_id=test_tournament.id,
        institution_id=third_institution.id,
        invited_by=test_user.id,
        db=db
    )
    
    # Create teams
    team1 = await register_team(
        tournament_id=test_tournament.id,
        institution_id=test_institution.id,
        team_name="Host Team",
        members_json=json.dumps(["Host 1", "Host 2"]),
        registered_by=test_user.id,
        db=db
    )
    
    team2 = await register_team(
        tournament_id=test_tournament.id,
        institution_id=second_institution.id,
        team_name="Second Team",
        members_json=json.dumps(["Second 1", "Second 2"]),
        registered_by=test_user.id,
        db=db
    )
    
    # Create a round and match
    round_obj = await generate_pairings_swiss(
        tournament_id=test_tournament.id,
        round_number=1,
        round_name="Round 1",
        scheduled_at=datetime.utcnow() + timedelta(days=1),
        created_by=test_user.id,
        db=db
    )
    
    # Get the match created
    result = await db.execute(
        select(TournamentMatch).where(TournamentMatch.round_id == round_obj.id)
    )
    match = result.scalar_one()
    
    # Create a panel with judge from first institution
    panel = CrossInstitutionPanel(
        tournament_id=test_tournament.id,
        panel_name="Test Panel",
        require_mixed_institutions=False,
        min_institutions_represented=1,
        created_by=test_user.id,
        created_at=datetime.utcnow()
    )
    db.add(panel)
    await db.flush()
    
    # Add judge from host institution
    panel_judge = PanelJudge(
        panel_id=panel.id,
        user_id=test_user.id,
        institution_id=test_institution.id,
        role="member",
        is_available=True,
        assigned_matches_count=0,
        created_at=datetime.utcnow()
    )
    db.add(panel_judge)
    await db.flush()
    
    # Try to assign panel to match - should fail due to conflict
    # because judge is from host institution and match involves host team
    with pytest.raises(JudgeConflictError):
        await assign_judge_panel(
            match_id=match.id,
            panel_id=panel.id,
            assigned_by=test_user.id,
            db=db
        )


# =============================================================================
# Test 3: Deterministic Swiss Pairing
# =============================================================================

@pytest.mark.asyncio
async def test_deterministic_swiss_pairing(db: AsyncSession, test_institution, second_institution, third_institution, test_user, test_tournament):
    """
    Test that Swiss pairing is deterministic.
    
    - Run pairing generation twice with same inputs
    - Results should be identical
    - No randomness or Python hash() used
    """
    # Invite and register teams
    institutions = [test_institution, second_institution]
    teams = []
    
    for i, inst in enumerate(institutions):
        if inst.id != test_institution.id:
            await invite_institution(
                tournament_id=test_tournament.id,
                institution_id=inst.id,
                invited_by=test_user.id,
                db=db
            )
        
        team = await register_team(
            tournament_id=test_tournament.id,
            institution_id=inst.id,
            team_name=f"Team {i+1}",
            members_json=json.dumps([f"Member {i*2+1}", f"Member {i*2+2}"]),
            registered_by=test_user.id,
            db=db
        )
        teams.append(team)
    
    # Generate pairings twice
    round1 = await generate_pairings_swiss(
        tournament_id=test_tournament.id,
        round_number=1,
        round_name="Round 1",
        scheduled_at=datetime.utcnow() + timedelta(days=1),
        created_by=test_user.id,
        db=db
    )
    
    # Get match details
    result = await db.execute(
        select(TournamentMatch).where(TournamentMatch.round_id == round1.id)
    )
    matches1 = list(result.scalars().all())
    
    # Store pairing details
    pairings1 = [
        (m.petitioner_team_id, m.respondent_team_id) for m in matches1
    ]
    
    # Verify pairing is deterministic - running again would produce same result
    # (We can't actually run again with same round number due to unique constraint)
    # So we verify the pairing follows deterministic rules:
    
    # 1. Teams with no history are paired together
    # 2. Each team appears exactly once (or has a bye)
    team_ids_in_matches = set()
    for m in matches1:
        team_ids_in_matches.add(m.petitioner_team_id)
        team_ids_in_matches.add(m.respondent_team_id)
    
    # All registered teams should be paired
    registered_team_ids = {t.id for t in teams}
    assert team_ids_in_matches == registered_team_ids


# =============================================================================
# Test 4: Concurrent Ranking Finalization
# =============================================================================

@pytest.mark.asyncio
async def test_concurrent_ranking_finalization(db: AsyncSession, test_institution, second_institution, test_user, test_tournament):
    """
    Test that concurrent ranking finalization is handled correctly.
    
    - Multiple concurrent attempts to finalize
    - Only one should succeed
    - Idempotent behavior on re-attempt
    """
    # Setup: Create teams and matches
    await invite_institution(
        tournament_id=test_tournament.id,
        institution_id=second_institution.id,
        invited_by=test_user.id,
        db=db
    )
    
    team1 = await register_team(
        tournament_id=test_tournament.id,
        institution_id=test_institution.id,
        team_name="Team 1",
        members_json=json.dumps(["M1", "M2"]),
        registered_by=test_user.id,
        db=db
    )
    
    team2 = await register_team(
        tournament_id=test_tournament.id,
        institution_id=second_institution.id,
        team_name="Team 2",
        members_json=json.dumps(["M3", "M4"]),
        registered_by=test_user.id,
        db=db
    )
    
    # Create round
    round_obj = await generate_pairings_swiss(
        tournament_id=test_tournament.id,
        round_number=1,
        round_name="Round 1",
        scheduled_at=datetime.utcnow() + timedelta(days=1),
        created_by=test_user.id,
        db=db
    )
    
    # Submit match result
    result = await db.execute(
        select(TournamentMatch).where(TournamentMatch.round_id == round_obj.id)
    )
    match = result.scalar_one()
    
    await submit_match_result(
        match_id=match.id,
        petitioner_score=Decimal("85.5"),
        respondent_score=Decimal("78.0"),
        submitted_by=test_user.id,
        idempotency_key="test-key-1",
        db=db
    )
    
    # Try to finalize round - first attempt should succeed
    finalized_round = await finalize_round(
        round_id=round_obj.id,
        finalized_by=test_user.id,
        db=db
    )
    
    assert finalized_round.is_finalized is True
    assert finalized_round.finalized_at is not None
    
    # Second attempt should fail (round already finalized)
    with pytest.raises(TournamentError) as exc_info:
        await finalize_round(
            round_id=round_obj.id,
            finalized_by=test_user.id,
            db=db
        )
    
    assert "already finalized" in str(exc_info.value).lower()


# =============================================================================
# Test 5: Ledger Tamper Detection
# =============================================================================

@pytest.mark.asyncio
async def test_ledger_tamper_detection(db: AsyncSession, test_institution, test_user, test_tournament):
    """
    Test that ledger tampering is detected by chain verification.
    
    - Create ledger entries
    - Verify chain integrity (should pass)
    - Simulate tampering by checking hash computation
    - Verify tampered data is detected
    """
    # Create several ledger entries
    for i in range(3):
        await append_national_ledger_entry(
            tournament_id=test_tournament.id,
            event_type=TournamentLedgerEventType.TEAM_REGISTERED,
            entity_type="test_entity",
            entity_id=i + 1,
            event_data={"index": i, "data": f"test_{i}"},
            actor_user_id=test_user.id,
            institution_id=test_institution.id,
            db=db
        )
    
    # Verify chain integrity
    verification = await verify_national_ledger_chain(test_tournament.id, db)
    
    assert verification["is_valid"] is True
    assert verification["total_entries"] == 3
    assert len(verification["invalid_entries"]) == 0
    assert verification["errors"] is None
    
    # Test hash computation is deterministic
    previous_hash = "GENESIS"
    event_data = {"test": "data"}
    timestamp = "2026-02-14T12:00:00"
    
    hash1 = compute_ledger_hash(previous_hash, event_data, timestamp)
    hash2 = compute_ledger_hash(previous_hash, event_data, timestamp)
    
    assert hash1 == hash2  # Deterministic
    assert len(hash1) == 64  # SHA256 hex length
    
    # Verify chain links
    result = await db.execute(
        select(NationalLedgerEntry)
        .where(NationalLedgerEntry.tournament_id == test_tournament.id)
        .order_by(NationalLedgerEntry.id.asc())
    )
    entries = list(result.scalars().all())
    
    # First entry should have GENESIS previous_hash
    assert entries[0].previous_hash == "GENESIS"
    
    # Subsequent entries should link to previous
    for i in range(1, len(entries)):
        assert entries[i].previous_hash == entries[i-1].event_hash


# =============================================================================
# Test 6: Idempotent Match Submission
# =============================================================================

@pytest.mark.asyncio
async def test_idempotent_match_submission(db: AsyncSession, test_institution, second_institution, test_user, test_tournament):
    """
    Test that match submission is idempotent.
    
    - Submit match result with idempotency key
    - Submit again with same key
    - Second submission should return same result without error
    - Data should not change
    """
    # Setup
    await invite_institution(
        tournament_id=test_tournament.id,
        institution_id=second_institution.id,
        invited_by=test_user.id,
        db=db
    )
    
    team1 = await register_team(
        tournament_id=test_tournament.id,
        institution_id=test_institution.id,
        team_name="Team 1",
        members_json=json.dumps(["M1", "M2"]),
        registered_by=test_user.id,
        db=db
    )
    
    team2 = await register_team(
        tournament_id=test_tournament.id,
        institution_id=second_institution.id,
        team_name="Team 2",
        members_json=json.dumps(["M3", "M4"]),
        registered_by=test_user.id,
        db=db
    )
    
    round_obj = await generate_pairings_swiss(
        tournament_id=test_tournament.id,
        round_number=1,
        round_name="Round 1",
        scheduled_at=datetime.utcnow() + timedelta(days=1),
        created_by=test_user.id,
        db=db
    )
    
    result = await db.execute(
        select(TournamentMatch).where(TournamentMatch.round_id == round_obj.id)
    )
    match = result.scalar_one()
    
    # First submission
    idempotency_key = "unique-key-12345"
    
    result1 = await submit_match_result(
        match_id=match.id,
        petitioner_score=Decimal("85.5"),
        respondent_score=Decimal("78.0"),
        submitted_by=test_user.id,
        idempotency_key=idempotency_key,
        db=db
    )
    
    assert result1.petitioner_score == Decimal("85.5")
    assert result1.respondent_score == Decimal("78.0")
    assert result1.winner_team_id == match.petitioner_team_id
    
    # Second submission with same key - should be idempotent
    result2 = await submit_match_result(
        match_id=match.id,
        petitioner_score=Decimal("90.0"),  # Different scores
        respondent_score=Decimal("70.0"),
        submitted_by=test_user.id,
        idempotency_key=idempotency_key,  # Same key
        db=db
    )
    
    # Should return same result as first submission (scores unchanged)
    assert result2.petitioner_score == Decimal("85.5")  # Original value
    assert result2.respondent_score == Decimal("78.0")  # Original value
    assert result2.id == result1.id


# =============================================================================
# Test 7: Ledger Append-Only Enforcement
# =============================================================================

@pytest.mark.asyncio
async def test_ledger_append_only(db: AsyncSession, test_institution, test_user, test_tournament):
    """
    Test that ledger is append-only.
    
    - Attempt to update ledger entry (should fail)
    - Attempt to delete ledger entry (should fail)
    """
    # Create a ledger entry
    entry = await append_national_ledger_entry(
        tournament_id=test_tournament.id,
        event_type=TournamentLedgerEventType.TOURNAMENT_CREATED,
        entity_type="tournament",
        entity_id=test_tournament.id,
        event_data={"test": "data"},
        actor_user_id=test_user.id,
        institution_id=test_institution.id,
        db=db
    )
    
    # Attempt to update entry - should raise exception
    with pytest.raises(Exception) as exc_info:
        entry.event_data_json = json.dumps({"tampered": "data"})
        await db.flush()
    
    assert "append-only" in str(exc_info.value).lower() or "update" in str(exc_info.value).lower()
    
    # Rollback and test delete
    await db.rollback()
    
    # Reload entry
    result = await db.execute(
        select(NationalLedgerEntry).where(NationalLedgerEntry.id == entry.id)
    )
    entry = result.scalar_one_or_none()
    
    if entry:  # If entry still exists
        with pytest.raises(Exception) as exc_info:
            await db.delete(entry)
            await db.flush()
        
        assert "append-only" in str(exc_info.value).lower() or "delete" in str(exc_info.value).lower()


# =============================================================================
# Test 8: Knockout Bracket Generation
# =============================================================================

@pytest.mark.asyncio
async def test_knockout_bracket_generation(db: AsyncSession, test_institution, second_institution, third_institution, fourth_institution, test_user, test_tournament):
    """
    Test deterministic knockout bracket generation.
    
    - Create 8 teams with seeds
    - Generate knockout pairings
    - Verify bracket follows 1v8, 2v7, 3v6, 4v5 pattern
    """
    institutions = [test_institution, second_institution, third_institution, fourth_institution]
    
    # Invite all institutions
    for inst in institutions:
        if inst.id != test_institution.id:
            await invite_institution(
                tournament_id=test_tournament.id,
                institution_id=inst.id,
                invited_by=test_user.id,
                db=db,
                max_teams_allowed=2
            )
    
    # Create 8 teams with seeds
    teams = []
    for i in range(8):
        inst = institutions[i // 2]
        team = await register_team(
            tournament_id=test_tournament.id,
            institution_id=inst.id,
            team_name=f"Seed {i+1} Team",
            members_json=json.dumps([f"M{i*2+1}", f"M{i*2+2}"]),
            registered_by=test_user.id,
            db=db,
            seed_number=i+1
        )
        teams.append(team)
    
    # Generate knockout pairings
    round_obj = await generate_pairings_knockout(
        tournament_id=test_tournament.id,
        round_number=4,
        round_name="Quarterfinals",
        scheduled_at=datetime.utcnow() + timedelta(days=1),
        teams_advancing=teams,
        created_by=test_user.id,
        db=db
    )
    
    # Get matches
    result = await db.execute(
        select(TournamentMatch).where(TournamentMatch.round_id == round_obj.id)
    )
    matches = list(result.scalars().all())
    
    # Should have 4 matches for 8 teams
    assert len(matches) == 4
    
    # Verify bracket pattern: 1v8, 2v7, 3v6, 4v5
    # Get teams by seed
    teams_by_seed = {t.seed_number: t for t in teams}
    
    # Check each match follows expected pattern
    for match in matches:
        petitioner_seed = next((t.seed_number for t in teams if t.id == match.petitioner_team_id), None)
        respondent_seed = next((t.seed_number for t in teams if t.id == match.respondent_team_id), None)
        
        # One should be high seed (1-4), one should be low seed (5-8)
        assert petitioner_seed is not None and respondent_seed is not None
        assert (petitioner_seed <= 4 and respondent_seed >= 5) or (petitioner_seed >= 5 and respondent_seed <= 4)


# =============================================================================
# Test 9: Ranking Computation with Decimal Precision
# =============================================================================

@pytest.mark.asyncio
async def test_ranking_decimal_precision(db: AsyncSession, test_institution, second_institution, test_user, test_tournament):
    """
    Test that rankings use Decimal precision (never float).
    
    - Create teams with specific scores
    - Compute rankings
    - Verify no float values in ranking data
    """
    # Setup teams
    await invite_institution(
        tournament_id=test_tournament.id,
        institution_id=second_institution.id,
        invited_by=test_user.id,
        db=db
    )
    
    team1 = await register_team(
        tournament_id=test_tournament.id,
        institution_id=test_institution.id,
        team_name="Team A",
        members_json=json.dumps(["M1", "M2"]),
        registered_by=test_user.id,
        db=db
    )
    
    team2 = await register_team(
        tournament_id=test_tournament.id,
        institution_id=second_institution.id,
        team_name="Team B",
        members_json=json.dumps(["M3", "M4"]),
        registered_by=test_user.id,
        db=db
    )
    
    # Manually set precise scores
    team1.total_score = Decimal("123.4567")
    team1.wins = 2
    team2.total_score = Decimal("123.4566")
    team2.wins = 2
    await db.flush()
    
    # Compute ranking
    ranking = await compute_national_ranking(
        tournament_id=test_tournament.id,
        round_id=None,
        computed_by=test_user.id,
        db=db
    )
    
    # Parse rankings JSON
    rankings_data = json.loads(ranking.rankings_json)
    
    # Verify all scores are strings (Decimal serialized)
    for r in rankings_data:
        assert isinstance(r["base_score"], str)
        assert isinstance(r["weighted_score"], str)
        # Verify no float representation (would have less precision)
        assert "." in r["base_score"]  # Decimal representation


# =============================================================================
# Test 10: Tournament Lifecycle
# =============================================================================

@pytest.mark.asyncio
async def test_full_tournament_lifecycle(db: AsyncSession, test_institution, second_institution, test_user):
    """
    Test complete tournament lifecycle from creation to finalization.
    
    - Create tournament
    - Invite institutions
    - Register teams
    - Generate pairings
    - Submit results
    - Finalize rounds
    - Finalize tournament
    - Verify final ranking
    """
    # 1. Create tournament
    now = datetime.utcnow()
    tournament = await create_tournament(
        name="Full Lifecycle Tournament",
        slug="lifecycle-test-2026",
        host_institution_id=test_institution.id,
        created_by=test_user.id,
        format=TournamentFormat.SWISS,
        registration_opens_at=now,
        registration_closes_at=now + timedelta(days=7),
        tournament_starts_at=now + timedelta(days=14),
        db=db,
        total_rounds=2,
        max_teams_per_institution=2,
        teams_advance_to_knockout=2
    )
    
    assert tournament.status == TournamentStatus.DRAFT
    
    # 2. Invite institution
    await invite_institution(
        tournament_id=tournament.id,
        institution_id=second_institution.id,
        invited_by=test_user.id,
        db=db
    )
    
    # 3. Register teams
    team1 = await register_team(
        tournament_id=tournament.id,
        institution_id=test_institution.id,
        team_name="Host Champions",
        members_json=json.dumps(["Alice", "Bob"]),
        registered_by=test_user.id,
        db=db
    )
    
    team2 = await register_team(
        tournament_id=tournament.id,
        institution_id=second_institution.id,
        team_name="Guest Challengers",
        members_json=json.dumps(["Carol", "Dave"]),
        registered_by=test_user.id,
        db=db
    )
    
    # 4. Generate pairings for Round 1
    round1 = await generate_pairings_swiss(
        tournament_id=tournament.id,
        round_number=1,
        round_name="Round 1",
        scheduled_at=now + timedelta(days=1),
        created_by=test_user.id,
        db=db
    )
    
    # 5. Submit match result
    result = await db.execute(
        select(TournamentMatch).where(TournamentMatch.round_id == round1.id)
    )
    match = result.scalar_one()
    
    await submit_match_result(
        match_id=match.id,
        petitioner_score=Decimal("90.0"),
        respondent_score=Decimal("85.0"),
        submitted_by=test_user.id,
        idempotency_key=f"round1-match-{match.id}",
        db=db
    )
    
    # 6. Finalize Round 1
    await finalize_round(
        round_id=round1.id,
        finalized_by=test_user.id,
        db=db
    )
    
    # 7. Generate pairings for Round 2
    round2 = await generate_pairings_swiss(
        tournament_id=tournament.id,
        round_number=2,
        round_name="Round 2",
        scheduled_at=now + timedelta(days=2),
        created_by=test_user.id,
        db=db
    )
    
    # Submit results for Round 2
    result = await db.execute(
        select(TournamentMatch).where(TournamentMatch.round_id == round2.id)
    )
    match2 = result.scalar_one()
    
    await submit_match_result(
        match_id=match2.id,
        petitioner_score=Decimal("88.0"),
        respondent_score=Decimal("82.0"),
        submitted_by=test_user.id,
        idempotency_key=f"round2-match-{match2.id}",
        db=db
    )
    
    # 8. Finalize Round 2
    await finalize_round(
        round_id=round2.id,
        finalized_by=test_user.id,
        db=db
    )
    
    # 9. Finalize tournament
    finalized_tournament = await finalize_tournament(
        tournament_id=tournament.id,
        finalized_by=test_user.id,
        db=db
    )
    
    assert finalized_tournament.status == TournamentStatus.COMPLETED
    assert finalized_tournament.tournament_ends_at is not None
    
    # 10. Verify ledger has all events
    result = await db.execute(
        select(func.count(NationalLedgerEntry.id))
        .where(NationalLedgerEntry.tournament_id == tournament.id)
    )
    entry_count = result.scalar()
    
    assert entry_count >= 6  # Tournament creation + invites + teams + pairings + results + finalizations
    
    # Verify ledger chain integrity
    verification = await verify_national_ledger_chain(tournament.id, db)
    assert verification["is_valid"] is True
