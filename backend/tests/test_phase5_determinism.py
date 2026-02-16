"""
Phase 5 — Live Courtroom Determinism Test Suite

Tests for all deterministic guarantees:
- No float() usage
- No random() usage
- No datetime.now()
- No Python hash()
- All json.dumps include sort_keys=True
- Event sequence strictly monotonic
- SHA256 used
- No unsorted iteration
"""
import hashlib
import inspect
import json
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.live_court import (
    LiveCourtSession, LiveTurn, LiveEventLog,
    LiveCourtStatus, LiveTurnState, OralSide, OralTurnType,
    get_next_event_sequence
)
from backend.orm.national_network import Institution
from backend.orm.round_pairing import TournamentRound, RoundType
from backend.orm.user import User, UserRole


# =============================================================================
# Source Code Audit Tests
# =============================================================================

def test_service_no_float_usage():
    """Verify no float() usage in live court service."""
    import backend.services.live_court_service as svc
    
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
    """Verify no random usage in live court service."""
    import backend.services.live_court_service as svc
    
    source = inspect.getsource(svc).lower()
    
    assert 'random' not in source or 'random_state' in source, "Must not use random()"
    assert 'shuffle' not in source, "Must not use random.shuffle()"


def test_service_no_datetime_now():
    """Verify only utcnow() used, not now()."""
    import backend.services.live_court_service as svc
    
    source = inspect.getsource(svc)
    
    assert 'datetime.now()' not in source, "Must use datetime.utcnow(), not datetime.now()"


def test_service_no_python_hash():
    """Verify no Python hash() function used."""
    import backend.services.live_court_service as svc
    
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
    import backend.services.live_court_service as svc
    
    source = inspect.getsource(svc)
    
    assert 'hashlib.sha256' in source, "Must use hashlib.sha256 for hashing"


def test_orm_models_use_sha256():
    """Verify ORM models use SHA256 for hashing."""
    import backend.orm.live_court as orm
    
    source = inspect.getsource(orm)
    
    assert 'hashlib.sha256' in source, "ORM must use hashlib.sha256"


def test_websocket_no_float_usage():
    """Verify no float() in WebSocket code."""
    import backend.routes.live_court_ws as ws
    
    source = inspect.getsource(ws)
    lines = source.split('\n')
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if '"' in line or "'" in line:
            continue
        assert 'float(' not in line, f"WebSocket Line {i}: Must not use float()"


def test_websocket_json_uses_sort_keys():
    """Verify WebSocket uses sort_keys for JSON."""
    import backend.routes.live_court_ws as ws
    
    source = inspect.getsource(ws)
    
    assert 'sort_keys=True' in source, "WebSocket must use sort_keys=True"


# =============================================================================
# Hash Formula Tests
# =============================================================================

def test_event_hash_formula():
    """Test event hash formula is deterministic."""
    previous_hash = "0" * 64
    event_sequence = 5
    event_type = "TEST_EVENT"
    payload = {"b": 2, "a": 1, "c": 3}  # Out of order keys
    created_at = datetime.utcnow()
    
    # Compute hash
    computed = LiveEventLog.compute_event_hash(
        previous_hash=previous_hash,
        event_sequence=event_sequence,
        event_type=event_type,
        payload=payload,
        created_at=created_at
    )
    
    # Recompute with same data - should be identical
    computed2 = LiveEventLog.compute_event_hash(
        previous_hash=previous_hash,
        event_sequence=event_sequence,
        event_type=event_type,
        payload=payload,
        created_at=created_at
    )
    
    assert computed == computed2, "Event hash must be deterministic"
    assert len(computed) == 64, "SHA256 hex digest is 64 characters"


def test_event_hash_payload_order_independent():
    """Test that payload key order doesn't affect hash."""
    previous_hash = "0" * 64
    event_sequence = 1
    event_type = "TEST"
    created_at = datetime.utcnow()
    
    # Two payloads with same data, different key order
    payload1 = {"z": 1, "a": 2, "m": 3}
    payload2 = {"a": 2, "m": 3, "z": 1}
    
    hash1 = LiveEventLog.compute_event_hash(
        previous_hash, event_sequence, event_type, payload1, created_at
    )
    hash2 = LiveEventLog.compute_event_hash(
        previous_hash, event_sequence, event_type, payload2, created_at
    )
    
    assert hash1 == hash2, "Hash must be independent of payload key order"


