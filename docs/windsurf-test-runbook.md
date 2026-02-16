# Windsurf Full System Architecture Audit — Test Runbook

**Version:** 1.0  
**Date:** February 15, 2026  
**Scope:** Phases 14–21 (Moot Court Platform)  
**Environments:** local, staging, perf, prod

---

## Quick Start

Execute the full test suite with one command:

```bash
./scripts/run_full_audit.sh
```

Or step-by-step:

```bash
# 1. Environment snapshot
./scripts/snapshot_env.sh

# 2. Seed test data
python scripts/seed_test_data.py --teams 100 --matches 500

# 3. Run tests
pytest -q
python scripts/run_determinism_audits.py
python scripts/concurrency_harness.py --concurrency 50 --endpoint "/api/match/test-id/advance" --method POST
k6 run perf/k6/rankings_test.js

# 4. Generate report
python scripts/save_test_report.py artifacts/latest/results.json
```

---

## Test Execution Order

### Stage 0: Preconditions & Environment Snapshot

**Script:** `scripts/snapshot_env.sh`

**Purpose:** Capture environment state before testing

**Outputs:**
- `artifacts/env_snapshots/<timestamp>/`
  - `windsurf_env_snapshot.txt` — Environment variables
  - `windsurf_branch.txt` — Git branch
  - `windsurf_commit.txt` — Git commit hash
  - `windsurf_py_version.txt` — Python version
  - `windsurf_pip_freeze.txt` — Installed packages
  - `windsurf_db_schema.txt` — Database schema
  - `windsurf_feature_flags.txt` — Feature flag states

**Acceptance:**
- All files created
- No errors during execution

---

### Stage 1: Unit & Component Tests

**Command:**
```bash
pytest -q --maxfail=1
```

**Coverage:**
- Phase 14: Deterministic Round Engine
- Phase 15: AI Judge Intelligence
- Phase 16: Analytics & Ranking
- Phase 17: Appeals & Governance
- Phase 18: Scheduling & Allocation
- Phase 19: Moot Courtroom Operations
- Phase 20: Tournament Lifecycle
- Phase 21: Admin Command Center

**Pass Criteria:**
- 100% tests pass
- No deprecation warnings breaking determinism

**On Failure:**
```bash
# Capture failures
pytest -q 2>&1 | tee artifacts/unit_failures.log
python scripts/triage_failures.py --input artifacts/latest/results.json
```

---

### Stage 2: Integration Tests

**Command:**
```bash
pytest backend/tests/test_integration_*.py -q
```

**Test Scenarios:**

| ID | Scenario | Endpoint | Expected |
|----|----------|----------|----------|
| A1 | Auth + RBAC | `/api/auth/login` | JWT with correct scopes |
| A2 | Create Tournament → Lifecycle | POST `/api/lifecycle/create/{id}` | Lifecycle DRAFT state |
| A3 | Create Round/Matches | POST `/api/rounds` | Deterministic turn ordering |
| A4 | Freeze Match → Attempt Update | POST `/api/match/{id}/freeze` | 403 Forbidden |
| A5 | AI Official Evaluation | POST `/api/ai/evaluate/{id}` | evaluation_hash present |
| A6 | Analytics Recompute | POST `/api/analytics/recompute` | Deterministic ranks |
| A7 | Appeals Filing | POST `/api/appeals` | integrity_hash present |
| A8 | Scheduling | POST `/api/schedule/generate` | No overlap |
| A9 | Live Session Lifecycle | WebSocket + REST | Hash chain valid |
| A10 | Lifecycle Transitions | POST `/api/lifecycle/transition` | 409 for illegal transitions |
| A11 | Admin Center Operations | GET `/api/admin/overview` | Correct aggregation |

**Pass Criteria:**
- All scenarios pass
- HTTP status codes as expected
- Response times < 500ms

---

### Stage 3: Determinism & Integrity Audits

**Command:**
```bash
python scripts/run_determinism_audits.py --output artifacts/determinism
```

**Tests:**

| Test | Description | Pass Criteria |
|------|-------------|---------------|
| D1 | Snapshot hash determinism | Same match → identical SHA256 |
| D2 | Evaluation hash chaining | Recomputed hash matches stored |
| D3 | Session log chain | verify_log_integrity() == True |
| D4 | Standings hash reproducibility | Recomputed == stored |
| D5 | Cross-machine determinism | Identical hashes on two nodes |
| D6 | Phase 15 audit | All tests pass |
| D7 | Phase 20 audit | All tests pass |
| D8 | Phase 21 audit | All tests pass |

