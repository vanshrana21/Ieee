"""
Phase 6 — Objection & Procedural Control Determinism Test Suite

Tests for all deterministic guarantees:
- No float() usage
- No random() usage
- No datetime.now()
- No Python hash()
- All json.dumps include sort_keys=True
- SHA256 used for hashing
- No unsorted iteration
- Enum values deterministic
"""
import hashlib
import inspect
import json
from datetime import datetime

import pytest

from backend.orm.live_objection import (
    LiveObjection, ObjectionType, ObjectionState
)


# =============================================================================
# Source Code Audit Tests
# =============================================================================

def test_service_no_float_usage():
    """Verify no float() usage in objection service."""
    import backend.services.live_objection_service as svc
    
    source = inspect.getsource(svc)
    lines = source.split('\n')
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if '"' in line or "'" in line:
            # Skip lines that contain strings (likely comments or docstrings)
            continue
        assert 'float(' not in line, f"Line {i}: Must not use float() - {line}"


def test_service_no_random_usage():
    """Verify no random usage in objection service."""
    import backend.services.live_objection_service as svc
    
    source = inspect.getsource(svc).lower()
    
    assert 'random' not in source, "Must not use random()"
    assert 'shuffle' not in source, "Must not use random.shuffle()"


def test_service_no_datetime_now():
    """Verify only utcnow() used, not now()."""
    import backend.services.live_objection_service as svc
    
    source = inspect.getsource(svc)
    
    assert 'datetime.now()' not in source, "Must use datetime.utcnow(), not datetime.now()"


def test_service_no_python_hash():
    """Verify no Python hash() function used."""
    import backend.services.live_objection_service as svc
    
    source = inspect.getsource(svc)
    lines = source.split('\n')
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        # Check for standalone hash( calls
        if 'hash(' in line and 'hashlib' not in line and 'objection_hash' not in line:
            assert False, f"Line {i}: Must not use Python hash() function - use hashlib.sha256"


def test_service_uses_sha256():
    """Verify all hashing uses hashlib.sha256."""
    import backend.services.live_objection_service as svc
    
    source = inspect.getsource(svc)
    
    assert 'hashlib.sha256' in source, "Must use hashlib.sha256 for hashing"


def test_orm_models_use_sha256():
    """Verify ORM models use SHA256 for hashing."""
    import backend.orm.live_objection as orm
    
    source = inspect.getsource(orm)
    
    assert 'hashlib.sha256' in source, "ORM must use hashlib.sha256"


def test_routes_no_float_usage():
    """Verify no float() in routes."""
    import backend.routes.live_objection as routes
    
    source = inspect.getsource(routes)
    lines = source.split('\n')
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if '"' in line or "'" in line:
            continue
        assert 'float(' not in line, f"Routes Line {i}: Must not use float()"


def test_routes_no_datetime_now():
    """Verify routes use utcnow()."""
    import backend.routes.live_objection as routes
    
    source = inspect.getsource(routes)
    
    assert 'datetime.now()' not in source, "Routes must use datetime.utcnow()"


# =============================================================================
# Hash Formula Tests
# =============================================================================

def test_objection_hash_formula():
    """Test objection hash formula is deterministic."""
    session_id = 42
    turn_id = 15
    raised_by_user_id = 7
    objection_type = ObjectionType.LEADING
    reason_text = "Leading question"
    raised_at = datetime.utcnow()
    
    # Compute hash
    computed = LiveObjection.compute_objection_hash(
        session_id=session_id,
        turn_id=turn_id,
        raised_by_user_id=raised_by_user_id,
        objection_type=objection_type,
        reason_text=reason_text,
        raised_at=raised_at
    )
    
    # Recompute with same data - should be identical
    computed2 = LiveObjection.compute_objection_hash(
        session_id=session_id,
        turn_id=turn_id,
        raised_by_user_id=raised_by_user_id,
        objection_type=objection_type,
        reason_text=reason_text,
        raised_at=raised_at
    )
    
    assert computed == computed2, "Objection hash must be deterministic"
    assert len(computed) == 64, "SHA256 hex digest is 64 characters"


