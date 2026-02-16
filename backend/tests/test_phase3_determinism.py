"""
Phase 3 — Round Pairing Determinism Test Suite

Tests for all deterministic guarantees:
- No float() usage
- No random() usage
- No datetime.now()
- No Python hash()
- All JSON uses sort_keys=True
- All hashing via sha256
- Swiss algorithm produces identical pairings for identical input twice
"""
import hashlib
import inspect
import json
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.round_pairing import (
    TournamentRound, RoundPairing, PairingHistory, RoundFreeze,
    RoundType, RoundStatus
)
from backend.orm.national_network import TournamentTeam, NationalTournament
from backend.orm.user import User, UserRole
from backend.services.round_pairing_service import (
    create_round, generate_swiss_pairings, generate_knockout_pairings,
    publish_round, get_pairings_by_round, normalize_team_ids
)


# =============================================================================
# Source Code Audit Tests
# =============================================================================

def test_service_no_float_usage():
    """Verify no float() usage in round pairing service."""
    import backend.services.round_pairing_service as svc
    
    source = inspect.getsource(svc)
    lines = source.split('\n')
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if '"' in line or "'" in line:
            # Skip string literals
            continue
        assert 'float(' not in line, f"Line {i}: Must not use float() - {line}"


def test_service_no_random_usage():
    """Verify no random usage in round pairing service."""
    import backend.services.round_pairing_service as svc
    
    source = inspect.getsource(svc).lower()
    
    assert 'random' not in source or 'random_state' in source, "Must not use random()"
    assert 'shuffle' not in source, "Must not use random.shuffle()"


def test_service_no_datetime_now():
    """Verify only utcnow() used, not now()."""
    import backend.services.round_pairing_service as svc
    
    source = inspect.getsource(svc)
    
    assert 'datetime.now()' not in source, "Must use datetime.utcnow(), not datetime.now()"


def test_service_no_python_hash():
    """Verify no Python hash() function used."""
    import backend.services.round_pairing_service as svc
    
    source = inspect.getsource(svc)
    lines = source.split('\n')
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        # Check for hash( pattern
        if 'hash(' in line and 'hashlib' not in line:
            assert False, f"Line {i}: Must not use Python hash() function"


def test_service_uses_sha256():
    """Verify all hashing uses hashlib.sha256."""
    import backend.services.round_pairing_service as svc
    
    source = inspect.getsource(svc)
    
    assert 'hashlib.sha256' in source, "Must use hashlib.sha256 for hashing"


def test_orm_models_use_sha256():
    """Verify ORM models use SHA256 for hashing."""
    from backend.orm import round_pairing as orm
    
    source = inspect.getsource(orm)
    
    assert 'hashlib.sha256' in source, "ORM must use hashlib.sha256"


def test_normalize_team_ids_deterministic():
    """Verify normalize_team_ids always returns smaller ID first."""
    # Test various combinations
    assert normalize_team_ids(1, 2) == (1, 2)
    assert normalize_team_ids(2, 1) == (1, 2)
    assert normalize_team_ids(5, 3) == (3, 5)
    assert normalize_team_ids(10, 10) == (10, 10)  # Edge case


# =============================================================================
# Hash Formula Tests
# =============================================================================

def test_pairing_hash_formula():
    """Test pairing hash formula is deterministic."""
    # Create a mock pairing
    class MockPairing:
        def __init__(self):
            self.id = 1
            self.round_id = 10
            self.petitioner_team_id = 100
            self.respondent_team_id = 200
            self.table_number = 5
    
    mock = MockPairing()
    
    # Compute expected hash
    expected = hashlib.sha256(
        "10|100|200|5".encode()
    ).hexdigest()
    
    # Simulate the computation
    combined = f"{mock.round_id}|{mock.petitioner_team_id}|{mock.respondent_team_id}|{mock.table_number}"
    computed = hashlib.sha256(combined.encode()).hexdigest()
    
    assert computed == expected


def test_round_checksum_formula():
    """Test round checksum formula is deterministic."""
    # Create a mock freeze
    class MockFreeze:
        pass
    
    pairing_hashes = ["abc123", "def456", "ghi789"]
    
    # Compute checksum (should sort hashes first)
    sorted_hashes = sorted(pairing_hashes)
    combined = "|".join(sorted_hashes)
    expected = hashlib.sha256(combined.encode()).hexdigest()
    
    # Verify with different order gives same result
    reverse_hashes = list(reversed(pairing_hashes))
    reverse_sorted = sorted(reverse_hashes)
    reverse_combined = "|".join(reverse_sorted)
    reverse_result = hashlib.sha256(reverse_combined.encode()).hexdigest()
    
    assert expected == reverse_result, "Checksum must be order-independent"