**Outputs:**
- `artifacts/determinism/determinism_audit_report.json`
- `artifacts/determinism/determinism_audit_report.md`

---

### Stage 4: Concurrency & Race Condition Tests

**Command:**
```bash
# C1: Double-advance flood
python scripts/concurrency_harness.py \
  --concurrency 50 \
  --endpoint "/api/match/{match_id}/advance" \
  --method POST \
  --test-name double_advance

# C2: Simultaneous freeze & complete
python scripts/concurrency_harness.py \
  --concurrency 30 \
  --endpoint "/api/match/{match_id}/freeze" \
  --method POST \
  --test-name freeze_race

# C3: Timer tick hammer
python scripts/concurrency_harness.py \
  --concurrency 100 \
  --endpoint "/api/timer/tick" \
  --method POST \
  --test-name timer_hammer

# C4: Multi-judge appeal reviews
python scripts/concurrency_harness.py \
  --concurrency 20 \
  --endpoint "/api/appeals/{id}/review" \
  --method POST \
  --payload '{"decision": "upheld"}' \
  --test-name appeal_reviews
```

**Pass Criteria:**
- No DB constraint violations
- No partial updates
- Expected error codes (409, 423) for contested operations
- Race conditions detected but handled gracefully

**Outputs:**
- `artifacts/concurrency/<test_name>_summary.json`
- `artifacts/concurrency/<test_name>_detailed.json`

---

### Stage 5: Crash-Recovery & Chaos Tests

**Manual Procedures:**

#### R1: Timer Recovery

```bash
# Start match timers
curl -X POST /api/match/{id}/start

# Kill backend
kill -9 $(pgrep -f "python backend/main.py")

# Restart server
python backend/main.py

# Verify recovery
curl /api/match/{id}/status
```

**Verify:**
- remaining_seconds updated
- Expired turns auto-completed
- original_remaining recorded

#### R2: DB Failover (Postgres)

```bash
# Simulate outage
sudo iptables -A INPUT -p tcp --dport 5432 -j DROP

# Wait 30s, verify app handles gracefully
curl /api/health

# Restore connection
sudo iptables -D INPUT -p tcp --dport 5432 -j DROP

# Verify recovery
```

#### R3: Worker Crash During Evaluation

```bash
# Trigger mock exception (use test endpoint)
curl -X POST /api/test/simulate-evaluation-crash

# Verify retry mechanism
curl /api/ai/evaluation/{id}/status
# Expected: pending_retry → completed
```

#### R4: Mid-Transaction OS Crash

```bash
# Start ranking recompute
curl -X POST /api/analytics/recompute &

# Kill during execution
kill -9 $!

# Verify consistency
curl /api/analytics/rankings
# Expected: No partial/inconsistent rankings
```

---

### Stage 6: Load & Stress Tests

#### L1: API Baseline (k6)

```bash
k6 run perf/k6/rankings_test.js
```

**Metrics:**
- 1000 RPS for 1 minute
- p95 latency < 200ms
- Error rate < 0.1%

#### L2: Concurrency Burst

```bash
python scripts/concurrency_harness.py \
  --concurrency 200 \
  --endpoint "/api/match/{id}/advance" \
  --method POST \
  --delay-ms 10
```

**Monitor:**
- DB locks
- Timeouts
- Error rates

#### L3: Bulk Freeze & Evaluation

```bash
# Seed 500 matches
python scripts/seed_test_data.py --matches 500

# Freeze all matches
./scripts/bulk_operation.sh freeze

# Queue evaluations
./scripts/bulk_operation.sh evaluate

# Monitor LLM router, token budget, DB throughput
```

#### L4: Timer Engine Stress

```bash
# Simulate 10k timers
python scripts/stress_timers.py --count 10000 --tpm 10000
```

**Metrics:**
- Tick processing latency < 50ms
- CPU < 80%
- Memory stable

#### L5: Soak Test

```bash
# 2 hours mixed load
k6 run perf/k6/soak_test.js --duration 2h
```

**Monitor:**
- Memory leak
- Increasing latency
- Error rate trend

---

### Stage 7: Security Tests

#### S1: RBAC & Auth

```bash
# Test all endpoints with all roles
python scripts/security_rbac_test.py
```

**Verify:**
- Sensitive endpoints reject unauthorized (403)
- Admin endpoints require admin role

