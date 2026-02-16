"""
Phase 13 — Determinism Audit Test Suite

Strict audit for deterministic behavior compliance.
No floats, no random, no datetime.now, no Python hash().
"""
import ast
import inspect
import json
from typing import List, Dict, Any

import pytest

from backend.core import tenant_guard
from backend.services import plan_enforcement_service, institution_service
from backend.orm.tournament_results import Institution, InstitutionRole, InstitutionAuditLog


class TestTenantGuardDeterminism:
    """Test tenant guard for determinism."""
    
    def test_no_float_in_tenant_guard(self):
        """Verify tenant guard uses no float operations."""
        source = inspect.getsource(tenant_guard)
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == 'float':
                    pytest.fail("tenant_guard contains float() call")
    
    def test_no_random_in_tenant_guard(self):
        """Verify tenant guard uses no random."""
        source = inspect.getsource(tenant_guard)
        
        assert 'random' not in source.lower(), "tenant_guard contains random reference"
        assert 'randint' not in source.lower(), "tenant_guard contains randint"
        assert 'choice' not in source.lower(), "tenant_guard contains choice"
    
    def test_no_datetime_now(self):
        """Verify no datetime.now() calls."""
        source = inspect.getsource(tenant_guard)
        
        assert 'datetime.now()' not in source, "tenant_guard contains datetime.now()"
        assert 'datetime.utcnow()' in source or 'utcnow' not in source, "Should use utcnow if datetime used"
    
    def test_role_constants_defined(self):
        """Verify role constants are strings (deterministic)."""
        assert tenant_guard.ROLE_INSTITUTION_ADMIN == "institution_admin"
        assert tenant_guard.ROLE_FACULTY == "faculty"
        assert tenant_guard.ROLE_JUDGE == "judge"
        assert tenant_guard.ROLE_PARTICIPANT == "participant"
        assert tenant_guard.ROLE_SUPER_ADMIN == "super_admin"
    
    def test_allowed_roles_is_frozen_set(self):
        """Verify allowed roles is deterministic set."""
        roles = tenant_guard.ALLOWED_ROLES
        
        # Should be exactly these 4 roles
        expected = {"institution_admin", "faculty", "judge", "participant"}
        assert roles == expected, f"ALLOWED_ROLES mismatch: {roles}"


class TestPlanEnforcementDeterminism:
    """Test plan enforcement service for determinism."""
    
    def test_no_float_in_service(self):
        """Verify plan enforcement uses no float operations."""
        source = inspect.getsource(plan_enforcement_service)
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == 'float':
                    pytest.fail("plan_enforcement_service contains float() call")
    
    def test_decimal_comparison_used(self):
        """Verify Decimal is used for comparisons."""
        source = inspect.getsource(plan_enforcement_service.PlanEnforcementService)
        
        assert 'Decimal' in source, "Must use Decimal for deterministic comparison"
    
    def test_no_datetime_now_in_service(self):
        """Verify service uses no datetime.now()."""
        source = inspect.getsource(plan_enforcement_service)
        
        assert 'datetime.now()' not in source, "Service contains datetime.now()"


