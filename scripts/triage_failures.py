#!/usr/bin/env python3
"""
Windsurf Test Failure Triage Tool

Analyzes test failures and generates triage reports with severity and action items.
Usage: python scripts/triage_failures.py --input artifacts/latest/results.json
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class Severity(Enum):
    """Failure severity levels."""
    P0 = "P0"  # Critical - blocks release
    P1 = "P1"  # High - must fix before release
    P2 = "P2"  # Medium - fix in next sprint
    P3 = "P3"  # Low - nice to have


@dataclass
class Failure:
    """Represents a test failure."""
    test_id: str
    category: str  # unit, integration, determinism, concurrency, etc.
    phase: str
    error_message: str
    stack_trace: Optional[str]
    severity: Severity
    owner: str  # backend, frontend, devops, qa
    action: str
    retry_possible: bool


@dataclass
class TriageReport:
    """Complete triage report."""
    run_id: str
    timestamp: str
    total_failures: int
    by_severity: Dict[str, int]
    by_category: Dict[str, int]
    by_owner: Dict[str, int]
    p0_failures: List[Failure]
    p1_failures: List[Failure]
    p2_failures: List[Failure]
    p3_failures: List[Failure]
    hotfixes_required: List[str]
    rollback_recommended: bool


class FailureClassifier:
    """Classifies test failures by severity and owner."""
    
    # Keywords that indicate severity
    CRITICAL_KEYWORDS = [
        'determinism', 'hash_mismatch', 'race_condition', 'data_loss',
        'security_vulnerability', 'rbac_bypass', 'injection', 'crash'
    ]
    
    HIGH_KEYWORDS = [
        'concurrent', 'timeout', 'lock', 'deadlock', 'constraint_violation',
        'integrity', 'hash_invalid', 'corruption'
    ]
    
    # Keywords that indicate owner
    BACKEND_KEYWORDS = ['orm', 'database', 'sql', 'service', 'route', 'api']
    DEVOPS_KEYWORDS = ['infra', 'deploy', 'config', 'env', 'container']
    QA_KEYWORDS = ['test', 'fixture', 'mock', 'stub']
    
    @classmethod
    def classify_severity(cls, error_message: str, category: str) -> Severity:
        """Classify failure severity."""
        msg_lower = error_message.lower()
        
        # Check critical keywords
        for keyword in cls.CRITICAL_KEYWORDS:
            if keyword in msg_lower:
                return Severity.P0
        
        # Check high keywords
        for keyword in cls.HIGH_KEYWORDS:
            if keyword in msg_lower:
                return Severity.P1
        
        # Category-based classification
        if category in ['determinism', 'security', 'crash_recovery']:
            return Severity.P0
        
        if category == 'concurrency':
            return Severity.P1
        
        if category == 'load':
            return Severity.P2
        
        return Severity.P2  # Default medium
    
    @classmethod
    def classify_owner(cls, error_message: str, category: str) -> str:
        """Classify failure owner."""
        msg_lower = error_message.lower()
        
        for keyword in cls.BACKEND_KEYWORDS:
            if keyword in msg_lower:
                return 'backend'
        
        for keyword in cls.DEVOPS_KEYWORDS:
            if keyword in msg_lower:
                return 'devops'
        
        for keyword in cls.QA_KEYWORDS:
            if keyword in msg_lower:
                return 'qa'
        
        # Category-based
        if category in ['unit', 'integration']:
            return 'backend'
        
        if category in ['load', 'chaos']:
            return 'devops'
        
        return 'backend'  # Default
    
    @classmethod
    def suggest_action(cls, error_message: str, severity: Severity) -> str:
        """Suggest action based on failure."""
        if severity == Severity.P0:
            return "Immediate investigation and hotfix required"
        
        if severity == Severity.P1:
            return "Fix before next release"
        
        if 'timeout' in error_message.lower():
            return "Review timeout configuration and performance"
        
        if 'lock' in error_message.lower():
            return "Review locking strategy and concurrency"
        
        if 'hash' in error_message.lower():
            return "Review hash generation logic for determinism"
        
        return "Standard bug fix process"


class TriageTool:
    """Tool for triaging test failures."""
    
    def __init__(self, results_path: str, output_dir: str):
        self.results_path = Path(results_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.failures: List[Failure] = []
    
    def load_and_parse(self):
        """Load test results and parse failures."""
        print(f"Loading results from: {self.results_path}")
        
        with open(self.results_path, 'r') as f:
            data = json.load(f)
        
        # Parse failures from different sections
        self._parse_unit_failures(data)
        self._parse_integration_failures(data)
        self._parse_determinism_failures(data)
        self._parse_concurrency_failures(data)
        self._parse_load_failures(data)
        self._parse_security_failures(data)
        
        print(f"Parsed {len(self.failures)} failures")
    
    def _parse_unit_failures(self, data: Dict):
        """Parse unit test failures."""
        unit_failures = data.get('unit_failures', [])
        for failure in unit_failures:
            self._add_failure(
                test_id=failure.get('test_id', 'unknown'),
                category='unit',
                phase=failure.get('phase', 'unknown'),
                error_message=failure.get('error', 'No error message'),
                stack_trace=failure.get('stack_trace')
            )
    
    def _parse_integration_failures(self, data: Dict):
        """Parse integration test failures."""
        integration_failures = data.get('integration_failures', [])
        for failure in integration_failures:
            self._add_failure(
                test_id=failure.get('test_id', 'unknown'),
                category='integration',
                phase=failure.get('phase', 'unknown'),
                error_message=failure.get('error', 'No error message'),
                stack_trace=failure.get('stack_trace')
            )
    
    def _parse_determinism_failures(self, data: Dict):
        """Parse determinism audit failures."""
        determinism_results = data.get('determinism_results', [])
        for result in determinism_results:
            if not result.get('passed', True):
                self._add_failure(
                    test_id=result.get('test_name', 'unknown'),
                    category='determinism',
                    phase=result.get('phase', 'unknown'),
                    error_message=result.get('details', {}).get('error', 'Determinism check failed'),
                    stack_trace=None
                )
    
    def _parse_concurrency_failures(self, data: Dict):
        """Parse concurrency test failures."""
        concurrency_results = data.get('concurrency_results', {})
        if concurrency_results.get('race_conditions_detected', False):
            self._add_failure(
                test_id='race_condition',
                category='concurrency',
                phase='multi',
                error_message='Race conditions detected in concurrent test execution',
                stack_trace=None
            )
    
    def _parse_load_failures(self, data: Dict):
        """Parse load test failures."""
        load_results = data.get('load_results', {})
        if load_results.get('latency_p95', 0) > 500:  # 500ms threshold
            self._add_failure(
                test_id='load_latency',
                category='load',
                phase='multi',
                error_message=f"High latency detected: p95={load_results.get('latency_p95')}ms",
                stack_trace=None
            )
        
        if load_results.get('error_rate', 0) > 0.01:  # 1% threshold
            self._add_failure(
                test_id='load_errors',
                category='load',
                phase='multi',
                error_message=f"High error rate detected: {load_results.get('error_rate')}%",
                stack_trace=None
            )
    
    def _parse_security_failures(self, data: Dict):
        """Parse security test failures."""
        security_results = data.get('security_results', {})
        critical_count = security_results.get('critical', 0)
        if critical_count > 0:
            self._add_failure(
                test_id='security_critical',
                category='security',
                phase='multi',
                error_message=f"{critical_count} critical security vulnerabilities found",
                stack_trace=None
            )
    
    def _add_failure(self, test_id: str, category: str, phase: str,
                     error_message: str, stack_trace: Optional[str]):
        """Add a classified failure."""
        severity = FailureClassifier.classify_severity(error_message, category)
        owner = FailureClassifier.classify_owner(error_message, category)
        action = FailureClassifier.suggest_action(error_message, severity)
        
        failure = Failure(
            test_id=test_id,
            category=category,
            phase=phase,
            error_message=error_message,
            stack_trace=stack_trace,
            severity=severity,
            owner=owner,
            action=action,
            retry_possible=category not in ['determinism', 'race_condition']
        )
        
        self.failures.append(failure)
    
    def generate_report(self) -> TriageReport:
        """Generate triage report."""
        # Group by severity
        p0 = [f for f in self.failures if f.severity == Severity.P0]
        p1 = [f for f in self.failures if f.severity == Severity.P1]
        p2 = [f for f in self.failures if f.severity == Severity.P2]
        p3 = [f for f in self.failures if f.severity == Severity.P3]
        
        # Count by category
        by_category: Dict[str, int] = {}
        for f in self.failures:
            by_category[f.category] = by_category.get(f.category, 0) + 1
        
        # Count by owner
        by_owner: Dict[str, int] = {}
        for f in self.failures:
            by_owner[f.owner] = by_owner.get(f.owner, 0) + 1
        
        # Hotfixes required
        hotfixes = [f.test_id for f in p0 if f.severity == Severity.P0]
        
        # Recommend rollback if any P0 failures
        rollback_recommended = len(p0) > 0
        
        return TriageReport(
            run_id=self._generate_run_id(),
            timestamp=datetime.utcnow().isoformat(),
            total_failures=len(self.failures),
            by_severity={
                'P0': len(p0),
                'P1': len(p1),
                'P2': len(p2),
                'P3': len(p3)
            },
            by_category=by_category,
            by_owner=by_owner,
            p0_failures=p0,
            p1_failures=p1,
            p2_failures=p2,
            p3_failures=p3,
            hotfixes_required=hotfixes,
            rollback_recommended=rollback_recommended
        )
    
    def _generate_run_id(self) -> str:
        """Generate run ID from timestamp."""
        return datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    
    def save_reports(self, report: TriageReport):
        """Save triage reports."""
        # JSON report
        json_path = self.output_dir / f'triage_report_{report.run_id}.json'
        with open(json_path, 'w') as f:
            json.dump(asdict(report), f, indent=2, default=lambda x: x.value if isinstance(x, Enum) else str(x))
        
        # Markdown report
        md_path = self.output_dir / f'triage_report_{report.run_id}.md'
        self._save_markdown_report(report, md_path)
        
        print(f"\nReports saved:")
        print(f"  JSON: {json_path}")
        print(f"  Markdown: {md_path}")
        
        return str(md_path)
    
    def _save_markdown_report(self, report: TriageReport, path: Path):
        """Save markdown report."""
        lines = [
            "# Windsurf Test Failure Triage Report",
            "",
            f"**Run ID:** {report.run_id}",
            f"**Timestamp:** {report.timestamp}",
            f"**Total Failures:** {report.total_failures}",
            "",
            "## Summary",
            "",
            "### By Severity",
            f"- P0 (Critical): {report.by_severity.get('P0', 0)}",
            f"- P1 (High): {report.by_severity.get('P1', 0)}",
            f"- P2 (Medium): {report.by_severity.get('P2', 0)}",
            f"- P3 (Low): {report.by_severity.get('P3', 0)}",
            "",
            "### By Category",
        ]
        
        for category, count in report.by_category.items():
            lines.append(f"- {category}: {count}")
        
        lines.extend([
            "",
            "### By Owner",
        ])
        
        for owner, count in report.by_owner.items():
            lines.append(f"- {owner}: {count}")
        
        # P0 Failures
        if report.p0_failures:
            lines.extend([
                "",
                "## 🔴 P0 Failures (Critical - Blocks Release)",
                "",
            ])
            for failure in report.p0_failures:
                lines.extend([
                    f"### {failure.test_id}",
                    f"- **Category:** {failure.category}",
                    f"- **Phase:** {failure.phase}",
                    f"- **Owner:** {failure.owner}",
                    f"- **Action:** {failure.action}",
                    f"- **Error:** {failure.error_message[:200]}...",
                    "",
                ])
        
        # P1 Failures
        if report.p1_failures:
            lines.extend([
                "",
                "## 🟠 P1 Failures (High - Fix Before Release)",
                "",
            ])
            for failure in report.p1_failures:
                lines.extend([
                    f"### {failure.test_id}",
                    f"- **Category:** {failure.category}",
                    f"- **Phase:** {failure.phase}",
                    f"- **Owner:** {failure.owner}",
                    f"- **Action:** {failure.action}",
                    "",
                ])
        
        # Recommendations
        lines.extend([
            "",
            "## Recommendations",
            "",
        ])
        
        if report.rollback_recommended:
            lines.extend([
                "⚠️ **ROLLBACK RECOMMENDED**",
                "",
                "Critical failures detected. Consider rolling back to previous stable release.",
                "",
            ])
        
        if report.hotfixes_required:
            lines.extend([
                "### Hotfixes Required",
                "",
            ])
            for hotfix in report.hotfixes_required:
                lines.append(f"- [ ] {hotfix}")
        
        with open(path, 'w') as f:
            f.write('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(
        description='Windsurf Test Failure Triage Tool'
    )
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='Path to test results JSON file'
    )
    parser.add_argument(
        '--output', '-o',
        default='./artifacts/triage',
        help='Output directory for triage reports'
    )
    
    args = parser.parse_args()
    
    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
    
    # Create tool and run
    tool = TriageTool(args.input, args.output)
    tool.load_and_parse()
    report = tool.generate_report()
    
    # Print summary
    print(f"\n=== Triage Summary ===")
    print(f"Total Failures: {report.total_failures}")
    print(f"  P0 (Critical): {report.by_severity.get('P0', 0)}")
    print(f"  P1 (High): {report.by_severity.get('P1', 0)}")
    print(f"  P2 (Medium): {report.by_severity.get('P2', 0)}")
    print(f"  P3 (Low): {report.by_severity.get('P3', 0)}")
    
    if report.rollback_recommended:
        print("\n⚠️  ROLLBACK RECOMMENDED - Critical failures detected")
    
    # Save reports
    report_path = tool.save_reports(report)
    print(f"\nTriage report: {report_path}")
    
    # Exit with error code if P0 failures
    sys.exit(1 if report.by_severity.get('P0', 0) > 0 else 0)


if __name__ == "__main__":
    main()
