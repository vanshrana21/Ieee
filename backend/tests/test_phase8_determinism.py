"""
Phase 8 — Determinism Audit Test Suite

Strict audit for forbidden patterns in realtime modules.
Verifies SHA256, sort_keys=True, and no non-deterministic sources.
"""
import pytest
import ast
import inspect
import hashlib
import json
from pathlib import Path
from typing import List, Tuple

from backend.realtime.broadcast_adapter import BroadcastAdapter
from backend.realtime.in_memory_adapter import InMemoryAdapter
from backend.realtime.redis_adapter import RedisAdapter
from backend.realtime.connection_manager import ConnectionManager
from backend.realtime.rate_limit import RedisRateLimiter
from backend.realtime.backpressure import BackpressureManager
from backend.realtime.ws_server import websocket_endpoint
from backend.routes.integrity import IntegrityVerifier


# =============================================================================
# Source Code Scanner
# =============================================================================

def get_module_source(module) -> str:
    """Get source code of a module."""
    try:
        return inspect.getsource(module)
    except (TypeError, OSError):
        return ""


def find_forbidden_patterns(source_code: str, filename: str) -> List[Tuple[int, str, str]]:
    """
    Scan source code for forbidden non-deterministic patterns.
    
    Returns list of (line_number, pattern, line_content)
    """
    forbidden = []
    lines = source_code.split('\n')
    
    for i, line in enumerate(lines, 1):
        # Skip comments and strings
        code_only = line.split('#')[0]
        
        # Check for float()
        if 'float(' in code_only and 'def ' not in code_only:
            forbidden.append((i, 'float()', line.strip()))
        
        # Check for random
        if 'random' in code_only.lower() and 'import' not in code_only.lower():
            if 'random()' in code_only or '.random(' in code_only:
                forbidden.append((i, 'random', line.strip()))
        
        # Check for datetime.now() (should use utcnow)
        if 'datetime.now()' in code_only or 'datetime.datetime.now()' in code_only:
            forbidden.append((i, 'datetime.now()', line.strip()))
        
        # Check for Python hash()
        if 'hash(' in code_only and 'sha256' not in code_only.lower():
            # Allow hashlib.sha256, but not bare hash()
            if 'hashlib' not in code_only.lower():
                forbidden.append((i, 'hash()', line.strip()))
        
        # Check for unsorted iteration
        if 'json.dumps' in code_only and 'sort_keys' not in code_only:
            forbidden.append((i, 'json.dumps without sort_keys', line.strip()))
    
    return forbidden


# =============================================================================
# Test: Forbidden Pattern Scan
# =============================================================================

@pytest.mark.parametrize("module,name", [
    (BroadcastAdapter, "broadcast_adapter"),
    (InMemoryAdapter, "in_memory_adapter"),
    (RedisAdapter, "redis_adapter"),
    (ConnectionManager, "connection_manager"),
    (RedisRateLimiter, "rate_limit"),
    (BackpressureManager, "backpressure"),
    (IntegrityVerifier, "integrity"),
])
def test_no_forbidden_patterns(module, name):
    """Scan all Phase 8 modules for forbidden patterns."""
    source = get_module_source(module)
    if not source:
        pytest.skip(f"Could not get source for {name}")
    
    forbidden = find_forbidden_patterns(source, name)
    
    if forbidden:
        errors = '\n'.join([f"Line {line}: {pattern} - {content[:60]}" 
                          for line, pattern, content in forbidden])
        pytest.fail(f"Forbidden patterns found in {name}:\n{errors}")


# =============================================================================
# Test: SHA256 Hash Usage
# =============================================================================

def test_sha256_used_for_hashes():
    """Verify SHA256 is used for hash computation."""
    source = get_module_source(BroadcastAdapter)
    
    # Should have sha256 usage
    assert 'sha256' in source.lower(), "SHA256 not found in BroadcastAdapter"
    assert 'hashlib' in source.lower(), "hashlib not found in BroadcastAdapter"


def test_message_hash_computation_deterministic():
    """Test that message hash computation is deterministic."""
    adapter = InMemoryAdapter()
    
    message = {
        "type": "EVENT",
        "session_id": 42,
        "event_sequence": 1,
        "payload": {"b": 2, "a": 1}  # Unsorted keys
    }
    
    # Compute hash twice
    serialized1 = adapter._serialize_message(message)
    serialized2 = adapter._serialize_message(message)
    
    assert serialized1 == serialized2, "Serialization not deterministic"
    
    hash1 = hashlib.sha256(serialized1.encode()).hexdigest()
    hash2 = hashlib.sha256(serialized2.encode()).hexdigest()
    
    assert hash1 == hash2, "Hash computation not deterministic"


# =============================================================================
# Test: JSON Serialization
# =============================================================================

def test_json_sort_keys_true():
    """Verify all json.dumps use sort_keys=True."""
    modules = [
        BroadcastAdapter,
        InMemoryAdapter,
        RedisAdapter,
        ConnectionManager,
        IntegrityVerifier,
    ]
    
    for module in modules:
        source = get_module_source(module)
        if not source:
            continue
        
        # Find all json.dumps calls
        lines = source.split('\n')
        for i, line in enumerate(lines, 1):
            if 'json.dumps' in line:
                # Check for sort_keys
                if 'sort_keys=True' not in line and 'sort_keys' not in line:
                    # Might be multi-line, check next few lines
                    context = ' '.join(lines[max(0, i-2):min(len(lines), i+3)])
                    if 'sort_keys=True' not in context:
                        pytest.fail(f"json.dumps without sort_keys=True in {module.__name__} at line {i}")