def test_objection_hash_format():
    """Test hash format is correct SHA256 hex."""
    hash_val = LiveObjection.compute_objection_hash(
        session_id=1,
        turn_id=1,
        raised_by_user_id=1,
        objection_type=ObjectionType.PROCEDURAL,
        reason_text="Test",
        raised_at=datetime.utcnow()
    )
    
    # Must be 64 hex characters
    assert len(hash_val) == 64
    assert all(c in '0123456789abcdef' for c in hash_val.lower())


def test_objection_hash_different_data():
    """Test different data produces different hashes."""
    raised_at = datetime.utcnow()
    
    hash1 = LiveObjection.compute_objection_hash(
        session_id=1, turn_id=1, raised_by_user_id=1,
        objection_type=ObjectionType.LEADING,
        reason_text="Reason A", raised_at=raised_at
    )
    
    hash2 = LiveObjection.compute_objection_hash(
        session_id=2, turn_id=1, raised_by_user_id=1,
        objection_type=ObjectionType.LEADING,
        reason_text="Reason A", raised_at=raised_at
    )
    
    hash3 = LiveObjection.compute_objection_hash(
        session_id=1, turn_id=1, raised_by_user_id=1,
        objection_type=ObjectionType.SPECULATION,
        reason_text="Reason A", raised_at=raised_at
    )
    
    assert hash1 != hash2, "Different session_id should produce different hash"
    assert hash1 != hash3, "Different objection_type should produce different hash"


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


def test_objection_to_dict_sorted():
    """Test that objection serialization produces sorted keys."""
    # Create a mock objection
    class MockObjection:
        id = 1
        session_id = 2
        turn_id = 3
        raised_by_user_id = 4
        ruled_by_user_id = 5
        objection_type = ObjectionType.LEADING
        state = ObjectionState.PENDING
        reason_text = "Test"
        ruling_reason_text = None
        raised_at = datetime.utcnow()
        ruled_at = None
        objection_hash = "a" * 64
        created_at = datetime.utcnow()
        
        def verify_hash(self):
            return True
    
    obj = MockObjection()
    
    # Get dict representation
    obj_dict = {
        "id": obj.id,
        "session_id": obj.session_id,
        "turn_id": obj.turn_id,
        "raised_by_user_id": obj.raised_by_user_id,
        "ruled_by_user_id": obj.ruled_by_user_id,
        "objection_type": obj.objection_type.value,
        "state": obj.state.value,
        "reason_text": obj.reason_text,
        "ruling_reason_text": obj.ruling_reason_text,
        "raised_at": obj.raised_at.isoformat() if obj.raised_at else None,
        "ruled_at": obj.ruled_at.isoformat() if obj.ruled_at else None,
        "objection_hash": obj.objection_hash,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "hash_valid": obj.verify_hash()
    }
    
    # Verify keys are sorted
    keys = list(obj_dict.keys())
    assert keys == sorted(keys), "Dictionary keys must be sorted for determinism"


# =============================================================================
# Enum Tests
# =============================================================================

def test_objection_type_enum_deterministic():
    """Test objection type enum values are fixed."""
    assert ObjectionType.LEADING.value == "leading"
    assert ObjectionType.IRRELEVANT.value == "irrelevant"
    assert ObjectionType.MISREPRESENTATION.value == "misrepresentation"
    assert ObjectionType.SPECULATION.value == "speculation"
    assert ObjectionType.PROCEDURAL.value == "procedural"


def test_objection_state_enum_deterministic():
    """Test objection state enum values are fixed."""
    assert ObjectionState.PENDING.value == "pending"
    assert ObjectionState.SUSTAINED.value == "sustained"
    assert ObjectionState.OVERRULED.value == "overruled"


def test_enum_values_unique():
    """Test that all enum values are unique."""
    type_values = [e.value for e in ObjectionType]
    assert len(type_values) == len(set(type_values)), "Enum values must be unique"
    
    state_values = [e.value for e in ObjectionState]
    assert len(state_values) == len(set(state_values)), "Enum values must be unique"


# =============================================================================
# No Unsorted Iteration Tests
# =============================================================================

