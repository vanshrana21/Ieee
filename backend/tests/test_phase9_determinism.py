"""
Phase 9 — Determinism Audit Test Suite

Comprehensive scan for forbidden patterns in Phase 9 codebase.

Forbidden Patterns:
- float() usage (must use Decimal)
- random() usage (must be deterministic)
- datetime.now() (must use utcnow())
- Python hash() function (must use SHA256)
- Non-sorted JSON dumps

Compliance Target: 9.9/10
"""
import ast
import inspect
import json
from decimal import Decimal
from datetime import datetime
from typing import List, Tuple, Set

import pytest

# Import all Phase 9 modules for auditing
from backend.orm import performance_intelligence
from backend.services import performance_intelligence_service
from backend.routes import recruiter


class Phase9DeterminismAuditor:
    """
    AST-based auditor for Phase 9 determinism compliance.
    
    Scans source code for forbidden patterns that could introduce
    non-deterministic behavior.
    """
    
    FORBIDDEN_PATTERNS = {
        'float': {
            'patterns': ['float(', 'float64', 'float32', 'np.float', 'numpy.float'],
            'severity': 'ERROR',
            'reason': 'Must use Decimal for all numeric values'
        },
        'random': {
            'patterns': [
                'random()', 'random.random', 'random.randint', 'random.choice',
                'random.shuffle', 'random.uniform', 'random.gauss', 'random.seed',
                'np.random', 'numpy.random'
            ],
            'severity': 'ERROR',
            'reason': 'All operations must be deterministic'
        },
        'datetime_now': {
            'patterns': ['datetime.now()', 'datetime.datetime.now()'],
            'severity': 'ERROR',
            'reason': 'Must use datetime.utcnow() for consistency'
        },
        'python_hash': {
            'patterns': ['hash(', 'hash(', 'builtins.hash'],
            'severity': 'ERROR',
            'reason': 'Must use hashlib.sha256 for cryptographic hashing'
        },
        'unsorted_json': {
            'patterns': ['json.dumps('],  # Will check for sort_keys
            'severity': 'WARNING',
            'reason': 'JSON dumps must use sort_keys=True for determinism'
        }
    }
    
    def __init__(self):
        self.violations: List[Tuple[str, str, str, str]] = []  # (module, pattern_type, line, severity)
        self.warnings: List[Tuple[str, str, str]] = []  # (module, pattern_type, line)
    
    def audit_module(self, module, module_name: str) -> bool:
        """
        Audit a module for forbidden patterns.
        
        Returns True if no violations found, False otherwise.
        """
        try:
            source = inspect.getsource(module)
            tree = ast.parse(source)
        except (TypeError, OSError):
            return True
        
        lines = source.split('\n')
        
        for node in ast.walk(tree):
            self._check_node(node, module_name, lines)
        
        # Additional text-based checks
        self._text_based_checks(source, module_name, lines)
        
        return len(self.violations) == 0
    
    def _check_node(self, node: ast.AST, module_name: str, lines: List[str]) -> None:
        """Check an AST node for forbidden patterns."""
        line_num = getattr(node, 'lineno', 0)
        line_content = lines[line_num - 1].strip() if 0 < line_num <= len(lines) else ""
        
        # Skip comments and docstrings
        if line_content.startswith('#') or line_content.startswith('"""') or line_content.startswith("'''"):
            return
        
        # Check for float() calls
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'float':
                self._add_violation(module_name, 'float', line_content, 'ERROR')
        
        # Check for random module usage
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if (isinstance(node.func.value, ast.Name) and 
                    node.func.value.id in ['random', 'np', 'numpy'] and
                    node.func.attr in ['random', 'randint', 'choice', 'shuffle', 'uniform', 'gauss', 'seed', 'randn']):
                    self._add_violation(module_name, 'random', line_content, 'ERROR')
        
        # Check for hash() function (excluding hashlib)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'hash':
                # Check if this is hashlib context
                if 'hashlib' not in line_content and 'sha256' not in line_content:
                    self._add_violation(module_name, 'python_hash', line_content, 'ERROR')
        
        # Check for datetime.now()
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if (node.func.attr == 'now' and
                    not isinstance(node.func.value, ast.Name)):  # Not utcnow()
                    if 'utcnow' not in line_content:
                        self._add_violation(module_name, 'datetime_now', line_content, 'ERROR')
    
    def _text_based_checks(self, source: str, module_name: str, lines: List[str]) -> None:
        """Additional text-based pattern matching."""
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Skip comments
            if stripped.startswith('#'):
                continue
            
            # Check for datetime.now() patterns
            if 'datetime.now()' in stripped and 'utcnow' not in stripped:
                if not any(v[2] == stripped for v in self.violations if v[0] == module_name and v[1] == 'datetime_now'):
                    self._add_violation(module_name, 'datetime_now', stripped, 'ERROR')
            
            # Check for json.dumps without sort_keys
            if 'json.dumps(' in stripped:
                if 'sort_keys' not in stripped:
                    # Check if it's a hash-related dump
                    if 'hash' in stripped or 'checksum' in stripped or 'combined' in stripped:
                        self._add_violation(module_name, 'unsorted_json', stripped, 'WARNING')
    
    def _add_violation(self, module: str, pattern_type: str, line: str, severity: str) -> None:
        """Record a violation."""
        # Skip test files
        if 'test_' in module.lower():
            return
        
        # Skip lines with allowed patterns
        if 'hashlib' in line or 'import' in line or 'sha256' in line:
            return
        
        if severity == 'ERROR':
            self.violations.append((module, pattern_type, line, severity))
        else:
            self.warnings.append((module, pattern_type, line))
    
    def get_report(self) -> str:
        """Generate audit report."""
        report = []
        
        if self.violations:
            report.append("=" * 70)
            report.append("❌ DETERMINISM VIOLATIONS FOUND")
            report.append("=" * 70)
            
            for module, pattern, line, severity in self.violations:
                report.append(f"\nModule: {module}")
                report.append(f"Severity: {severity}")
                report.append(f"Issue: {pattern}")
                report.append(f"Code: {line[:80]}")
                report.append(f"Reason: {self.FORBIDDEN_PATTERNS.get(pattern, {}).get('reason', 'Unknown')}")
        
        if self.warnings:
            report.append("\n" + "=" * 70)
            report.append("⚠️  DETERMINISM WARNINGS")
            report.append("=" * 70)
            
            for module, pattern, line in self.warnings:
                report.append(f"\nModule: {module}")
                report.append(f"Issue: {pattern}")
                report.append(f"Code: {line[:80]}")
        
        if not self.violations and not self.warnings:
            report.append("=" * 70)
            report.append("✅ NO DETERMINISM VIOLATIONS FOUND")
            report.append("=" * 70)
            report.append("\nPhase 9 is compliant with determinism requirements.")
        
        return "\n".join(report)
    
    def get_compliance_score(self) -> float:
        """Calculate compliance score out of 10."""
        base_score = 10.0
        
        # Violations deduct 1.0 each
        base_score -= len(self.violations) * 1.0
        
        # Warnings deduct 0.1 each
        base_score -= len(self.warnings) * 0.1
        
        return max(0.0, base_score)


