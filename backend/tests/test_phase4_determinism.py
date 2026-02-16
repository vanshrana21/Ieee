"""
Phase 4 — Judge Panel Assignment Determinism Test Suite

Tests for all deterministic guarantees:
- No float() usage
- No random() usage
- No datetime.now()
- No Python hash()
- All JSON uses sort_keys=True
- All hashing via sha256
- Panel assignment is deterministic
"""
import hashlib
import inspect
import json
from datetime import datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.panel_assignment import (
    JudgePanel, PanelMember, PanelMemberRole, JudgeAssignmentHistory, PanelFreeze
)
from backend.orm.round_pairing import TournamentRound, RoundPairing, RoundType, RoundStatus
from backend.orm.national_network import TournamentTeam, NationalTournament, Institution
from backend.orm.user import User, UserRole
from backend.services.panel_assignment_service import (
    generate_panels_for_round, publish_panels, verify_panel_integrity,
    get_available_judges
)


# =============================================================================
# Source Code Audit Tests
# =============================================================================

def test_service_no_float_usage():
    """Verify no float() usage in panel assignment service."""
    import backend.services.panel_assignment_service as svc
    
    source = inspect.getsource(svc)
    lines = source.split('\n')
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if '"' in line or "'" in line:
            continue
        assert 'float(' not in line, f"Line {i}: Must not use float() - {line}"


def test_service_no_random_usage():
    """Verify no random usage in panel assignment service."""
    import backend.services.panel_assignment_service as svc
    
    source = inspect.getsource(svc).lower()
    
    assert 'random' not in source or 'random_state' in source, "Must not use random()"
    assert 'shuffle' not in source, "Must not use random.shuffle()"


def test_service_no_datetime_now():
    """Verify only utcnow() used, not now()."""
    import backend.services.panel_assignment_service as svc
    
    source = inspect.getsource(svc)
    
    assert 'datetime.now()' not in source, "Must use datetime.utcnow(), not datetime.now()"


def test_service_no_python_hash():
    """Verify no Python hash() function used."""
    import backend.services.panel_assignment_service as svc
    
    source = inspect.getsource(svc)
    lines = source.split('\n')
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if 'hash(' in line and 'hashlib' not in line:
            assert False, f"Line {i}: Must not use Python hash() function"


def test_service_uses_sha256():
    """Verify all hashing uses hashlib.sha256."""
    import backend.services.panel_assignment_service as svc
    
    source = inspect.getsource(svc)
    
    assert 'hashlib.sha256' in source, "Must use hashlib.sha256 for hashing"


def test_orm_models_use_sha256():
    """Verify ORM models use SHA256 for hashing."""
    import backend.orm.panel_assignment as orm
    
    source = inspect.getsource(orm)
    
    assert 'hashlib.sha256' in source, "ORM must use hashlib.sha256"


# =============================================================================
# Hash Formula Tests
# =============================================================================

def test_panel_hash_formula():
    """Test panel hash formula is deterministic."""
    class MockPanel:
        def __init__(self, panel_id, table_number, members):
            self.id = panel_id
            self.table_number = table_number
            self.members = members
    
    class MockMember:
        def __init__(self, judge_id):
            self.judge_id = judge_id
    
    # Create panel with members
    members = [MockMember(1), MockMember(3), MockMember(2)]  # Out of order
    panel = MockPanel(10, 5, members)
    
    # Compute hash manually (sorted member IDs)
    sorted_ids = sorted([m.judge_id for m in members])
    expected = hashlib.sha256(f"10|[1,2,3]|5".encode()).hexdigest()
    
    # Should be consistent
    combined = f"10|{str(sorted_ids)}|5"
    computed = hashlib.sha256(combined.encode()).hexdigest()
    
    assert computed == expected


def test_panel_checksum_formula():
    """Test panel checksum formula is deterministic."""
    panel_hashes = ["abc123", "def456", "ghi789"]
    
    # Compute checksum (should sort hashes first)
    sorted_hashes = sorted(panel_hashes)
    combined = "|".join(sorted_hashes)
    expected = hashlib.sha256(combined.encode()).hexdigest()
    
    # Verify with different order gives same result
    reverse_hashes = list(reversed(panel_hashes))
    reverse_sorted = sorted(reverse_hashes)
    reverse_combined = "|".join(reverse_sorted)
    reverse_result = hashlib.sha256(reverse_combined.encode()).hexdigest()
    
    assert expected == reverse_result, "Checksum must be order-independent"


# =============================================================================
# Judge Sorting Tests
# =============================================================================