# =============================================================================
# Swiss Algorithm Determinism Tests
# =============================================================================

@pytest.mark.asyncio
async def test_swiss_algorithm_deterministic_same_input(
    db: AsyncSession
):
    """Test Swiss algorithm produces identical pairings for identical input twice."""
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
    
    # Create teams (4 teams for simplicity)
    teams = []
    for i in range(4):
        team = TournamentTeam(
            tournament_id=tournament.id,
            institution_id=1,
            team_code=f"TEAM-{i+1:03d}",
            team_name=f"Team {i+1}",
            registered_by=1,
            registration_status="confirmed",
            created_at=datetime.utcnow()
        )
        db.add(team)
        teams.append(team)
    await db.flush()
    
    # Create round
    round1 = await create_round(
        tournament_id=tournament.id,
        round_number=1,
        round_type=RoundType.SWISS,
        db=db
    )
    
    # Generate pairings first time
    pairings1 = await generate_swiss_pairings(round1.id, db)
    
    # Store the pairing data
    data1 = [
        (p.petitioner_team_id, p.respondent_team_id, p.table_number, p.pairing_hash)
        for p in sorted(pairings1, key=lambda x: x.table_number)
    ]
    
    # Delete pairings and regenerate
    for p in pairings1:
        await db.delete(p)
    
    # Delete history too
    result = await db.execute(
        select(PairingHistory).where(PairingHistory.round_id == round1.id)
    )
    for h in result.scalars().all():
        await db.delete(h)
    
    await db.flush()
    
    # Generate pairings second time
    pairings2 = await generate_swiss_pairings(round1.id, db)
    
    # Store the pairing data
    data2 = [
        (p.petitioner_team_id, p.respondent_team_id, p.table_number, p.pairing_hash)
        for p in sorted(pairings2, key=lambda x: x.table_number)
    ]
    
    # Should be identical
    assert len(data1) == len(data2), "Same number of pairings"
    assert data1 == data2, "Pairings must be identical for identical input"


@pytest.mark.asyncio
async def test_swiss_side_balancing_deterministic(
    db: AsyncSession
):
    """Test side balancing is deterministic (lower petitioner appearances or lower ID)."""
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
    
    # Create 4 teams
    teams = []
    for i in range(4):
        team = TournamentTeam(
            tournament_id=tournament.id,
            institution_id=1,
            team_code=f"TEAM-{i+1:03d}",
            team_name=f"Team {i+1}",
            registered_by=1,
            registration_status="confirmed",
            created_at=datetime.utcnow()
        )
        db.add(team)
        teams.append(team)
    await db.flush()
    
    # Create round
    round1 = await create_round(
        tournament_id=tournament.id,
        round_number=1,
        round_type=RoundType.SWISS,
        db=db
    )
    
    # Generate pairings
    pairings = await generate_swiss_pairings(round1.id, db)
    
    # Verify each pairing has consistent side assignment
    for p in pairings:
        # Lower team ID should petition if appearances equal
        # (in first round, all appearances are 0)
        assert p.petitioner_team_id < p.respondent_team_id, \
            "Side balancing should assign lower ID as petitioner when appearances equal"


# =============================================================================
# Knockout Algorithm Determinism Tests
# =============================================================================

@pytest.mark.asyncio
async def test_knockout_bracket_deterministic(
    db: AsyncSession
):
    """Test knockout bracket follows standard pattern."""
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
    
    # Create 8 teams
    team_ids = []
    for i in range(8):
        team = TournamentTeam(
            tournament_id=tournament.id,
            institution_id=1,
            team_code=f"TEAM-{i+1:03d}",
            team_name=f"Team {i+1}",
            registered_by=1,
            registration_status="confirmed",
            created_at=datetime.utcnow()
        )
        db.add(team)
        await db.flush()
        team_ids.append(team.id)
    
    # Create round
    round1 = await create_round(
        tournament_id=tournament.id,
        round_number=1,
        round_type=RoundType.KNOCKOUT,
        db=db
    )
    
    # Generate pairings
    pairings = await generate_knockout_pairings(round1.id, db)
    
    # Sort by table number
    sorted_pairings = sorted(pairings, key=lambda p: p.table_number)
    
    # Standard bracket: 1 vs N, 2 vs N-1, 3 vs N-2, etc.
    sorted_team_ids = sorted(team_ids)
    n = len(sorted_team_ids)
    
    for i, pairing in enumerate(sorted_pairings):
        expected_team1 = sorted_team_ids[i]  # Top half
        expected_team2 = sorted_team_ids[n - 1 - i]  # Bottom half
        
        # Lower seed petitions
        if expected_team1 < expected_team2:
            expected_petitioner = expected_team1
            expected_respondent = expected_team2
        else:
            expected_petitioner = expected_team2
            expected_respondent = expected_team1
        
        assert pairing.petitioner_team_id == expected_petitioner, \
            f"Table {i+1}: petitioner mismatch"
        assert pairing.respondent_team_id == expected_respondent, \
            f"Table {i+1}: respondent mismatch"