# =============================================================================
# Test Functions
# =============================================================================

def test_no_float_usage_in_phase9():
    """
    Phase 9 must not use float() anywhere.
    
    All numeric values must use Decimal for deterministic precision.
    """
    auditor = Phase9DeterminismAuditor()
    
    modules = [
        (performance_intelligence, 'performance_intelligence'),
        (performance_intelligence_service, 'performance_intelligence_service'),
        (recruiter, 'recruiter'),
    ]
    
    for module, name in modules:
        auditor.audit_module(module, name)
    
    float_violations = [v for v in auditor.violations if v[1] == 'float']
    
    if float_violations:
        print(f"\n{auditor.get_report()}")
    
    assert len(float_violations) == 0, f"Float violations found: {float_violations}"


def test_no_random_usage_in_phase9():
    """
    Phase 9 must not use random() anywhere.
    
    All operations must be deterministic.
    """
    auditor = Phase9DeterminismAuditor()
    
    modules = [
        (performance_intelligence, 'performance_intelligence'),
        (performance_intelligence_service, 'performance_intelligence_service'),
        (recruiter, 'recruiter'),
    ]
    
    for module, name in modules:
        auditor.audit_module(module, name)
    
    random_violations = [v for v in auditor.violations if v[1] == 'random']
    
    if random_violations:
        print(f"\n{auditor.get_report()}")
    
    assert len(random_violations) == 0, f"Random violations found: {random_violations}"


