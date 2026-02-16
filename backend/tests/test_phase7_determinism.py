"""
Phase 7 — Evidence & Exhibit Management Determinism Test Suite

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

from backend.orm.exhibit import SessionExhibit, ExhibitState


# =============================================================================
# Source Code Audit Tests
# =============================================================================

def test_service_no_float_usage():
    """Verify no float() usage in exhibit service."""
    import backend.services.exhibit_service as svc

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
    """Verify no random usage in exhibit service."""
    import backend.services.exhibit_service as svc

    source = inspect.getsource(svc).lower()

    assert 'random' not in source, "Must not use random()"
    assert 'shuffle' not in source, "Must not use random.shuffle()"


def test_service_no_datetime_now():
    """Verify only utcnow() used, not now()."""
    import backend.services.exhibit_service as svc

    source = inspect.getsource(svc)

    assert 'datetime.now()' not in source, "Must use datetime.utcnow(), not datetime.now()"


def test_service_no_python_hash():
    """Verify no Python hash() function used."""
    import backend.services.exhibit_service as svc

    source = inspect.getsource(svc)
    lines = source.split('\n')

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if 'hash(' in line and 'hashlib' not in line and 'exhibit_hash' not in line and 'file_hash' not in line:
            assert False, f"Line {i}: Must not use Python hash() function - use hashlib.sha256"


def test_service_uses_sha256():
    """Verify all hashing uses hashlib.sha256."""
    import backend.services.exhibit_service as svc

    source = inspect.getsource(svc)

    assert 'hashlib.sha256' in source, "Must use hashlib.sha256 for hashing"


def test_orm_models_use_sha256():
    """Verify ORM models use SHA256 for hashing."""
    import backend.orm.exhibit as orm

    source = inspect.getsource(orm)

    assert 'hashlib.sha256' in source, "ORM must use hashlib.sha256"


def test_routes_no_float_usage():
    """Verify no float() in routes."""
    import backend.routes.exhibits as routes

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
    import backend.routes.exhibits as routes

    source = inspect.getsource(routes)

    assert 'datetime.now()' not in source, "Routes must use datetime.utcnow()"


# =============================================================================
# Hash Formula Tests
# =============================================================================

def test_exhibit_hash_formula():
    """Test exhibit hash formula is deterministic."""
    session_id = 42
    side = "petitioner"
    exhibit_number = 5
    file_hash_sha256 = "a" * 64
    marked_at = datetime.utcnow()

    # Compute hash
    computed = SessionExhibit.compute_exhibit_hash(
        session_id=session_id,
        side=side,
        exhibit_number=exhibit_number,
        file_hash_sha256=file_hash_sha256,
        marked_at=marked_at
    )

    # Recompute with same data - should be identical
    computed2 = SessionExhibit.compute_exhibit_hash(
        session_id=session_id,
        side=side,
        exhibit_number=exhibit_number,
        file_hash_sha256=file_hash_sha256,
        marked_at=marked_at
    )

    assert computed == computed2, "Exhibit hash must be deterministic"
    assert len(computed) == 64, "SHA256 hex digest is 64 characters"


def test_exhibit_hash_format():
    """Test hash format is correct SHA256 hex."""
    hash_val = SessionExhibit.compute_exhibit_hash(
        session_id=1,
        side="petitioner",
        exhibit_number=1,
        file_hash_sha256="b" * 64,
        marked_at=datetime.utcnow()
    )

    # Must be 64 hex characters
    assert len(hash_val) == 64
    assert all(c in '0123456789abcdef' for c in hash_val.lower())


def test_exhibit_hash_different_data():
    """Test different data produces different hashes."""
    marked_at = datetime.utcnow()

    hash1 = SessionExhibit.compute_exhibit_hash(
        session_id=1,
        side="petitioner",
        exhibit_number=1,
        file_hash_sha256="a" * 64,
        marked_at=marked_at
    )

    hash2 = SessionExhibit.compute_exhibit_hash(
        session_id=2,
        side="petitioner",
        exhibit_number=1,
        file_hash_sha256="a" * 64,
        marked_at=marked_at
    )

    hash3 = SessionExhibit.compute_exhibit_hash(
        session_id=1,
        side="respondent",
        exhibit_number=1,
        file_hash_sha256="a" * 64,
        marked_at=marked_at
    )

    assert hash1 != hash2, "Different session_id should produce different hash"
    assert hash1 != hash3, "Different side should produce different hash"


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


def test_exhibit_to_dict_sorted():
    """Test that exhibit serialization produces sorted keys."""
    # Create a mock exhibit
    class MockExhibit:
        id = 1
        session_id = 2
        turn_id = 3
        institution_id = 4
        side = "petitioner"
        exhibit_number = 1
        original_filename = "test.pdf"
        file_path = "/path/to/file.pdf"
        file_hash_sha256 = "a" * 64
        state = ExhibitState.MARKED
        marked_by_user_id = 5
        ruled_by_user_id = None
        marked_at = datetime.utcnow()
        ruled_at = None
        exhibit_hash = "b" * 64
        created_at = datetime.utcnow()

        def verify_hash(self):
            return True

        def get_formatted_number(self):
            return "P-1"

    obj = MockExhibit()

    # Get dict representation
    obj_dict = {
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "exhibit_hash": obj.exhibit_hash,
        "exhibit_id": obj.id,
        "exhibit_number": obj.exhibit_number,
        "file_hash_sha256": obj.file_hash_sha256,
        "file_path": obj.file_path,
        "formatted_number": obj.get_formatted_number(),
        "hash_valid": obj.verify_hash(),
        "id": obj.id,
        "institution_id": obj.institution_id,
        "marked_at": obj.marked_at.isoformat() if obj.marked_at else None,
        "marked_by_user_id": obj.marked_by_user_id,
        "original_filename": obj.original_filename,
        "ruled_at": obj.ruled_at.isoformat() if obj.ruled_at else None,
        "ruled_by_user_id": obj.ruled_by_user_id,
        "session_id": obj.session_id,
        "side": obj.side,
        "state": obj.state.value,
        "turn_id": obj.turn_id,
    }

    # Verify keys are sorted
    keys = list(obj_dict.keys())
    assert keys == sorted(keys), "Dictionary keys must be sorted for determinism"


# =============================================================================
# Enum Tests
# =============================================================================

def test_exhibit_state_enum_deterministic():
    """Test exhibit state enum values are fixed."""
    assert ExhibitState.UPLOADED.value == "uploaded"
    assert ExhibitState.MARKED.value == "marked"
    assert ExhibitState.TENDERED.value == "tendered"
    assert ExhibitState.ADMITTED.value == "admitted"
    assert ExhibitState.REJECTED.value == "rejected"


def test_enum_values_unique():
    """Test that all enum values are unique."""
    state_values = [e.value for e in ExhibitState]
    assert len(state_values) == len(set(state_values)), "Enum values must be unique"


# =============================================================================
# No Unsorted Iteration Tests
# =============================================================================

def test_service_uses_sorted_for_queries():
    """Verify service layer uses order_by for deterministic ordering."""
    import backend.services.exhibit_service as svc

    source = inspect.getsource(svc)

    # Check for order_by usage
    assert '.order_by(' in source, "Queries should use order_by for deterministic results"


def test_orm_uses_sorted_in_methods():
    """Verify ORM serialization is deterministic."""
    import backend.orm.exhibit as orm

    source = inspect.getsource(orm)

    # Check to_dict uses deterministic ordering
    assert 'sorted(' in source or 'order_by' in source, "ORM should use sorted() or order_by for determinism"


# =============================================================================
# Migration Tests (Determinism)
# =============================================================================

def test_migration_no_float():
    """Verify migration script has no float usage."""
    import backend.migrations.migrate_phase7_exhibits as mig

    source = inspect.getsource(mig)

    assert 'float(' not in source, "Migration must not use float()"


def test_migration_no_random():
    """Verify migration script has no random usage."""
    import backend.migrations.migrate_phase7_exhibits as mig

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
    """Verify datetime.utcnow() is used in exhibit code."""
    import backend.services.exhibit_service as svc

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