#### S2: Injection & Input Validation

```bash
# Fuzz testing
python scripts/fuzz_test.py --endpoint /api/match --payloads fuzz_payloads.txt
```

#### S3: Secrets & Config

```bash
# Verify no secrets in logs
grep -r "api_key\|password\|secret" artifacts/logs/ || echo "No secrets found"
```

#### S4: Token Misuse

```bash
# Replay test
curl -H "Authorization: Bearer $OLD_TOKEN" /api/admin/overview
# Expected: 401
```

#### S5: Rate Limiting

```bash
# Burst test
python scripts/concurrency_harness.py \
  --concurrency 1000 \
  --endpoint "/api/auth/login" \
  --method POST
```

---

### Stage 8: End-to-End User Flow

**Automated Script:**
```bash
python scripts/e2e_flow.py --teams 100 --full
```

**Steps:**

1. **E1:** Admin creates tournament
2. **E2:** 100 teams register
3. **E3:** Scheduling creates slots (conflict-free)
4. **E4:** Round generation
5. **E5:** Start matches → Live sessions
6. **E6:** Participants join/leave, log events
7. **E7:** Complete matches, freeze
8. **E8:** AI shadow & official evaluation (cached)
9. **E9:** Rankings recompute
10. **E10:** File appeal → reviews → override
11. **E11:** Lifecycle transitions to COMPLETED/ARCHIVED
12. **E12:** Admin overview & integrity check
13. **E13:** Verify override results used in ranking

**Capture:**
- Request/response payloads
- DB rows created/updated
- Hashes computed
- Timestamps and logs

---

### Stage 9: Observability & Monitoring

#### O1: Structured Logs

```bash
# Verify critical actions logged
grep "FREEZE\|EVALUATE\|ADVANCE\|APPEAL" artifacts/logs/app.log
```

#### O2: Metrics

```bash
# Verify Prometheus metrics
curl /metrics | grep "moot_court_"
```

#### O3: Distributed Tracing

```bash
# Verify trace headers
curl -I /api/match/{id}/status | grep "X-Trace-Id"
```

#### O4: Alert Triggering

```bash
# Generate synthetic DB failure
python scripts/chaos_db_failure.py

# Verify alert fires (manual check)
```

---

### Stage 10: Disaster & Rollback

#### DR1: Migration Rollback

```bash
# Run migration
alembic upgrade head

# Attempt rollback
alembic downgrade -1

# Verify safe rollback or explicit failure
```

#### DR2: Restore from Backup

```bash
# Backup
pg_dump $PG_DB > /tmp/backup.sql

# Delete data
curl -X POST /api/admin/clear-test-data

# Restore
psql $PG_DB < /tmp/backup.sql

# Verify integrity hashes match
python scripts/verify_integrity.py
```

#### DR3: Release Rollback

```bash
# Deploy previous release
kubectl rollout undo deployment/moot-court

# Run smoke tests
python scripts/smoke_test.py
```

---

## Test Data & Fixtures

### Seeding

```bash
python scripts/seed_test_data.py \
  --teams 100 \
  --tournaments 1 \
  --matches 500 \
  --rounds 5 \
  --judges 20 \
  --courtrooms 10
```

**Deterministic UUIDs:**
- `tournament_0` → `tournament_id`
- `team_{i}` → team IDs
- `match_{round}_{match}` → match IDs

### Export/Import

```bash
# Export
python scripts/seed_test_data.py --export fixtures/seed_100_teams.json

# Import
python scripts/seed_test_data.py --import fixtures/seed_100_teams.json
```

---

## Performance Targets

| Metric | Target | Critical Threshold |
|--------|--------|-------------------|
| API p95 latency | < 200ms | > 500ms |
| Error rate | < 0.1% | > 1% |
| Concurrent judges | 200 | 50 |
| Timer events/min | 10,000 | 5,000 |
| LLM evaluations/min | 500 (mocked) | 100 |
| Memory usage | < 2GB | > 4GB |
| CPU usage | < 80% | > 95% |

---

## Acceptance Criteria

System passes when:

