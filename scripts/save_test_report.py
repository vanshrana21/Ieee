#!/usr/bin/env python3
"""
Windsurf Test Report Generator

Generates markdown test reports from test results JSON.
Usage: python scripts/save_test_report.py artifacts/latest/results.json
"""
import os
import sys
import json
import hashlib
import datetime
from pathlib import Path

# Template for test report
REPORT_TEMPLATE = """# Windsurf Full System Test Report

**Run ID:** {run_id}
**Date:** {date}
**Branch:** {branch} ({commit})
**Environment:** {env}
**Tester:** {tester}

## Summary

| Test Category | Status | Details |
|--------------|--------|---------|
| Unit tests | {unit_status} | {unit_details} |
| Integration tests | {integration_status} | {integration_details} |
| Determinism audits | {determinism_status} | {determinism_details} |
| Concurrency tests | {concurrency_status} | {concurrency_details} |
| Crash-Recovery tests | {crash_status} | {crash_details} |
| Load tests | {load_status} | {load_details} |
| Security tests | {security_status} | {security_details} |
| E2E flow | {e2e_status} | {e2e_details} |
| Observability | {obs_status} | {obs_details} |
| Backup/Restore | {dr_status} | {dr_details} |

**Overall Status:** {overall_status}

## Key Findings

{key_findings}

## Test Results by Phase

### Phase 14 - Deterministic Round Engine
- Status: {p14_status}
- Tests: {p14_tests}
- Failures: {p14_failures}

### Phase 15 - AI Judge Intelligence
- Status: {p15_status}
- Tests: {p15_tests}
- Failures: {p15_failures}

### Phase 16 - Analytics & Ranking
- Status: {p16_status}
- Tests: {p16_tests}
- Failures: {p16_failures}

### Phase 17 - Appeals & Governance
- Status: {p17_status}
- Tests: {p17_tests}
- Failures: {p17_failures}

### Phase 18 - Scheduling & Allocation
- Status: {p18_status}
- Tests: {p18_tests}
- Failures: {p18_failures}

### Phase 19 - Moot Courtroom Operations
- Status: {p19_status}
- Tests: {p19_tests}
- Failures: {p19_failures}

### Phase 20 - Tournament Lifecycle
- Status: {p20_status}
- Tests: {p20_tests}
- Failures: {p20_failures}

### Phase 21 - Admin Command Center
- Status: {p21_status}
- Tests: {p21_tests}
- Failures: {p21_failures}

## Failures & Artifacts

- Artifacts path: {artifacts_path}
- Unit failures log: {unit_failures_log}
- Integration failures log: {integration_failures_log}
- Concurrency results: {concurrency_results}
- Load test results: {load_results}

## Actions & Owners

{actions}

## Determinism Verification

- Snapshot hash determinism: {snapshot_determinism}
- Evaluation hash chaining: {evaluation_hash_valid}
- Session log chain: {session_log_valid}
- Standings hash reproducibility: {standings_hash_valid}

## Performance Metrics

- Avg response time (p95): {p95_latency}ms
- Max throughput: {max_throughput} RPS
- Error rate: {error_rate}%
- Memory usage: {memory_usage}MB

## Security Summary

- Critical issues: {security_critical}
- High issues: {security_high}
- Medium issues: {security_medium}
- Low issues: {security_low}

## Notes

{notes}

---
**Report saved by Windsurf test harness.**
Generated at: {timestamp}
"""


def load_results(results_path: str) -> dict:
    """Load test results from JSON file."""
    with open(results_path, 'r') as f:
        return json.load(f)