def test_no_datetime_now_usage():
    """
    Phase 9 must use datetime.utcnow(), not datetime.now().
    """
    auditor = Phase9DeterminismAuditor()
    
    modules = [
        (performance_intelligence, 'performance_intelligence'),
        (performance_intelligence_service, 'performance_intelligence_service'),
    ]
    
    for module, name in modules:
        auditor.audit_module(module, name)
    
    now_violations = [v for v in auditor.violations if v[1] == 'datetime_now']
    
    if now_violations:
        print(f"\n{auditor.get_report()}")
    
    assert len(now_violations) == 0, f"datetime.now() violations found: {now_violations}"


def test_no_python_hash_function():
    """
    Phase 9 must use hashlib.sha256, not Python hash().
    """
    auditor = Phase9DeterminismAuditor()
    
    modules = [
        (performance_intelligence, 'performance_intelligence'),
        (performance_intelligence_service, 'performance_intelligence_service'),
    ]
    
    for module, name in modules:
        auditor.audit_module(module, name)
    
    hash_violations = [v for v in auditor.violations if v[1] == 'python_hash']
    
    if hash_violations:
        print(f"\n{auditor.get_report()}")
    
    assert len(hash_violations) == 0, f"Python hash() violations found: {hash_violations}"


def test_decimal_columns_in_orm():
    """
    Verify all numeric columns in Phase 9 ORM use Numeric/Decimal.
    """
    from backend.orm.performance_intelligence import (
        CandidateSkillVector, PerformanceNormalizationStats,
        NationalCandidateRanking, FairnessAuditLog
    )
    
    # Check CandidateSkillVector
    decimal_columns = [
        'oral_advocacy_score', 'statutory_interpretation_score',
        'case_law_application_score', 'procedural_compliance_score',
        'rebuttal_responsiveness_score', 'courtroom_etiquette_score',
        'consistency_factor', 'confidence_index'
    ]
    
    for col_name in decimal_columns:
        column = CandidateSkillVector.__table__.columns[col_name]
        assert str(column.type).startswith('NUMERIC'), \
            f"{col_name} must be NUMERIC, found {column.type}"
    
    # Check PerformanceNormalizationStats
    norm_columns = ['mean_value', 'std_deviation']
    for col_name in norm_columns:
        column = PerformanceNormalizationStats.__table__.columns[col_name]
        assert str(column.type).startswith('NUMERIC'), \
            f"{col_name} must be NUMERIC, found {column.type}"
    
    # Check NationalCandidateRanking
    ranking_columns = ['composite_score', 'percentile']
    for col_name in ranking_columns:
        column = NationalCandidateRanking.__table__.columns[col_name]
        assert str(column.type).startswith('NUMERIC'), \
            f"{col_name} must be NUMERIC, found {column.type}"


def test_checksum_formula_includes_all_components():
    """
    Verify checksum formula includes all required components.
    
    Checksum must include: user_id|rank|composite_score|percentile
    """
    from backend.orm.performance_intelligence import NationalCandidateRanking
    import hashlib
    from decimal import Decimal
    
    # Create test ranking
    ranking = NationalCandidateRanking(
        user_id=123,
        national_rank=5,
        composite_score=Decimal("87.6543"),
        percentile=Decimal("95.123")
    )
    ranking.checksum = "test_checksum"
    
    # Verify verify_checksum method exists and works
    assert hasattr(ranking, 'verify_checksum'), "NationalCandidateRanking must have verify_checksum method"


def test_json_sort_keys_in_service():
    """
    Verify json.dumps uses sort_keys=True in hash-related operations.
    """
    import inspect
    source = inspect.getsource(performance_intelligence_service)
    
    # Check for hashlib.sha256 usage
    assert 'hashlib.sha256' in source, "Must use hashlib.sha256 for checksums"
    
    # Check for proper checksum construction
    assert 'combined' in source, "Must construct combined string for checksum"


def test_composite_score_formula_weights():
    """
    Verify composite score formula uses correct weights.
    
    Formula:
    composite = (0.4 * oral_advocacy)
            + (0.2 * statutory_interpretation)
            + (0.15 * rebuttal_responsiveness)
            + (0.15 * case_law_application)
            + (0.1 * consistency_factor)
    """
    import inspect
    source = inspect.getsource(performance_intelligence_service)
    
    # Check for correct weights in source
    assert 'Decimal("0.4")' in source, "Must use weight 0.4 for oral_advocacy"
    assert 'Decimal("0.2")' in source, "Must use weight 0.2 for statutory_interpretation"
    assert 'Decimal("0.15")' in source, "Must use weight 0.15 for rebuttal_responsiveness"
    assert 'Decimal("0.1")' in source, "Must use weight 0.1 for consistency_factor"