- [ ] Unit tests: 100% pass
- [ ] Integration tests: All scenarios pass
- [ ] Determinism audits: All hashes match
- [ ] Concurrency tests: No corruption, expected error codes
- [ ] Crash recovery: Timers/state recovered
- [ ] Load tests: Latency/error budgets met
- [ ] Security tests: Zero critical issues
- [ ] E2E flow: Completes without intervention
- [ ] Observability: Dashboards and alerts validated
- [ ] Backup/restore: Validated
- [ ] **Final markdown report saved to artifacts/**

---

## Post-Test Actions

### On Failure

```bash
# Generate triage report
python scripts/triage_failures.py \
  --input artifacts/latest/results.json \
  --output artifacts/triage

# Output: artifacts/triage/triage_report_<id>.md
```

**Triage includes:**
- Severity classification (P0/P1/P2/P3)
- Owner assignment (backend/frontend/devops/qa)
- Action items
- Hotfix recommendations
- Rollback recommendation (if P0 present)

### Report Generation

```bash
# Save final report (MANDATORY)
python scripts/save_test_report.py artifacts/latest/results.json

# Output: artifacts/<run_id>/windsurf_test_report_<id>.md
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install Dependencies
        run: pip install -r requirements.txt
      
      - name: Environment Snapshot
        run: ./scripts/snapshot_env.sh
      
      - name: Lint
        run: make lint
      
      - name: Unit Tests
        run: pytest -q
      
      - name: Integration Tests
        run: pytest backend/tests/test_integration_*.py -q
      
      - name: Determinism Audits
        run: python scripts/run_determinism_audits.py
      
      - name: Seed Data
        run: python scripts/seed_test_data.py --teams 50 --matches 100
      
      - name: Concurrency Tests
        run: python scripts/concurrency_harness.py --concurrency 50 --endpoint "/api/health"
      
      - name: Generate Report
        run: python scripts/save_test_report.py artifacts/latest/results.json
      
      - name: Upload Artifacts
        uses: actions/upload-artifact@v3
        with:
          name: test-reports
          path: artifacts/
```

---

## Quick Reference

### One-Liner Commands

```bash
# Full audit
./scripts/run_full_audit.sh

# Snapshot
./scripts/snapshot_env.sh

# Unit tests
pytest -q

# Determinism
python scripts/run_determinism_audits.py

# Concurrency
python scripts/concurrency_harness.py --concurrency 100 --endpoint "/api/health"

# Load test
k6 run perf/k6/rankings_test.js

# Seed data
python scripts/seed_test_data.py --teams 100 --matches 500

# Triage
python scripts/triage_failures.py --input artifacts/latest/results.json

# Report (MANDATORY FINAL STEP)
python scripts/save_test_report.py artifacts/latest/results.json
```

### Environment Variables

```bash
# Required
export DATABASE_URL="postgresql://user:pass@localhost/mootcourt"
export JWT_SECRET="test-secret"

# Optional
export FEATURE_ALL=True  # Enable all phases
export LOG_LEVEL=INFO
export K6_BASE_URL="http://localhost:8000"
```

---

## Troubleshooting

### Common Issues

**Issue:** `ModuleNotFoundError: No module named 'backend'`
**Fix:** Run from project root: `cd /path/to/IEEE && python scripts/...`

**Issue:** Database connection refused
**Fix:** Start Postgres: `docker-compose up -d postgres`

**Issue:** k6 not found
**Fix:** Install k6: `brew install k6` or `sudo apt-get install k6`

**Issue:** Port already in use
**Fix:** `lsof -ti:8000 | xargs kill -9`

---

## File Locations

```
scripts/
  snapshot_env.sh              # Environment capture
  seed_test_data.py              # Test data generation
  run_determinism_audits.py      # Determinism tests
  concurrency_harness.py         # Race condition tests
  triage_failures.py             # Failure analysis
  save_test_report.py            # Report generation
  run_full_audit.sh              # Master script

backend/tests/
  test_phase14_*.py             # Unit tests
  test_phase15_*.py
  ...
  test_integration_*.py          # Integration tests
  phase15_determinism_audit.py   # Determinism audits
  phase20_determinism_audit.py
  phase21_determinism_audit.py

perf/
  k6/
    rankings_test.js             # Load tests
    soak_test.js

artifacts/
  <run_id>/
    windsurf_test_report_<id>.md  # FINAL REPORT
    determinism/
    concurrency/
    triage/
```

---

## Contact & Support

- **Test Infrastructure:** Backend team
- **Performance Issues:** DevOps team
- **Security Issues:** Security team
- **Phase-specific bugs:** Respective phase owners

---

**End of Runbook**

*Remember: The final mandatory step is always `python scripts/save_test_report.py artifacts/latest/results.json`*