def generate_run_id(data: dict) -> str:
    """Generate unique run ID from data hash."""
    content = json.dumps(data, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def get_default_value(data: dict, key: str, default: str = "N/A") -> str:
    """Safely get value from data with default."""
    return data.get(key, default) if data.get(key) is not None else default


def render_report(data: dict) -> str:
    """Render test report from template and data."""
    run_id = generate_run_id(data)
    timestamp = datetime.datetime.utcnow().isoformat()
    
    # Prepare context
    context = {
        'run_id': run_id,
        'date': get_default_value(data, 'date', timestamp),
        'branch': get_default_value(data, 'branch', 'unknown'),
        'commit': get_default_value(data, 'commit', 'unknown'),
        'env': get_default_value(data, 'env', 'unknown'),
        'tester': get_default_value(data, 'tester', 'windsurf'),
        
        # Status values
        'unit_status': get_default_value(data, 'unit_status', 'NOT_RUN'),
        'unit_details': get_default_value(data, 'unit_details', ''),
        'integration_status': get_default_value(data, 'integration_status', 'NOT_RUN'),
        'integration_details': get_default_value(data, 'integration_details', ''),
        'determinism_status': get_default_value(data, 'determinism_status', 'NOT_RUN'),
        'determinism_details': get_default_value(data, 'determinism_details', ''),
        'concurrency_status': get_default_value(data, 'concurrency_status', 'NOT_RUN'),
        'concurrency_details': get_default_value(data, 'concurrency_details', ''),
        'crash_status': get_default_value(data, 'crash_status', 'NOT_RUN'),
        'crash_details': get_default_value(data, 'crash_details', ''),
        'load_status': get_default_value(data, 'load_status', 'NOT_RUN'),
        'load_details': get_default_value(data, 'load_details', ''),
        'security_status': get_default_value(data, 'security_status', 'NOT_RUN'),
        'security_details': get_default_value(data, 'security_details', ''),
        'e2e_status': get_default_value(data, 'e2e_status', 'NOT_RUN'),
        'e2e_details': get_default_value(data, 'e2e_details', ''),
        'obs_status': get_default_value(data, 'obs_status', 'NOT_RUN'),
        'obs_details': get_default_value(data, 'obs_details', ''),
        'dr_status': get_default_value(data, 'dr_status', 'NOT_RUN'),
        'dr_details': get_default_value(data, 'dr_details', ''),
        
        'overall_status': get_default_value(data, 'overall_status', 'INCOMPLETE'),
        'key_findings': get_default_value(data, 'key_findings', 'No findings recorded.'),
        
        # Phase results
        'p14_status': get_default_value(data, 'p14_status', 'NOT_RUN'),
        'p14_tests': get_default_value(data, 'p14_tests', '0'),
        'p14_failures': get_default_value(data, 'p14_failures', '0'),
        'p15_status': get_default_value(data, 'p15_status', 'NOT_RUN'),
        'p15_tests': get_default_value(data, 'p15_tests', '0'),
        'p15_failures': get_default_value(data, 'p15_failures', '0'),
        'p16_status': get_default_value(data, 'p16_status', 'NOT_RUN'),
        'p16_tests': get_default_value(data, 'p16_tests', '0'),
        'p16_failures': get_default_value(data, 'p16_failures', '0'),
        'p17_status': get_default_value(data, 'p17_status', 'NOT_RUN'),
        'p17_tests': get_default_value(data, 'p17_tests', '0'),
        'p17_failures': get_default_value(data, 'p17_failures', '0'),
        'p18_status': get_default_value(data, 'p18_status', 'NOT_RUN'),
        'p18_tests': get_default_value(data, 'p18_tests', '0'),
        'p18_failures': get_default_value(data, 'p18_failures', '0'),
        'p19_status': get_default_value(data, 'p19_status', 'NOT_RUN'),
        'p19_tests': get_default_value(data, 'p19_tests', '0'),
        'p19_failures': get_default_value(data, 'p19_failures', '0'),
        'p20_status': get_default_value(data, 'p20_status', 'NOT_RUN'),
        'p20_tests': get_default_value(data, 'p20_tests', '0'),
        'p20_failures': get_default_value(data, 'p20_failures', '0'),
        'p21_status': get_default_value(data, 'p21_status', 'NOT_RUN'),
        'p21_tests': get_default_value(data, 'p21_tests', '0'),
        'p21_failures': get_default_value(data, 'p21_failures', '0'),
        
        # Paths
        'artifacts_path': get_default_value(data, 'artifacts_path', './artifacts'),
        'unit_failures_log': get_default_value(data, 'unit_failures_log', 'N/A'),
        'integration_failures_log': get_default_value(data, 'integration_failures_log', 'N/A'),
        'concurrency_results': get_default_value(data, 'concurrency_results', 'N/A'),
        'load_results': get_default_value(data, 'load_results', 'N/A'),
        
        'actions': get_default_value(data, 'actions', 'No actions recorded.'),
        
        # Determinism
        'snapshot_determinism': get_default_value(data, 'snapshot_determinism', 'NOT_VERIFIED'),
        'evaluation_hash_valid': get_default_value(data, 'evaluation_hash_valid', 'NOT_VERIFIED'),
        'session_log_valid': get_default_value(data, 'session_log_valid', 'NOT_VERIFIED'),
        'standings_hash_valid': get_default_value(data, 'standings_hash_valid', 'NOT_VERIFIED'),
        
        # Performance
        'p95_latency': get_default_value(data, 'p95_latency', '0'),
        'max_throughput': get_default_value(data, 'max_throughput', '0'),
        'error_rate': get_default_value(data, 'error_rate', '0'),
        'memory_usage': get_default_value(data, 'memory_usage', '0'),
        
        # Security
        'security_critical': get_default_value(data, 'security_critical', '0'),
        'security_high': get_default_value(data, 'security_high', '0'),
        'security_medium': get_default_value(data, 'security_medium', '0'),
        'security_low': get_default_value(data, 'security_low', '0'),
        
        'notes': get_default_value(data, 'notes', ''),
        'timestamp': timestamp,
    }
    
    return REPORT_TEMPLATE.format(**context)


def save_report(report: str, run_id: str, output_dir: str = None) -> str:
    """Save report to artifacts directory."""
    if output_dir is None:
        # Determine project root
        script_dir = Path(__file__).parent
        project_root = script_dir.parent.parent
        output_dir = project_root / "artifacts" / run_id
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    report_path = output_dir / f"windsurf_test_report_{run_id}.md"
    
    with open(report_path, 'w') as f:
        f.write(report)
    
    return str(report_path)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/save_test_report.py <results.json> [output_dir]")
        print("  results.json: Path to test results JSON file")
        print("  output_dir: Optional output directory (default: ./artifacts/<run_id>/)")
        sys.exit(1)
    
    results_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not os.path.exists(results_path):
        print(f"Error: Results file not found: {results_path}")
        sys.exit(1)
    
    # Load results
    print(f"Loading results from: {results_path}")
    data = load_results(results_path)
    
    # Generate report
    print("Generating markdown report...")
    report = render_report(data)
    run_id = generate_run_id(data)
    
    # Save report
    report_path = save_report(report, run_id, output_dir)
    print(f"Report saved: {report_path}")
    
    # Create symlink to latest
    if output_dir is None:
        script_dir = Path(__file__).parent
        project_root = script_dir.parent.parent
        latest_link = project_root / "artifacts" / "latest"
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(Path(report_path).parent, target_is_directory=True)
        print(f"Symlink updated: artifacts/latest -> {run_id}")
    
    return report_path


if __name__ == "__main__":
    main()