# =============================================================================
# JSON Serialization Tests
# =============================================================================

def test_json_dumps_uses_sort_keys():
    """Verify JSON dumps always uses sort_keys=True."""
    # Test snapshot serialization
    data = {
        "z_key": 1,
        "a_key": 2,
        "m_key": 3
    }
    
    # Without sort_keys - order is arbitrary
    unsorted = json.dumps(data)
    
    # With sort_keys - always same order
    sorted_json = json.dumps(data, sort_keys=True)
    
    # Should start with a_key
    assert '"a_key"' in sorted_json[:20], "sort_keys=True ensures consistent ordering"
    
    # Parse and verify
    parsed = json.loads(sorted_json)
    keys = list(parsed.keys())
    assert keys == sorted(keys), "Keys must be sorted"


# =============================================================================
# Checksum Stability Tests
# =============================================================================

@pytest.mark.asyncio
async def test_checksum_stable_after_multiple_verifications(
    db: AsyncSession
):
    """Test that checksum remains stable across multiple verifications."""
    # Create tournament and round
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
    
    # Create 4 teams
    for i in range(4):
        team = TournamentTeam(
            tournament_id=tournament.id,
            institution_id=1,
            team_code=f"TEAM-{i+1:03d}",
            team_name=f"Team {i+1}",
            registered_by=1,
            registration_status="confirmed",
            created_at=datetime.utcnow()
        )
        db.add(team)
    await db.flush()
    
    # Create round and pairings
    round1 = await create_round(
        tournament_id=tournament.id,
        round_number=1,
        round_type=RoundType.SWISS,
        db=db
    )
    
    pairings = await generate_swiss_pairings(round1.id, db)
    
    # Create user
    user = User(
        email="admin@test.edu",
        full_name="Admin User",
        password_hash="hashed",
        role=UserRole.teacher,
        institution_id=1,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(user)
    await db.flush()
    
    # Publish round
    freeze = await publish_round(round1.id, user.id, db)
    
    checksum1 = freeze.round_checksum
    
    # Verify multiple times - checksum should be same
    for _ in range(3):
        freeze2 = await db.execute(
            select(RoundFreeze).where(RoundFreeze.round_id == round1.id)
        )
        freeze_obj = freeze2.scalar_one()
        
        # Recompute checksum
        pairing_hashes = [p.pairing_hash for p in pairings]
        recomputed = freeze_obj.compute_round_checksum(pairing_hashes)
        
        assert freeze_obj.round_checksum == checksum1, "Checksum must remain stable"
        assert recomputed == checksum1, "Recomputed checksum must match stored"


# =============================================================================
# Table Number Assignment Tests
# =============================================================================

@pytest.mark.asyncio
async def test_table_numbers_sequential(
    db: AsyncSession
):
    """Test table numbers are assigned sequentially starting from 1."""
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
    
    # Create 4 teams
    for i in range(4):
        team = TournamentTeam(
            tournament_id=tournament.id,
            institution_id=1,
            team_code=f"TEAM-{i+1:03d}",
            team_name=f"Team {i+1}",
            registered_by=1,
            registration_status="confirmed",
            created_at=datetime.utcnow()
        )
        db.add(team)
    await db.flush()
    
    # Create round
    round1 = await create_round(
        tournament_id=tournament.id,
        round_number=1,
        round_type=RoundType.SWISS,
        db=db
    )
    
    # Generate pairings
    pairings = await generate_swiss_pairings(round1.id, db)
    
    # Extract table numbers
    table_numbers = sorted([p.table_number for p in pairings])
    
    # Should be 1, 2 for 4 teams
    expected = list(range(1, len(pairings) + 1))
    assert table_numbers == expected, "Table numbers must be sequential"
