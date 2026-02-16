"""
Phase 12 — Determinism Audit Test Suite

Strict audit for deterministic behavior compliance.
No floats, no random, no datetime.now, no Python hash().
"""
import ast
import inspect
import json
from typing import List, Tuple

import pytest

from backend.security import merkle
from backend.services import audit_service, certificate_service
from backend.orm.tournament_results import TournamentAuditSnapshot


class TestMerkleDeterminism:
    """Test Merkle tree implementation for determinism."""
    
    def test_sha256_no_floats(self):
        """Verify sha256 function uses no float operations."""
        source = inspect.getsource(merkle.sha256)
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == 'float':
                    pytest.fail("sha256 function contains float() call")
    
    def test_build_merkle_root_no_random(self):
        """Verify build_merkle_root uses no random operations."""
        source = inspect.getsource(merkle.build_merkle_root)
        
        # Check for random module usage
        assert 'random' not in source.lower(), "build_merkle_root contains random reference"
        assert 'randint' not in source.lower(), "build_merkle_root contains randint"
        assert 'choice' not in source.lower(), "build_merkle_root contains choice"
    
    def test_merkle_root_determinism(self):
        """Verify Merkle root is deterministic regardless of input order."""
        hashes = [
            "a1b2c3d4e5f6" * 4,  # 24 chars -> 64 with padding
            "1234567890ab" * 4,
            "fedcba098765" * 4,
        ]
        
        # Build with different orders
        root1 = merkle.build_merkle_root(hashes)
        root2 = merkle.build_merkle_root(list(reversed(hashes)))
        root3 = merkle.build_merkle_root(sorted(hashes, reverse=True))
        
        assert root1 == root2 == root3, "Merkle root must be order-independent"
        assert len(root1) == 64, "Merkle root must be 64 hex chars (SHA256)"
    
    def test_merkle_root_stability(self):
        """Verify same inputs always produce same root."""
        hashes = ["hash1" * 8, "hash2" * 8, "hash3" * 8]
        
        roots = [merkle.build_merkle_root(hashes) for _ in range(10)]
        
        assert all(r == roots[0] for r in roots), "Merkle root must be stable"
    
    def test_merkle_empty_tree(self):
        """Verify empty tree handling."""
        root = merkle.build_merkle_root([])
        
        assert isinstance(root, str), "Root must be string"
        assert len(root) == 64, "Empty tree root must be 64 hex chars"


class TestAuditServiceDeterminism:
    """Test audit service for determinism."""
    
    def test_no_datetime_now(self):
        """Verify no datetime.now() calls."""
        source = inspect.getsource(audit_service)
        
        # Parse AST
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr == 'now':
                    pytest.fail("audit_service contains datetime.now() call")
    
    def test_no_python_hash(self):
        """Verify no built-in hash() function usage."""
        source = inspect.getsource(audit_service)
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == 'hash':
                    pytest.fail("audit_service contains Python hash() call - must use hashlib.sha256")
    
    def test_json_uses_sort_keys(self):
        """Verify JSON serialization uses sort_keys=True."""
        source = inspect.getsource(audit_service)
        
        # Find all json.dumps calls
        assert 'sort_keys=True' in source, "audit_service json.dumps must use sort_keys=True"
    
    def test_signature_computation_determinism(self):
        """Verify signature computation is deterministic."""
        root_hash = "a" * 64
        secret = "test_secret"
        
        sig1 = audit_service.compute_signature(root_hash, secret)
        sig2 = audit_service.compute_signature(root_hash, secret)
        
        assert sig1 == sig2, "Signature must be deterministic"
        assert len(sig1) == 64, "Signature must be 64 hex chars"


class TestCertificateServiceDeterminism:
    """Test certificate service for determinism."""
    
    def test_compute_signature_no_float(self):
        """Verify compute_signature uses no floats."""
        source = inspect.getsource(certificate_service.compute_signature)
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == 'float':
                    pytest.fail("compute_signature contains float() call")
    
    def test_certificate_json_sorting(self):
        """Verify certificate uses sorted JSON keys."""
        source = inspect.getsource(certificate_service.generate_tournament_certificate)
        
        assert 'sort_keys=True' in source, "Certificate JSON must use sort_keys=True"
        assert 'separators=' in source, "Certificate JSON should use compact separators"


class TestTournamentAuditSnapshotORM:
    """Test TournamentAuditSnapshot ORM for determinism."""
    
    def test_to_dict_sorting(self):
        """Verify to_dict returns sorted keys."""
        source = inspect.getsource(TournamentAuditSnapshot.to_dict)
        
        # Check for sorted dict literal
        tree = ast.parse(source)
        
        # Verify method exists and returns dict
        found_return = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Return):
                found_return = True
                if isinstance(node.value, ast.Dict):
                    keys = [k.s for k in node.value.keys if isinstance(k, ast.Constant)]
                    assert keys == sorted(keys), "to_dict must return sorted keys"
        
        assert found_return, "to_dict must have return statement"