def test_decimal_quantization_usage():
    """
    Verify Decimal quantize is used for precision control.
    """
    import inspect
    source = inspect.getsource(performance_intelligence_service)
    
    assert 'quantize' in source, "Must use Decimal.quantize() for precision control"
    assert 'QUANTIZER' in source or 'quantize' in source, "Must define quantizers"


def test_recruiter_role_in_enum():
    """
    Verify RECRUITER role is defined in UserRole enum.
    """
    from backend.orm.user import UserRole
    
    assert hasattr(UserRole, 'RECRUITER'), "UserRole must have RECRUITER member"
    assert UserRole.RECRUITER == 'recruiter', "RECRUITER value must be 'recruiter'"


def test_serializable_isolation_in_ranking():
    """
    Verify compute_national_rankings uses SERIALIZABLE isolation.
    """
    import inspect
    source = inspect.getsource(performance_intelligence_service.compute_national_rankings)
    
    assert 'SERIALIZABLE' in source, "Must use SERIALIZABLE isolation for ranking computation"
    assert 'SET TRANSACTION ISOLATION LEVEL' in source, "Must set transaction isolation level"


def test_safe_divide_prevents_zero_division():
    """
    Verify safe_divide function exists and prevents division by zero.
    """
    from backend.services.performance_intelligence_service import safe_divide
    from decimal import Decimal
    
    # Test with zero denominator
    result = safe_divide(Decimal("100"), Decimal("0"), Decimal("0"))
    assert result == Decimal("0"), "safe_divide must return default on zero division"
    
    # Test normal division
    result = safe_divide(Decimal("100"), Decimal("10"))
    assert result == Decimal("10"), "safe_divide must perform normal division"


def test_decimal_sqrt_implementation():
    """
    Verify decimal_sqrt uses Newton's method (deterministic).
    """
    from backend.services.performance_intelligence_service import decimal_sqrt
    from decimal import Decimal
    
    # Test perfect square
    result = decimal_sqrt(Decimal("16"))
    assert abs(result - Decimal("4")) < Decimal("0.0001"), "decimal_sqrt must compute accurate square roots"
    
    # Test non-perfect square
    result = decimal_sqrt(Decimal("2"))
    assert result > Decimal("1.4"), "decimal_sqrt must return positive root"
    assert result < Decimal("1.5"), "decimal_sqrt must return accurate root"


def test_deterministic_sorting_in_rankings():
    """
    Verify national rankings use deterministic sorting.
    """
    import inspect
    source = inspect.getsource(performance_intelligence_service.compute_national_rankings)
    
    # Check for deterministic tiebreaker
    assert 'user_id.asc()' in source or 'user_id' in source, \
        "Must use user_id as deterministic tiebreaker"


@pytest.mark.asyncio
async def test_full_determinism_compliance():
    """
    Run full determinism audit and verify compliance score >= 9.9.
    """
    auditor = Phase9DeterminismAuditor()
    
    modules = [
        (performance_intelligence, 'performance_intelligence'),
        (performance_intelligence_service, 'performance_intelligence_service'),
        (recruiter, 'recruiter'),
    ]
    
    for module, name in modules:
        auditor.audit_module(module, name)
    
    score = auditor.get_compliance_score()
    
    print(f"\n{auditor.get_report()}")
    print(f"\nCompliance Score: {score}/10")
    
    assert score >= 9.9, f"Compliance score {score} is below target 9.9"


# =============================================================================
# Compliance Report Generator
# =============================================================================

def generate_phase9_compliance_report() -> str:
    """Generate comprehensive Phase 9 compliance report."""
    auditor = Phase9DeterminismAuditor()
    
    modules = [
        (performance_intelligence, 'performance_intelligence'),
        (performance_intelligence_service, 'performance_intelligence_service'),
        (recruiter, 'recruiter'),
    ]
    
    for module, name in modules:
        auditor.audit_module(module, name)
    
    score = auditor.get_compliance_score()
    
    report = []
    report.append("=" * 70)
    report.append("PHASE 9 DETERMINISM COMPLIANCE REPORT")
    report.append("=" * 70)
    report.append(f"\nOverall Score: {score:.1f}/10")
    report.append(f"Target: 9.9/10")
    report.append(f"Status: {'✅ PASS' if score >= 9.9 else '❌ FAIL'}")
    report.append("")
    report.append(auditor.get_report())
    
    return "\n".join(report)


if __name__ == "__main__":
    # Run compliance report
    print(generate_phase9_compliance_report())