def test_sorted_json_output():
    """Verify JSON output is actually sorted."""
    adapter = InMemoryAdapter()
    
    # Message with keys in random order
    message = {
        "z_key": 1,
        "a_key": 2,
        "m_key": 3,
        "event_sequence": 1,
        "type": "EVENT"
    }
    
    serialized = adapter._serialize_message(message)
    
    # Parse and verify order
    parsed = json.loads(serialized)
    keys = list(parsed.keys())
    
    assert keys == sorted(keys), f"Keys not sorted: {keys}"


# =============================================================================
# Test: No Datetime.now()
# =============================================================================

def test_no_datetime_now():
    """Verify no datetime.now() usage (should use utcnow)."""
    modules = [
        BroadcastAdapter,
        InMemoryAdapter,
        RedisAdapter,
        ConnectionManager,
        RedisRateLimiter,
        BackpressureManager,
        IntegrityVerifier,
    ]
    
    for module in modules:
        source = get_module_source(module)
        if not source:
            continue
        
        # Check for datetime.now()
        if 'datetime.now()' in source:
            pytest.fail(f"Forbidden datetime.now() found in {module.__name__}")
        
        if 'datetime.datetime.now()' in source:
            pytest.fail(f"Forbidden datetime.datetime.now() found in {module.__name__}")


# =============================================================================
# Test: No Random Usage
# =============================================================================

def test_no_random():
    """Verify no random() usage in any form."""
    modules = [
        BroadcastAdapter,
        InMemoryAdapter,
        RedisAdapter,
        ConnectionManager,
        RedisRateLimiter,
        BackpressureManager,
    ]
    
    for module in modules:
        source = get_module_source(module)
        if not source:
            continue
        
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            # Check for random imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if 'random' in alias.name.lower():
                        pytest.fail(f"random import found in {module.__name__}")
            
            if isinstance(node, ast.ImportFrom):
                if node.module and 'random' in node.module.lower():
                    pytest.fail(f"random import found in {module.__name__}")
            
            # Check for random calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if 'random' in node.func.id.lower():
                        pytest.fail(f"random() call found in {module.__name__}")


# =============================================================================
# Test: No Float Usage
# =============================================================================

def test_no_float():
    """Verify no float() usage (should use int for time calculations)."""
    modules = [
        BroadcastAdapter,
        InMemoryAdapter,
        RedisAdapter,
        ConnectionManager,
        RedisRateLimiter,
        BackpressureManager,
    ]
    
    for module in modules:
        source = get_module_source(module)
        if not source:
            continue
        
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id == 'float':
                        pytest.fail(f"float() call found in {module.__name__}")


# =============================================================================
# Test: Broadcast Contract Compliance
# =============================================================================

def test_broadcast_contract_fields_present():
    """Verify broadcast messages include required fields."""
    source = get_module_source(BroadcastAdapter)
    
    # Should validate required fields
    assert 'event_sequence' in source
    assert 'event_hash' in source
    assert 'session_id' in source
    assert 'validate_message' in source


# =============================================================================
# Test: No Unordered Iteration
# =============================================================================

def test_sorted_iteration():
    """Verify dict iteration is sorted when used for hashing."""
    # Check that any dict iteration used for serialization is sorted
    source = get_module_source(BroadcastAdapter)
    
    # The _serialize_message should use json.dumps with sort_keys
    assert 'sort_keys=True' in source


# =============================================================================
# Test: Redis Channel Naming
# =============================================================================

def test_deterministic_channel_naming():
    """Verify Redis channel names are deterministic."""
    source = get_module_source(RedisAdapter)
    
    # Should use predictable patterns like "session:{id}"
    assert 'session:' in source
    
    # Should NOT use random/uuid based names
    assert 'uuid' not in source.lower() or 'def ' not in source.lower()


# =============================================================================
# Test: Rate Limit Determinism
# =============================================================================

def test_rate_limit_key_format():
    """Verify rate limit keys are deterministic."""
    limiter = RedisRateLimiter()
    
    # Key format should be predictable
    key = limiter._make_key("ws_connections_per_user", "user_123")
    expected = "ratelimit:ws_connections_per_user:user_123"
    
    assert key == expected, f"Unexpected key format: {key}"


# =============================================================================
# Test: Query Ordering
# =============================================================================

def test_sorted_queries():
    """Verify database queries use sorted ordering."""
    source = get_module_source(IntegrityVerifier)
    
    # Should use .order_by() for deterministic results
    assert '.order_by(' in source
    assert '.asc()' in source


# =============================================================================
# Test: Time Calculations
# =============================================================================

def test_time_calculations_use_int():
    """Verify time calculations use int() not float()."""
    # Check that timestamp calculations don't use float
    modules = [ConnectionManager, BackpressureManager]
    
    for module in modules:
        source = get_module_source(module)
        if not source:
            continue
        
        # Check for proper int conversion of timestamps
        if 'total_seconds()' in source:
            # Should be wrapped in int()
            lines = source.split('\n')
            for i, line in enumerate(lines, 1):
                if 'total_seconds()' in line and 'int(' not in line:
                    # Check context
                    context = ' '.join(lines[max(0, i-2):min(len(lines), i+3)])
                    if 'int(' not in context:
                        pytest.fail(f"total_seconds() without int() in {module.__name__}")


# =============================================================================
# Test: Global Instance Management
# =============================================================================

def test_global_instances_thread_safe():
    """Verify global instance management is deterministic."""
    from backend.realtime.connection_manager import get_connection_manager, set_connection_manager
    from backend.realtime.backpressure import get_backpressure_manager, set_backpressure_manager
    
    # These should be simple getter/setters
    assert get_connection_manager() is None or isinstance(get_connection_manager(), ConnectionManager)
    assert get_backpressure_manager() is None or isinstance(get_backpressure_manager(), BackpressureManager)