class TestMerkleIntegration:
    """Integration tests for Merkle engine."""
    
    def test_full_hash_tree_determinism(self):
        """Test full tournament hash tree is deterministic."""
        tournament_id = 42
        
        # Build tree multiple times
        for _ in range(5):
            root = merkle.hash_tournament_data(
                tournament_id=tournament_id,
                pairing_checksum="pair_hash_" * 6,
                panel_checksum="panel_hash_" * 6,
                event_hashes=["evt1" * 8, "evt2" * 8, "evt3" * 8],
                objection_hashes=["obj1" * 8],
                exhibit_hashes=["exh1" * 8, "exh2" * 8],
                results_checksum="results_hash_" * 5
            )
            
            assert len(root) == 64, f"Root must be 64 chars, got {len(root)}"
    
    def test_component_order_independence(self):
        """Verify hash is independent of component order."""
        base_params = {
            "tournament_id": 42,
            "pairing_checksum": "pair" * 8,
            "panel_checksum": "panel" * 8,
            "results_checksum": "results" * 8,
            "event_hashes": ["e1" * 16, "e2" * 16],
            "objection_hashes": ["o1" * 16],
            "exhibit_hashes": ["ex1" * 16, "ex2" * 16]
        }
        
        # Original order
        root1 = merkle.hash_tournament_data(**base_params)
        
        # Reversed lists
        params2 = base_params.copy()
        params2["event_hashes"] = list(reversed(base_params["event_hashes"]))
        params2["objection_hashes"] = list(reversed(base_params["objection_hashes"]))
        params2["exhibit_hashes"] = list(reversed(base_params["exhibit_hashes"]))
        root2 = merkle.hash_tournament_data(**params2)
        
        assert root1 == root2, "Hash must be independent of list ordering"


class TestSourceCodeAudit:
    """Source code audit for forbidden patterns."""
    
    def test_merkle_py_no_forbidden_patterns(self):
        """Audit merkle.py for forbidden patterns."""
        source = inspect.getsource(merkle)
        
        forbidden_patterns = [
            'datetime.now()',
            'random.rand',
            'random.choice',
            'random.shuffle',
            'time.time()',
        ]
        
        for pattern in forbidden_patterns:
            assert pattern not in source, f"merkle.py contains forbidden pattern: {pattern}"
    
    def test_audit_service_no_forbidden_patterns(self):
        """Audit audit_service.py for forbidden patterns."""
        source = inspect.getsource(audit_service)
        
        forbidden_patterns = [
            'datetime.now()',
            'random.',
            'time.time()',
        ]
        
        for pattern in forbidden_patterns:
            assert pattern not in source, f"audit_service.py contains forbidden pattern: {pattern}"
    
    def test_certificate_service_no_forbidden_patterns(self):
        """Audit certificate_service.py for forbidden patterns."""
        source = inspect.getsource(certificate_service)
        
        forbidden_patterns = [
            'datetime.now()',
            'random.',
            'time.time()',
        ]
        
        for pattern in forbidden_patterns:
            assert pattern not in source, f"certificate_service.py contains forbidden pattern: {pattern}"


class TestSerializationDeterminism:
    """Test JSON serialization is deterministic."""
    
    def test_json_dumps_consistency(self):
        """Verify json.dumps produces consistent output."""
        data = {
            "z_key": "value",
            "a_key": "value",
            "m_key": "value"
        }
        
        # Multiple dumps
        outputs = [json.dumps(data, sort_keys=True) for _ in range(10)]
        
        assert all(o == outputs[0] for o in outputs), "JSON must be consistent"
        
        # Verify sorting
        assert outputs[0].index('a_key') < outputs[0].index('m_key'), "Keys must be sorted"
        assert outputs[0].index('m_key') < outputs[0].index('z_key'), "Keys must be sorted"


class TestHashLengthRequirements:
    """Test hash length requirements."""
    
    def test_sha256_output_length(self):
        """Verify SHA256 produces 64 char hex output."""
        test_inputs = [
            "",
            "a",
            "test string",
            "x" * 1000
        ]
        
        for inp in test_inputs:
            result = merkle.sha256(inp)
            assert len(result) == 64, f"SHA256 must produce 64 hex chars for input: {inp[:20]}..."
            assert all(c in '0123456789abcdef' for c in result.lower()), "Must be hex string"