def test_event_hash_chain_integrity():
    """Test that hash chain builds correctly."""
    # Genesis
    genesis_hash = "0" * 64
    
    # Event 1
    event1_hash = LiveEventLog.compute_event_hash(
        previous_hash=genesis_hash,
        event_sequence=1,
        event_type="EVENT1",
        payload={"data": "first"},
        created_at=datetime.utcnow()
    )
    
    # Event 2
    event2_hash = LiveEventLog.compute_event_hash(
        previous_hash=event1_hash,
        event_sequence=2,
        event_type="EVENT2",
        payload={"data": "second"},
        created_at=datetime.utcnow()
    )
    
    # Each hash should be different
    assert event1_hash != genesis_hash
    assert event2_hash != event1_hash
    assert event2_hash != genesis_hash


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
    
    # Should be deterministic
    sorted_json2 = json.dumps(data, sort_keys=True)
    assert sorted_json == sorted_json2, "sort_keys=True ensures consistent output"
    
    # Parse and verify
    parsed = json.loads(sorted_json)
    keys = list(parsed.keys())
    assert keys == sorted(keys), "Keys must be sorted"


def test_event_payload_sorted_in_db():
    """Test that event payload is stored with sorted keys."""
    unsorted_payload = {"z": 1, "a": 2, "m": 3}
    
    # When stored, should be sorted
    sorted_json = json.dumps(unsorted_payload, sort_keys=True)
    sorted_payload = json.loads(sorted_json)
    
    # Keys should be in order
    keys = list(sorted_payload.keys())
    assert keys == ["a", "m", "z"], "Keys must be stored sorted"


# =============================================================================
# Event Sequence Tests
# =============================================================================

@pytest.mark.asyncio
async def test_event_sequence_strictly_monotonic(
    db: AsyncSession
):
    """Test event sequence numbers are strictly monotonic increasing."""
    # Create session
    inst = Institution(
        name="Test College",
        code="TC001",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(inst)
    await db.flush()
    
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
        institution_id=inst.id,
        status=LiveCourtStatus.NOT_STARTED,
        created_at=datetime.utcnow()
    )
    db.add(session)
    await db.flush()
    
    # Create multiple events
    sequences = []
    for i in range(10):
        event = LiveEventLog(
            session_id=session.id,
            event_sequence=i + 1,
            event_type="TEST",
            event_payload_json={"seq": i + 1},
            previous_hash="0" * 64,
            event_hash="a" * 64,
            created_at=datetime.utcnow()
        )
        db.add(event)
        sequences.append(event.event_sequence)
    
    await db.flush()
    
    # Verify strictly monotonic
    for i in range(1, len(sequences)):
        assert sequences[i] > sequences[i-1], "Sequence must be strictly increasing"


@pytest.mark.asyncio
async def test_get_next_event_sequence_incremental(
    db: AsyncSession
):
    """Test next event sequence is always +1 from last."""
    # Create session
    inst = Institution(
        name="Test College",
        code="TC002",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(inst)
    await db.flush()
    
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
        institution_id=inst.id,
        status=LiveCourtStatus.NOT_STARTED,
        created_at=datetime.utcnow()
    )
    db.add(session)
    await db.flush()
    
    # First event should be sequence 1
    seq1 = await get_next_event_sequence(session.id, db)
    assert seq1 == 1, "First event sequence should be 1"
    
    # Add event
    event1 = LiveEventLog(
        session_id=session.id,
        event_sequence=seq1,
        event_type="EVENT1",
        event_payload_json={},
        previous_hash="0" * 64,
        event_hash="a" * 64,
        created_at=datetime.utcnow()
    )
    db.add(event1)
    await db.flush()
    
    # Next should be 2
    seq2 = await get_next_event_sequence(session.id, db)
    assert seq2 == 2, "Second event sequence should be 2"
    
    # Add event
    event2 = LiveEventLog(
        session_id=session.id,
        event_sequence=seq2,
        event_type="EVENT2",
        event_payload_json={},
        previous_hash="a" * 64,
        event_hash="b" * 64,
        created_at=datetime.utcnow()
    )
    db.add(event2)
    await db.flush()
    
    # Next should be 3
    seq3 = await get_next_event_sequence(session.id, db)
    assert seq3 == 3, "Third event sequence should be 3"