class TestInstitutionServiceDeterminism:
    """Test institution service for determinism."""
    
    def test_no_float_in_institution_service(self):
        """Verify institution service uses no float."""
        source = inspect.getsource(institution_service)
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == 'float':
                    pytest.fail("institution_service contains float() call")
    
    def test_slug_generation_deterministic(self):
        """Verify slug generation is deterministic."""
        service_class = institution_service.InstitutionService
        
        # Test slug generation logic
        test_cases = [
            ("My Institution", "my-institution"),
            ("Test University", "test-university"),
            ("ABC College of Law", "abc-college-of-law"),
            ("Multiple   Spaces", "multiple-spaces"),
            ("Under_Score", "under-score"),
            ("Mixed-Case_Name", "mixed-case-name"),
        ]
        
        for input_name, expected_slug in test_cases:
            # Create mock service to test method
            slug = service_class._generate_slug(None, input_name)
            assert slug == expected_slug, f"Slug mismatch for '{input_name}': got {slug}, expected {expected_slug}"
    
    def test_slug_generation_consistent(self):
        """Verify same input always produces same slug."""
        service_class = institution_service.InstitutionService
        name = "Test University"
        
        slugs = [service_class._generate_slug(None, name) for _ in range(10)]
        assert all(s == slugs[0] for s in slugs), "Slug generation must be consistent"
    
    def test_payload_hash_deterministic(self):
        """Verify payload hash computation is deterministic."""
        service_class = institution_service.InstitutionService
        
        payload = {"z_key": 1, "a_key": 2, "m_key": 3}
        
        hashes = [service_class._compute_payload_hash(None, payload) for _ in range(10)]
        assert all(h == hashes[0] for h in hashes), "Payload hash must be deterministic"
        
        # Verify hash format
        assert len(hashes[0]) == 64, "Hash must be 64 hex chars"
        assert all(c in '0123456789abcdef' for c in hashes[0].lower()), "Must be hex"
    
    def test_payload_hash_order_independence(self):
        """Verify payload hash is independent of key order."""
        service_class = institution_service.InstitutionService
        
        payload1 = {"a": 1, "b": 2, "c": 3}
        payload2 = {"c": 3, "b": 2, "a": 1}
        
        hash1 = service_class._compute_payload_hash(None, payload1)
        hash2 = service_class._compute_payload_hash(None, payload2)
        
        assert hash1 == hash2, "Hash must be order-independent"
    
    def test_json_always_sort_keys(self):
        """Verify JSON serialization uses sort_keys=True."""
        source = inspect.getsource(institution_service)
        
        # Find json.dumps calls
        assert 'json.dumps' in source, "Must use json.dumps"
        assert 'sort_keys=True' in source, "Must use sort_keys=True"
        assert "separators=(',', ':')" in source, "Should use compact separators"


class TestAuditLogDeterminism:
    """Test audit log for determinism."""
    
    def test_audit_log_payload_sorted(self):
        """Verify audit log entries have sorted payloads."""
        source = inspect.getsource(institution_service.InstitutionService._log_action)
        
        assert 'sorted(payload.items())' in source, "Payload must be sorted before hashing"
    
    def test_audit_log_uses_utcnow(self):
        """Verify audit log uses utcnow, not now."""
        source = inspect.getsource(institution_service.InstitutionService._log_action)
        
        assert 'datetime.utcnow()' in source, "Must use utcnow()"
        assert 'datetime.now()' not in source, "Must not use now()"


class TestSourceCodeAudit:
    """Source code audit for forbidden patterns."""
    
    def test_tenant_guard_no_forbidden(self):
        """Audit tenant_guard for forbidden patterns."""
        source = inspect.getsource(tenant_guard)
        
        forbidden_patterns = [
            'datetime.now()',
            'random.rand',
            'random.choice',
            'time.time()',
            'hash(',  # Python hash()
        ]
        
        for pattern in forbidden_patterns:
            assert pattern not in source, f"tenant_guard contains forbidden pattern: {pattern}"
    
    def test_plan_service_no_forbidden(self):
        """Audit plan service for forbidden patterns."""
        source = inspect.getsource(plan_enforcement_service)
        
        forbidden_patterns = [
            'datetime.now()',
            'random.',
            'time.time()',
        ]
        
        for pattern in forbidden_patterns:
            assert pattern not in source, f"plan_enforcement_service contains forbidden pattern: {pattern}"
    
    def test_institution_service_no_forbidden(self):
        """Audit institution service for forbidden patterns."""
        source = inspect.getsource(institution_service)
        
        forbidden_patterns = [
            'datetime.now()',
            'random.',
            'time.time()',
        ]
        
        for pattern in forbidden_patterns:
            assert pattern not in source, f"institution_service contains forbidden pattern: {pattern}"


