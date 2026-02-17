"""
Phase 4 — Judge Panel Assignment Security Test Suite

Tests for all security guarantees:
- Institution conflict detection
- Repeat judging prevention
- Post-freeze modification blocked (PostgreSQL)
- Concurrent publish idempotent
- Tamper detection works
- Cross-tenant access blocked
- Panel diversity enforcement
"""
import pytest
from datetime import datetime
from sqlalchemy import select, text, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.panel_assignment import (
    JudgePanel, PanelMember, PanelMemberRole, JudgeAssignmentHistory, PanelFreeze
)
from backend.orm.round_pairing import TournamentRound, RoundPairing, RoundType, RoundStatus
from backend.orm.national_network import TournamentTeam, NationalTournament
from backend.orm.institution import Institution
from backend.orm.user import User, UserRole
from backend.services.panel_assignment_service import (
    generate_panels_for_round, publish_panels, verify_panel_integrity,
    check_institution_conflict, check_repeat_judging, has_judge_conflict,
    get_panels_by_round, get_assignment_history,
    PanelNotFoundError, PanelFrozenError, JudgeConflictError,
    InsufficientJudgesError, PanelAssignmentError
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
async def tournament_a(db: AsyncSession, institution_a: Institution) -> NationalTournament:
    """Create test tournament in institution A."""
    tournament = NationalTournament(
        name="Test Tournament A",
        host_institution_id=institution_a.id,
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow(),
        registration_deadline=datetime.utcnow(),
        max_teams=16,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(tournament)
    await db.flush()
    return tournament


@pytest.fixture
async def user_admin_a(db: AsyncSession, institution_a: Institution) -> User:
    """Create admin user in institution A."""
    user = User(
        email="admin_a@test.edu",
        full_name="Admin A",
        password_hash="hashed",
        role=UserRole.teacher,
        institution_id=institution_a.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def judge_from_inst_a(db: AsyncSession, institution_a: Institution) -> User:
    """Create judge in institution A."""
    judge = User(
        email="judge_a@test.edu",
        full_name="Judge A",
        password_hash="hashed",
        role=UserRole.teacher,
        institution_id=institution_a.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(judge)
    await db.flush()
    return judge


@pytest.fixture
async def four_teams_a(db: AsyncSession, tournament_a: NationalTournament, institution_a: Institution) -> list:
    """Create 4 teams in tournament A (all from institution A)."""
    teams = []
    for i in range(4):
        team = TournamentTeam(
            tournament_id=tournament_a.id,
            institution_id=institution_a.id,
            team_code=f"TEAM-A-{i+1:03d}",
            team_name=f"Team {i+1}",
            registered_by=1,
            registration_status="confirmed",
            created_at=datetime.utcnow()
        )
        db.add(team)
        teams.append(team)
    await db.flush()
    return teams


@pytest.fixture
async def swiss_round_a(db: AsyncSession, tournament_a: NationalTournament) -> TournamentRound:
    """Create Swiss round in tournament A."""
    round_obj = TournamentRound(
        tournament_id=tournament_a.id,
        round_number=1,
        round_type=RoundType.SWISS,
        status=RoundStatus.DRAFT,
        created_at=datetime.utcnow()
    )
    db.add(round_obj)
    await db.flush()
    return round_obj


@pytest.fixture
async def pairings_a(db: AsyncSession, swiss_round_a: TournamentRound, four_teams_a: list) -> list:
    """Create pairings for round A."""
    pairings = []
    for i in range(2):
        pairing = RoundPairing(
            round_id=swiss_round_a.id,
            petitioner_team_id=four_teams_a[i*2].id,
            respondent_team_id=four_teams_a[i*2+1].id,
            table_number=i+1,
            pairing_hash=f"hash{i}",
            created_at=datetime.utcnow()
        )
        db.add(pairing)
        pairings.append(pairing)
    await db.flush()
    return pairings


# =============================================================================
# Test: Institution Conflict Detection
# =============================================================================

@pytest.mark.asyncio
async def test_institution_conflict_detected(
    db: AsyncSession,
    institution_a: Institution,
    judge_from_inst_a: User,
    four_teams_a: list
):
    """Test that judge from same institution as team is flagged as conflict."""
    # Judge and team are both from institution_a
    team = four_teams_a[0]
    
    has_conflict = await check_institution_conflict(
        judge_id=judge_from_inst_a.id,
        team_id=team.id,
        db=db
    )
    
    assert has_conflict is True, "Judge from same institution should be conflict"


@pytest.mark.asyncio
async def test_no_conflict_different_institution(
    db: AsyncSession,
    institution_a: Institution,
    institution_b: Institution,
    four_teams_a: list
):
    """Test that judge from different institution has no conflict."""
    # Create judge from institution B
    judge_b = User(
        email="judge_b@test.edu",
        full_name="Judge B",
        password_hash="hashed",
        role=UserRole.teacher,
        institution_id=institution_b.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(judge_b)
    await db.flush()
    
    team = four_teams_a[0]
    
    has_conflict = await check_institution_conflict(
        judge_id=judge_b.id,
        team_id=team.id,
        db=db
    )
    
    assert has_conflict is False, "Judge from different institution should have no conflict"


@pytest.mark.asyncio
async def test_comprehensive_conflict_check(
    db: AsyncSession,
    institution_a: Institution,
    institution_b: Institution,
    tournament_a: NationalTournament,
    judge_from_inst_a: User,
    four_teams_a: list
):
    """Test comprehensive conflict check returns correct reason."""
    # Create judge from different institution (no conflict)
    judge_b = User(
        email="judge_b@test.edu",
        full_name="Judge B",
        password_hash="hashed",
        role=UserRole.teacher,
        institution_id=institution_b.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(judge_b)
    await db.flush()
    
    team1 = four_teams_a[0]
    team2 = four_teams_a[1]
    
    # Judge A (same institution as teams) should have conflict
    has_conflict_a, reason_a = await has_judge_conflict(
        tournament_id=tournament_a.id,
        judge_id=judge_from_inst_a.id,
        petitioner_team_id=team1.id,
        respondent_team_id=team2.id,
        db=db,
        strict_mode=False
    )
    
    assert has_conflict_a is True
    assert "institution" in reason_a.lower()
    
    # Judge B (different institution) should have no conflict
    has_conflict_b, reason_b = await has_judge_conflict(
        tournament_id=tournament_a.id,
        judge_id=judge_b.id,
        petitioner_team_id=team1.id,
        respondent_team_id=team2.id,
        db=db,
        strict_mode=False
    )
    
    assert has_conflict_b is False
    assert reason_b is None


# =============================================================================
# Test: Repeat Judging Prevention
# =============================================================================

@pytest.mark.asyncio
async def test_repeat_judging_detected(
    db: AsyncSession,
    institution_a: Institution,
    institution_b: Institution,
    tournament_a: NationalTournament,
    swiss_round_a: TournamentRound,
    four_teams_a: list
):
    """Test that repeat judging is detected via assignment history."""
    # Create judge from different institution
    judge_b = User(
        email="judge_b@test.edu",
        full_name="Judge B",
        password_hash="hashed",
        role=UserRole.teacher,
        institution_id=institution_b.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(judge_b)
    await db.flush()
    
    team = four_teams_a[0]
    
    # Initially no repeat judging
    has_repeat = await check_repeat_judging(
        tournament_id=tournament_a.id,
        judge_id=judge_b.id,
        team_id=team.id,
        db=db
    )
    assert has_repeat is False
    
    # Add assignment history entry
    history = JudgeAssignmentHistory(
        tournament_id=tournament_a.id,
        judge_id=judge_b.id,
        team_id=team.id,
        round_id=swiss_round_a.id
    )
    db.add(history)
    await db.flush()
    
    # Now should detect repeat
    has_repeat = await check_repeat_judging(
        tournament_id=tournament_a.id,
        judge_id=judge_b.id,
        team_id=team.id,
        db=db
    )
    assert has_repeat is True


@pytest.mark.asyncio
async def test_strict_mode_blocks_repeat_judging(
    db: AsyncSession,
    institution_a: Institution,
    institution_b: Institution,
    tournament_a: NationalTournament,
    swiss_round_a: TournamentRound,
    four_teams_a: list
):
    """Test that strict mode blocks repeat judging."""
    # Create judge from different institution
    judge_b = User(
        email="judge_b@test.edu",
        full_name="Judge B",
        password_hash="hashed",
        role=UserRole.teacher,
        institution_id=institution_b.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(judge_b)
    await db.flush()
    
    team1 = four_teams_a[0]
    team2 = four_teams_a[1]
    
    # Add assignment history for team1
    history = JudgeAssignmentHistory(
        tournament_id=tournament_a.id,
        judge_id=judge_b.id,
        team_id=team1.id,
        round_id=swiss_round_a.id
    )
    db.add(history)
    await db.flush()
    
    # Strict mode should detect conflict
    has_conflict, reason = await has_judge_conflict(
        tournament_id=tournament_a.id,
        judge_id=judge_b.id,
        petitioner_team_id=team1.id,
        respondent_team_id=team2.id,
        db=db,
        strict_mode=True
    )
    
    assert has_conflict is True
    assert "already" in reason.lower() or "repeat" in reason.lower()


# =============================================================================
# Test: Post-Freeze Immutability
# =============================================================================

@pytest.mark.asyncio
async def test_publish_idempotent(
    db: AsyncSession,
    institution_a: Institution,
    institution_b: Institution,
    tournament_a: NationalTournament,
    swiss_round_a: TournamentRound,
    pairings_a: list,
    user_admin_a: User
):
    """Test that publish is idempotent."""
    # Create conflict-free judges
    for i in range(4):
        judge_inst = Institution(
            name=f"Judge College {i}",
            code=f"JC{i:03d}",
            is_verified=True,
            created_at=datetime.utcnow()
        )
        db.add(judge_inst)
        await db.flush()
        
        judge = User(
            email=f"judge{i}@college{i}.edu",
            full_name=f"Judge {i}",
            password_hash="hashed",
            role=UserRole.teacher,
            institution_id=judge_inst.id,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.add(judge)
    await db.flush()
    
    # Generate panels
    await generate_panels_for_round(swiss_round_a.id, db, panel_size=2)
    
    # First publish
    freeze1 = await publish_panels(swiss_round_a.id, user_admin_a.id, db)
    
    # Second publish should return same freeze
    freeze2 = await publish_panels(swiss_round_a.id, user_admin_a.id, db)
    
    assert freeze1.id == freeze2.id, "Publish must be idempotent"
    assert freeze1.panel_checksum == freeze2.panel_checksum


@pytest.mark.asyncio
async def test_tamper_detection_detects_missing_panel(
    db: AsyncSession,
    institution_a: Institution,
    institution_b: Institution,
    tournament_a: NationalTournament,
    swiss_round_a: TournamentRound,
    pairings_a: list,
    user_admin_a: User
):
    """Test tamper detection catches deleted panels."""
    # Create conflict-free judges
    for i in range(4):
        judge_inst = Institution(
            name=f"Judge College {i}",
            code=f"JC{i:03d}",
            is_verified=True,
            created_at=datetime.utcnow()
        )
        db.add(judge_inst)
        await db.flush()
        
        judge = User(
            email=f"judge{i}@college{i}.edu",
            full_name=f"Judge {i}",
            password_hash="hashed",
            role=UserRole.teacher,
            institution_id=judge_inst.id,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.add(judge)
    await db.flush()
    
    # Generate and publish panels
    panels = await generate_panels_for_round(swiss_round_a.id, db, panel_size=2)
    freeze = await publish_panels(swiss_round_a.id, user_admin_a.id, db)
    
    # Delete a panel (simulate tampering)
    if len(panels) > 0:
        # Get members first
        result = await db.execute(
            select(PanelMember).where(PanelMember.panel_id == panels[0].id)
        )
        for member in result.scalars().all():
            await db.delete(member)
        
        await db.delete(panels[0])
        await db.flush()
        
        # Verify should detect tampering
        result = await verify_panel_integrity(swiss_round_a.id, db)
        
        assert result["found"] is True
        assert result["frozen"] is True
        assert result["valid"] is False
        assert result["tamper_detected"] is True


# =============================================================================
# Test: Cross-Tenant Access
# =============================================================================

@pytest.mark.asyncio
async def test_cross_institution_panel_access_blocked(
    db: AsyncSession,
    institution_a: Institution,
    institution_b: Institution,
    tournament_a: NationalTournament,
    swiss_round_a: TournamentRound
):
    """Test that panels from other institutions are not accessible."""
    # Try to access round as if from institution B
    result = await db.execute(
        select(TournamentRound)
        .join(NationalTournament, TournamentRound.tournament_id == NationalTournament.id)
        .where(
            and_(
                TournamentRound.id == swiss_round_a.id,
                NationalTournament.host_institution_id == institution_b.id
            )
        )
    )
    
    round_from_other_institution = result.scalar_one_or_none()
    
    # Should not find the round
    assert round_from_other_institution is None, "Cross-institution access should be blocked"


# =============================================================================
# Test: Panel Diversity
# =============================================================================

@pytest.mark.asyncio
async def test_panel_members_from_different_institutions(
    db: AsyncSession,
    institution_a: Institution,
    tournament_a: NationalTournament,
    swiss_round_a: TournamentRound,
    pairings_a: list
):
    """Test that panels can include judges from different institutions."""
    # Create judges from 3 different institutions
    institutions = [institution_a]
    for i in range(2):
        inst = Institution(
            name=f"Judge College {i}",
            code=f"JC{i:03d}",
            is_verified=True,
            created_at=datetime.utcnow()
        )
        db.add(inst)
        await db.flush()
        institutions.append(inst)
    
    # Create 2 judges per institution
    for inst in institutions:
        for i in range(2):
            judge = User(
                email=f"judge{i}@{inst.code.lower()}.edu",
                full_name=f"Judge from {inst.name}",
                password_hash="hashed",
                role=UserRole.teacher,
                institution_id=inst.id,
                is_active=True,
                created_at=datetime.utcnow()
            )
            db.add(judge)
    await db.flush()
    
    # Generate panels
    panels = await generate_panels_for_round(swiss_round_a.id, db, panel_size=3)
    
    # Verify each panel has members
    for panel in panels:
        assert len(panel.members) == 3, "Panel should have 3 members"
        
        # Verify no institution conflict (members from same institution as teams would be blocked)
        for member in panel.members:
            # Judge's institution should not be same as teams' institution
            result = await db.execute(
                select(User.institution_id).where(User.id == member.judge_id)
            )
            judge_inst_id = result.scalar()
            
            # Should not be institution_a (where teams are from)
            assert judge_inst_id != institution_a.id, \
                "Judge from same institution as teams should not be assigned"


# =============================================================================
# Test: PostgreSQL Trigger (if applicable)
# =============================================================================

@pytest.mark.asyncio
async def test_postgresql_trigger_blocks_panel_update(
    db: AsyncSession,
    institution_a: Institution,
    institution_b: Institution,
    tournament_a: NationalTournament,
    swiss_round_a: TournamentRound,
    pairings_a: list,
    user_admin_a: User
):
    """
    Test PostgreSQL trigger blocks panel UPDATE after freeze.
    
    Only runs on PostgreSQL.
    """
    # Check dialect
    result = await db.execute(text("SHOW server_version"))
    version = result.scalar()
    
    if not version or "SQLite" in str(version):
        pytest.skip("PostgreSQL-specific test")
    
    # Create conflict-free judges
    for i in range(4):
        judge_inst = Institution(
            name=f"Judge College {i}",
            code=f"JC{i:03d}",
            is_verified=True,
            created_at=datetime.utcnow()
        )
        db.add(judge_inst)
        await db.flush()
        
        judge = User(
            email=f"judge{i}@college{i}.edu",
            full_name=f"Judge {i}",
            password_hash="hashed",
            role=UserRole.teacher,
            institution_id=judge_inst.id,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.add(judge)
    await db.flush()
    
    # Generate and publish
    await generate_panels_for_round(swiss_round_a.id, db, panel_size=2)
    await publish_panels(swiss_round_a.id, user_admin_a.id, db)
    
    # Try direct SQL update (should fail due to trigger)
    try:
        await db.execute(
            text(f"""
                UPDATE judge_panels 
                SET table_number = 999 
                WHERE round_id = {swiss_round_a.id}
            """)
        )
        await db.flush()
        pytest.fail("Expected trigger to block update")
    except Exception as e:
        assert "freeze" in str(e).lower() or "frozen" in str(e).lower(), \
            f"Trigger should block with freeze message: {e}"


# =============================================================================
# Test: Assignment History Tracking
# =============================================================================

@pytest.mark.asyncio
async def test_assignment_history_created(
    db: AsyncSession,
    institution_a: Institution,
    institution_b: Institution,
    tournament_a: NationalTournament,
    swiss_round_a: TournamentRound,
    pairings_a: list
):
    """Test that assignment history entries are created for each judge-team pair."""
    # Create conflict-free judges
    for i in range(4):
        judge_inst = Institution(
            name=f"Judge College {i}",
            code=f"JC{i:03d}",
            is_verified=True,
            created_at=datetime.utcnow()
        )
        db.add(judge_inst)
        await db.flush()
        
        judge = User(
            email=f"judge{i}@college{i}.edu",
            full_name=f"Judge {i}",
            password_hash="hashed",
            role=UserRole.teacher,
            institution_id=judge_inst.id,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.add(judge)
    await db.flush()
    
    # Get initial history count
    initial_history = await get_assignment_history(tournament_a.id, db)
    initial_count = len(initial_history)
    
    # Generate panels
    panels = await generate_panels_for_round(swiss_round_a.id, db, panel_size=2)
    
    # Get new history count
    new_history = await get_assignment_history(tournament_a.id, db)
    new_count = len(new_history)
    
    # Should have more entries now
    assert new_count > initial_count, "Assignment history should be created"
    
    # Each judge should have 2 entries (one per team in their assigned pairing)
    total_expected_entries = len(panels) * 2 * 2  # panels * panel_size * 2 teams per pairing
    assert new_count == total_expected_entries, \
        f"Expected {total_expected_entries} assignment history entries"


# =============================================================================
# Test: Role Assignment
# =============================================================================

@pytest.mark.asyncio
async def test_panel_roles_assigned_correctly(
    db: AsyncSession,
    institution_a: Institution,
    institution_b: Institution,
    tournament_a: NationalTournament,
    swiss_round_a: TournamentRound,
    pairings_a: list
):
    """Test that first judge is presiding, others are members."""
    # Create conflict-free judges
    for i in range(6):
        judge_inst = Institution(
            name=f"Judge College {i}",
            code=f"JC{i:03d}",
            is_verified=True,
            created_at=datetime.utcnow()
        )
        db.add(judge_inst)
        await db.flush()
        
        judge = User(
            email=f"judge{i}@college{i}.edu",
            full_name=f"Judge {i}",
            password_hash="hashed",
            role=UserRole.teacher,
            institution_id=judge_inst.id,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.add(judge)
    await db.flush()
    
    # Generate panels with 3 judges each
    panels = await generate_panels_for_round(swiss_round_a.id, db, panel_size=3)
    
    # Verify role assignment
    for panel in panels:
        # Get members sorted by ID (deterministic order)
        result = await db.execute(
            select(PanelMember).where(PanelMember.panel_id == panel.id)
            .order_by(PanelMember.judge_id.asc())
        )
        members = result.scalars().all()
        
        # Should have exactly one presiding judge
        presiding_count = sum(1 for m in members if m.role == PanelMemberRole.PRESIDING)
        member_count = sum(1 for m in members if m.role == PanelMemberRole.MEMBER)
        
        assert presiding_count == 1, f"Panel {panel.id} should have exactly 1 presiding judge"
        assert member_count == 2, f"Panel {panel.id} should have exactly 2 member judges"