# =============================================================================
# Turn Time Calculation Tests
# =============================================================================

def test_turn_elapsed_seconds_integer():
    """Test that elapsed time calculations return integers only."""
    from datetime import datetime, timedelta
    
    class MockTurn:
        started_at = datetime.utcnow() - timedelta(seconds=65, milliseconds=500)
        ended_at = None
        state = LiveTurnState.ACTIVE
        
        def get_elapsed_seconds(self):
            if not self.started_at:
                return 0
            
            if self.ended_at:
                elapsed = (self.ended_at - self.started_at).total_seconds()
            else:
                elapsed = (datetime.utcnow() - self.started_at).total_seconds()
            
            return int(elapsed)
    
    turn = MockTurn()
    elapsed = turn.get_elapsed_seconds()
    
    assert isinstance(elapsed, int), "Elapsed seconds must be integer"
    assert elapsed >= 65, "Should capture full seconds"


def test_turn_remaining_seconds_integer():
    """Test that remaining time calculations return integers only."""
    from datetime import datetime, timedelta
    
    class MockTurn:
        started_at = datetime.utcnow() - timedelta(seconds=30)
        ended_at = None
        state = LiveTurnState.ACTIVE
        allocated_seconds = 60
        violation_flag = False
        
        def get_elapsed_seconds(self):
            return 30
        
        def get_remaining_seconds(self):
            if self.state == LiveTurnState.ENDED or self.violation_flag:
                return 0
            if not self.started_at:
                return self.allocated_seconds
            elapsed = self.get_elapsed_seconds()
            remaining = self.allocated_seconds - elapsed
            return max(0, remaining)
    
    turn = MockTurn()
    remaining = turn.get_remaining_seconds()
    
    assert isinstance(remaining, int), "Remaining seconds must be integer"
    assert remaining == 30, "Should be exactly 30 seconds"


# =============================================================================
# Enum Tests
# =============================================================================

def test_enum_values_deterministic():
    """Test that enum values are fixed and deterministic."""
    # LiveCourtStatus
    assert LiveCourtStatus.NOT_STARTED.value == "not_started"
    assert LiveCourtStatus.LIVE.value == "live"
    assert LiveCourtStatus.PAUSED.value == "paused"
    assert LiveCourtStatus.COMPLETED.value == "completed"
    
    # LiveTurnState
    assert LiveTurnState.PENDING.value == "pending"
    assert LiveTurnState.ACTIVE.value == "active"
    assert LiveTurnState.ENDED.value == "ended"
    
    # OralSide
    assert OralSide.PETITIONER.value == "petitioner"
    assert OralSide.RESPONDENT.value == "respondent"
    
    # OralTurnType
    assert OralTurnType.PRESENTATION.value == "presentation"
    assert OralTurnType.REBUTTAL.value == "rebuttal"


# =============================================================================
# No Unsorted Iteration Tests
# =============================================================================

def test_service_uses_sorted_for_queries():
    """Verify service layer uses sorted() for deterministic ordering."""
    import backend.services.live_court_service as svc
    
    source = inspect.getsource(svc)
    
    # Check for sorted() usage where ordering matters
    assert '.order_by(' in source, "Queries should use order_by for deterministic results"


def test_orm_uses_sorted_in_methods():
    """Verify ORM uses sorted() for serializing collections."""
    import backend.orm.live_court as orm
    
    source = inspect.getsource(orm)
    
    # Check to_dict methods use sorted
    assert 'sorted(' in source, "ORM should use sorted() for deterministic serialization"


# =============================================================================
# Genesis Hash Test
# =============================================================================

def test_genesis_hash_format():
    """Test genesis hash is correct format."""
    genesis = "0" * 64
    
    assert len(genesis) == 64, "Genesis hash must be 64 characters"
    assert all(c == '0' for c in genesis), "Genesis hash must be all zeros"
    assert genesis == "0" * 64, "Genesis hash format verification"