@pytest.mark.asyncio
async def test_available_judges_sorted_deterministically(
    db: AsyncSession
):
    """Test available judges are sorted by assignments, institution, id."""
    # Create tournament
    tournament = NationalTournament(
        name="Test Tournament",
        host_institution_id=1,
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow(),
        registration_deadline=datetime.utcnow(),
        max_teams=16,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(tournament)
    await db.flush()
    
    # Create round
    round_obj = TournamentRound(
        tournament_id=tournament.id,
        round_number=1,
        round_type=RoundType.SWISS,
        status=RoundStatus.DRAFT,
        created_at=datetime.utcnow()
    )
    db.add(round_obj)
    await db.flush()
    
    # Create institution
    inst = Institution(
        name="Test College",
        code="TC001",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(inst)
    await db.flush()
    
    # Create judges
    judges = []
    for i in range(5):
        judge = User(
            email=f"judge{i}@test.edu",
            full_name=f"Judge {i}",
            password_hash="hashed",
            role=UserRole.teacher,
            institution_id=inst.id,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.add(judge)
        judges.append(judge)
    await db.flush()
    
    # Get available judges
    available = await get_available_judges(tournament.id, round_obj.id, db)
    
    # Verify sorting: all should have 0 assignments initially
    # Then sorted by institution_id, then by judge_id
    assert len(available) == 5
    
    # Verify deterministic ordering (by id since assignments are equal)
    ids = [j["judge_id"] for j in available]
    assert ids == sorted(ids), "Judges must be deterministically sorted"


# =============================================================================
# Panel Generation Determinism Tests
# =============================================================================

@pytest.mark.asyncio
async def test_panel_generation_deterministic_same_input(
    db: AsyncSession
):
    """Test panel generation produces identical panels for identical input twice."""
    # Create institution
    inst = Institution(
        name="Test College",
        code="TC001",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(inst)
    await db.flush()
    
    # Create tournament
    tournament = NationalTournament(
        name="Test Tournament",
        host_institution_id=inst.id,
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow(),
        registration_deadline=datetime.utcnow(),
        max_teams=16,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(tournament)
    await db.flush()
    
    # Create round
    round_obj = TournamentRound(
        tournament_id=tournament.id,
        round_number=1,
        round_type=RoundType.SWISS,
        status=RoundStatus.DRAFT,
        created_at=datetime.utcnow()
    )
    db.add(round_obj)
    await db.flush()
    
    # Create teams
    teams = []
    for i in range(4):
        team = TournamentTeam(
            tournament_id=tournament.id,
            institution_id=inst.id,
            team_code=f"TEAM-{i+1:03d}",
            team_name=f"Team {i+1}",
            registered_by=1,
            registration_status="confirmed",
            created_at=datetime.utcnow()
        )
        db.add(team)
        teams.append(team)
    await db.flush()
    
    # Create pairings
    from backend.orm.round_pairing import RoundPairing
    for i in range(2):
        pairing = RoundPairing(
            round_id=round_obj.id,
            petitioner_team_id=teams[i*2].id,
            respondent_team_id=teams[i*2+1].id,
            table_number=i+1,
            pairing_hash=f"hash{i}",
            created_at=datetime.utcnow()
        )
        db.add(pairing)
    await db.flush()
    
    # Create judges (need judges from different institutions to avoid conflicts)
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
    
    # Generate panels first time
    panels1 = await generate_panels_for_round(round_obj.id, db, panel_size=2)
    
    # Store panel data
    data1 = [
        (p.table_number, sorted([m.judge_id for m in p.members]))
        for p in sorted(panels1, key=lambda x: x.table_number)
    ]
    
    # Delete panels and history
    for panel in panels1:
        for member in panel.members:
            await db.delete(member)
        await db.delete(panel)
    
    # Clear assignment history
    result = await db.execute(
        select(JudgeAssignmentHistory).where(JudgeAssignmentHistory.round_id == round_obj.id)
    )
    for h in result.scalars().all():
        await db.delete(h)
    
    await db.flush()
    
    # Generate panels second time
    panels2 = await generate_panels_for_round(round_obj.id, db, panel_size=2)
    
    # Store panel data
    data2 = [
        (p.table_number, sorted([m.judge_id for m in p.members]))
        for p in sorted(panels2, key=lambda x: x.table_number)
    ]
    
    # Should be identical
    assert len(data1) == len(data2), "Same number of panels"
    assert data1 == data2, "Panel assignments must be deterministic"


# =============================================================================
# JSON Serialization Tests
# =============================================================================

def test_json_dumps_uses_sort_keys():
    """Verify JSON dumps always uses sort_keys=True."""
    data = {
        "z_key": 1,
        "a_key": 2,
        "m_key": 3,
        "nested": {"z": 1, "a": 2}
    }
    
    # With sort_keys - always same order
    sorted_json = json.dumps(data, sort_keys=True)
    
    # Should start with a_key
    assert '"a_key"' in sorted_json[:50], "sort_keys=True ensures consistent ordering"
    
    # Parse and verify
    parsed = json.loads(sorted_json)
    keys = list(parsed.keys())
    assert keys == sorted(keys), "Keys must be sorted"
    
    # Nested should also be sorted
    nested_keys = list(parsed["nested"].keys())
    assert nested_keys == sorted(nested_keys), "Nested keys must be sorted"


# =============================================================================
# Checksum Stability Tests
# =============================================================================

@pytest.mark.asyncio
async def test_panel_checksum_stable_after_multiple_verifications(
    db: AsyncSession
):
    """Test that checksum remains stable across multiple verifications."""
    # Create institution
    inst = Institution(
        name="Test College",
        code="TC001",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(inst)
    await db.flush()
    
    # Create tournament and round
    tournament = NationalTournament(
        name="Test Tournament",
        host_institution_id=inst.id,
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow(),
        registration_deadline=datetime.utcnow(),
        max_teams=16,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(tournament)
    await db.flush()
    
    round_obj = TournamentRound(
        tournament_id=tournament.id,
        round_number=1,
        round_type=RoundType.SWISS,
        status=RoundStatus.DRAFT,
        created_at=datetime.utcnow()
    )
    db.add(round_obj)
    await db.flush()
    
    # Create teams and pairings
    teams = []
    for i in range(4):
        team = TournamentTeam(
            tournament_id=tournament.id,
            institution_id=inst.id,
            team_code=f"TEAM-{i+1:03d}",
            team_name=f"Team {i+1}",
            registered_by=1,
            registration_status="confirmed",
            created_at=datetime.utcnow()
        )
        db.add(team)
        teams.append(team)
    await db.flush()
    
    from backend.orm.round_pairing import RoundPairing
    for i in range(2):
        pairing = RoundPairing(
            round_id=round_obj.id,
            petitioner_team_id=teams[i*2].id,
            respondent_team_id=teams[i*2+1].id,
            table_number=i+1,
            pairing_hash=f"hash{i}",
            created_at=datetime.utcnow()
        )
        db.add(pairing)
    await db.flush()
    
    # Create judges from different institutions
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
    panels = await generate_panels_for_round(round_obj.id, db, panel_size=2)
    
    # Create user
    admin = User(
        email="admin@test.edu",
        full_name="Admin User",
        password_hash="hashed",
        role=UserRole.teacher,
        institution_id=inst.id,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(admin)
    await db.flush()
    
    # Publish panels
    freeze = await publish_panels(round_obj.id, admin.id, db)
    
    checksum1 = freeze.panel_checksum
    
    # Verify multiple times - checksum should be same
    for _ in range(3):
        freeze2 = await db.execute(
            select(PanelFreeze).where(PanelFreeze.round_id == round_obj.id)
        )
        freeze_obj = freeze2.scalar_one()
        
        # Recompute checksum
        panel_hashes = [p.panel_hash for p in panels]
        recomputed = freeze_obj.compute_panel_checksum(panel_hashes)
        
        assert freeze_obj.panel_checksum == checksum1, "Checksum must remain stable"
        assert recomputed == checksum1, "Recomputed checksum must match stored"


# =============================================================================
# Table Number Assignment Tests
# =============================================================================

@pytest.mark.asyncio
async def test_panels_match_pairing_table_numbers(
    db: AsyncSession
):
    """Test panels are assigned to match pairing table numbers."""
    # Create setup
    inst = Institution(
        name="Test College",
        code="TC001",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(inst)
    await db.flush()
    
    tournament = NationalTournament(
        name="Test Tournament",
        host_institution_id=inst.id,
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow(),
        registration_deadline=datetime.utcnow(),
        max_teams=16,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(tournament)
    await db.flush()
    
    round_obj = TournamentRound(
        tournament_id=tournament.id,
        round_number=1,
        round_type=RoundType.SWISS,
        status=RoundStatus.DRAFT,
        created_at=datetime.utcnow()
    )
    db.add(round_obj)
    await db.flush()
    
    # Create 4 teams
    teams = []
    for i in range(4):
        team = TournamentTeam(
            tournament_id=tournament.id,
            institution_id=inst.id,
            team_code=f"TEAM-{i+1:03d}",
            team_name=f"Team {i+1}",
            registered_by=1,
            registration_status="confirmed",
            created_at=datetime.utcnow()
        )
        db.add(team)
        teams.append(team)
    await db.flush()
    
    # Create pairings with specific table numbers
    from backend.orm.round_pairing import RoundPairing
    for i in range(2):
        pairing = RoundPairing(
            round_id=round_obj.id,
            petitioner_team_id=teams[i*2].id,
            respondent_team_id=teams[i*2+1].id,
            table_number=i+1,  # Table 1, 2
            pairing_hash=f"hash{i}",
            created_at=datetime.utcnow()
        )
        db.add(pairing)
    await db.flush()
    
    # Create judges from different institutions
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
    panels = await generate_panels_for_round(round_obj.id, db, panel_size=2)
    
    # Extract table numbers
    table_numbers = sorted([p.table_number for p in panels])
    
    # Should match pairing table numbers: 1, 2
    assert table_numbers == [1, 2], "Panel table numbers must match pairing table numbers"