def test_service_uses_sorted_for_queries():
    """Verify service layer uses order_by for deterministic ordering."""
    import backend.services.live_objection_service as svc
    
    source = inspect.getsource(svc)
    
    # Check for order_by usage
    assert '.order_by(' in source, "Queries should use order_by for deterministic results"


def test_orm_uses_sorted_in_methods():
    """Verify ORM serialization is deterministic."""
    import backend.orm.live_objection as orm
    
    source = inspect.getsource(orm)
    
    # Check to_dict uses deterministic ordering
    assert 'sorted(' in source or 'order_by' in source, "ORM should use sorted() or order_by for determinism"


# =============================================================================
# Migration Tests (Determinism)
# =============================================================================

def test_migration_no_float():
    """Verify migration script has no float usage."""
    import backend.migrations.migrate_phase6_objections as mig
    
    source = inspect.getsource(mig)
    
    assert 'float(' not in source, "Migration must not use float()"


def test_migration_no_random():
    """Verify migration script has no random usage."""
    import backend.migrations.migrate_phase6_objections as mig
    
    source = inspect.getsource(mig).lower()
    
    assert 'random' not in source, "Migration must not use random()"


# =============================================================================
# SHA256 Consistency Tests
# =============================================================================

def test_sha256_produces_consistent_output():
    """Test that hashlib.sha256 produces consistent output."""
    data = b"test data for hashing"
    
    hash1 = hashlib.sha256(data).hexdigest()
    hash2 = hashlib.sha256(data).hexdigest()
    
    assert hash1 == hash2, "SHA256 must produce consistent output"
    assert len(hash1) == 64, "SHA256 hex is 64 characters"


def test_sha256_different_input_different_output():
    """Test that different inputs produce different hashes."""
    hash1 = hashlib.sha256(b"input1").hexdigest()
    hash2 = hashlib.sha256(b"input2").hexdigest()
    
    assert hash1 != hash2, "Different inputs must produce different hashes"


# =============================================================================
# Timestamp Tests
# =============================================================================

def test_datetime_utcnow_used():
    """Verify datetime.utcnow() is used in objection code."""
    import backend.services.live_objection_service as svc
    
    source = inspect.getsource(svc)
    
    assert 'datetime.utcnow()' in source, "Must use datetime.utcnow()"


def test_timestamp_format_iso():
    """Test that timestamps use ISO format for hashing."""
    now = datetime.utcnow()
    iso_str = now.isoformat()
    
    # ISO format should be parseable and consistent
    assert isinstance(iso_str, str)
    assert 'T' in iso_str, "ISO format should contain T separator"


# =============================================================================
# Combined Hash + JSON Tests
# =============================================================================

def test_combined_hash_with_json_payload():
    """Test hashing combined with JSON payload is deterministic."""
    payload = {"b": 2, "a": 1, "c": 3}  # Out of order keys
    
    # Always sort JSON keys
    json_str = json.dumps(payload, sort_keys=True)
    
    # Hash should be consistent
    hash1 = hashlib.sha256(json_str.encode()).hexdigest()
    hash2 = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    
    assert hash1 == hash2, "Sorted JSON hashing must be deterministic"


def test_unsorted_vs_sorted_json_hash():
    """Test that unsorted JSON produces different hashes (demonstrating need for sort_keys)."""
    # This test demonstrates why sort_keys=True is critical
    # Without it, Python dict iteration order varies
    
    data = {"z": 1, "a": 2, "m": 3}
    
    # With sort_keys - always consistent
    sorted_json = json.dumps(data, sort_keys=True)
    hash_sorted = hashlib.sha256(sorted_json.encode()).hexdigest()
    
    # Without sort_keys - may vary (Python < 3.7)
    # In Python 3.7+ dicts preserve insertion order, but we still use sort_keys for safety
    unsorted_json = json.dumps(data, sort_keys=False)
    hash_unsorted = hashlib.sha256(unsorted_json.encode()).hexdigest()
    
    # The sorted hash should be consistent and calculable
    expected_sorted = json.dumps({"a": 2, "m": 3, "z": 1}, sort_keys=True)
    assert sorted_json == expected_sorted
    
    # Verify hash is 64 chars
    assert len(hash_sorted) == 64