class TestORMDeterminism:
    """Test ORM models for determinism."""
    
    def test_institution_model_decimal_fields(self):
        """Verify Institution uses appropriate types."""
        # Check max_tournaments is integer
        from sqlalchemy import Integer, String, Boolean
        
        # These should be integers, not floats
        assert isinstance(Institution.max_tournaments.type, Integer)
        assert isinstance(Institution.max_concurrent_sessions.type, Integer)
        assert isinstance(Institution.allow_audit_export.type, Boolean)
        assert isinstance(Institution.status.type, String)
    
    def test_no_float_columns_in_orm(self):
        """Verify no Float columns in governance ORM."""
        from sqlalchemy import Float
        
        # Check Institution
        for col in Institution.__table__.columns:
            assert not isinstance(col.type, Float), f"Institution.{col.name} is Float - use Integer or Numeric"
        
        # Check InstitutionRole
        for col in InstitutionRole.__table__.columns:
            assert not isinstance(col.type, Float), f"InstitutionRole.{col.name} is Float"
        
        # Check InstitutionAuditLog
        for col in InstitutionAuditLog.__table__.columns:
            assert not isinstance(col.type, Float), f"InstitutionAuditLog.{col.name} is Float"


class TestRequiredPatterns:
    """Test required patterns are present."""
    
    def test_sha256_used_for_hashing(self):
        """Verify SHA256 is used for hashing."""
        source = inspect.getsource(institution_service)
        
        assert 'hashlib.sha256' in source, "Must use hashlib.sha256"
        assert 'sha256(' in source, "Must call sha256()"
    
    def test_role_comparisons_use_constants(self):
        """Verify role comparisons use constants, not strings."""
        source = inspect.getsource(tenant_guard)
        
        # Should reference ROLE_INSTITUTION_ADMIN constant
        assert 'ROLE_INSTITUTION_ADMIN' in source, "Should use ROLE_INSTITUTION_ADMIN constant"
    
    def test_all_hashes_sha256(self):
        """Verify all hash operations use SHA256."""
        institution_source = inspect.getsource(institution_service)
        
        # Should only use sha256
        assert 'hashlib.sha256' in institution_source
        # Should not use other hash algorithms
        assert 'md5' not in institution_source.lower()
        assert 'sha1' not in institution_source.lower()


class TestInstitutionScoping:
    """Test institution scoping in services."""
    
    def test_queries_include_institution_filter(self):
        """Verify queries include institution_id filter."""
        source = inspect.getsource(plan_enforcement_service)
        
        # Check for institution_id filters
        assert 'institution_id' in source, "Queries must filter by institution_id"
        assert 'institution_id ==' in source, "Must use equality comparison"
    
    def test_tenant_guard_has_scope_check(self):
        """Verify tenant guard has institution scope check."""
        source = inspect.getsource(tenant_guard.require_institution_scope)
        
        assert 'institution_id' in source, "Must check institution_id"
        assert '404' in source or 'NOT FOUND' in source, "Must return 404 on mismatch"


class TestSerializationDeterminism:
    """Test JSON serialization is deterministic."""
    
    def test_json_dumps_consistency(self):
        """Verify json.dumps produces consistent output."""
        data = {"z": 1, "a": 2, "m": 3}
        
        # Multiple dumps
        outputs = [json.dumps(data, sort_keys=True) for _ in range(10)]
        
        assert all(o == outputs[0] for o in outputs), "JSON must be consistent"
        
        # Verify sorting
        assert outputs[0].index('a') < outputs[0].index('m'), "Keys must be sorted"
        assert outputs[0].index('m') < outputs[0].index('z'), "Keys must be sorted"


class TestDecimalUsage:
    """Test Decimal usage for precision."""
    
    def test_plan_limits_use_decimal_comparison(self):
        """Verify plan limit comparisons use Decimal."""
        source = inspect.getsource(plan_enforcement_service.PlanEnforcementService.enforce_tournament_limit)
        
        assert 'Decimal' in source, "Must use Decimal for comparison"
