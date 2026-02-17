# Moot Court Feature Audit Report

## Overview
- Scope: Non-destructive, deterministic audit of Moot Court features (backend focus).
- Environment: macOS, Python 3.14, SQLAlchemy 2.0.46, SQLite dialect. Server started with .env on http://localhost:8001/.
- Method: Static checks, ORM import/configure checks, runtime probes, feature enumeration, and gap analysis.

## Files Found
- Routes
  - [ai_moot.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/ai_moot.py)
  - [ai_opponent.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/ai_opponent.py)
  - [oral_round_ai_hybrid.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/oral_round_ai_hybrid.py)
  - [oral_round_timer.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/oral_round_timer.py)
  - [classroom.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/classroom.py)
  - [live_courtroom_ws.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/live_courtroom_ws.py)
  - [phase19_moot_operations.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/phase19_moot_operations.py)
  - [moot_project_scheduling.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/moot_project_scheduling.py)
  - [auth.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/auth.py)
- Services / Realtime
  - [services/classroom/websocket.py](file:///Users/vanshrana/Desktop/IEEE/backend/services/classroom/websocket.py)
  - [websockets/classroom_ws.py](file:///Users/vanshrana/Desktop/IEEE/backend/websockets/classroom_ws.py)
  - [websockets/courtroom.py](file:///Users/vanshrana/Desktop/IEEE/backend/websockets/courtroom.py)
  - [realtime/ws_server.py](file:///Users/vanshrana/Desktop/IEEE/backend/realtime/ws_server.py)
  - [services/ai_judge_service.py](file:///Users/vanshrana/Desktop/IEEE/backend/services/ai_judge_service.py)
- ORM Models
  - [orm/oral_round.py](file:///Users/vanshrana/Desktop/IEEE/backend/orm/oral_round.py)
  - [orm/oral_round_score.py](file:///Users/vanshrana/Desktop/IEEE/backend/orm/oral_round_score.py)
  - [orm/classroom_round.py](file:///Users/vanshrana/Desktop/IEEE/backend/orm/classroom_round.py)
  - [orm/ai_oral_session.py](file:///Users/vanshrana/Desktop/IEEE/backend/orm/ai_oral_session.py)
  - [orm/moot_case.py](file:///Users/vanshrana/Desktop/IEEE/backend/orm/moot_case.py)
  - [orm/phase19_moot_operations.py](file:///Users/vanshrana/Desktop/IEEE/backend/orm/phase19_moot_operations.py)
  - [orm/__init__.py](file:///Users/vanshrana/Desktop/IEEE/backend/orm/__init__.py)
- Docs
  - [phase3_round_engine.md](file:///Users/vanshrana/Desktop/IEEE/backend/docs/phase3_round_engine.md)
  - [phase4_ai_judge.md](file:///Users/vanshrana/Desktop/IEEE/backend/docs/phase4_ai_judge.md)

## Automated Static Checks
- Requirements file: Not found (pip install -r requirements.txt → missing).
- Git status: Workspace not clean; numerous modified/untracked files including new leaderboard/match routes and services.
- Pytest targeted run: Collection failed early with 39 errors (e.g., duplicate table definitions, missing imports, reserved attribute names). Example errors:
  - InvalidRequestError: Table 'tournament_rounds' already defined
  - InvalidRequestError: Attribute name 'metadata' reserved in Declarative API
  - NameError: name 'Boolean' is not defined
  - NameError: name 'Column' is not defined
- Full pytest run: Same 39 collection errors; 100+ warnings.
- Ruff: 2015 errors; 1396 auto-fixable (example F541 f-string issues). Command used: python3 -m ruff check .
- Mypy: 3526 errors across 324 files; widespread typing mismatches and incorrect symbol usage.
- SQLAlchemy version: 2.0.46 captured.

## Schema & ORM Checks
- Import sweep over backend.orm package produced multiple failures:
  - [phase14_round_engine] Duplicate table error: 'tournament_rounds' already defined.
  - [phase19_moot_operations] Reserved attribute name 'metadata' in Declarative class and duplicate table references.
  - [phase21_admin_center] NameError: 'actor_id' used before definition in relationship; indicates model field missing or misordered.
- These indicate structural instability in ORM layer when importing all models together.

## Runtime Probes
- Server start: Success using .env on port 8001 with multiple feature flags disabled by default; database initialization completed; case library seeded.
- Health endpoint: GET /api/adaptive/health returned 200 with JSON body.
- OpenAPI: GET /openapi.json returned 500 via global error handler, indicating documentation generation issues or exception masking.
- AI Moot problems: GET /ai-moot/problems returned 404 even with valid bearer token; suggests router registration mismatch (path prefix) or error handler overriding route resolution.

## Feature Completeness Checklist
- AI Moot Practice Mode
  - Endpoints declared in [ai_moot.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/ai_moot.py) for listing problems, creating sessions, submitting turns.
  - Depends on [ai_judge_service.py](file:///Users/vanshrana/Desktop/IEEE/backend/services/ai_judge_service.py) mock/LLM; feature flags indicate evaluation engines mostly disabled at startup.
  - Status: Partially implemented; runtime access to endpoints failing under current router configuration or auth handling.
- Round Engine and Timer
  - Timer endpoints present in [oral_round_timer.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/oral_round_timer.py); Round engine hybrid endpoints in [oral_round_ai_hybrid.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/oral_round_ai_hybrid.py).
  - Status: Partially implemented; unit tests referencing tournament_rounds collide with ORM metadata → collection errors.
- Classroom WebSocket Sync
  - Two implementations present: [websockets/classroom_ws.py](file:///Users/vanshrana/Desktop/IEEE/backend/websockets/classroom_ws.py) (placeholder auth) and [services/classroom/websocket.py](file:///Users/vanshrana/Desktop/IEEE/backend/services/classroom/websocket.py) (AsyncSession, JWT auth).
  - Status: Partially implemented; requires consolidation and proper route registration from main app.
- RBAC and Auth
  - Multiple RBAC modules: [backend/rbac.py](file:///Users/vanshrana/Desktop/IEEE/backend/rbac.py) and [backend/security/rbac.py](file:///Users/vanshrana/Desktop/IEEE/backend/security/rbac.py). Auth works for registration and token issuance; discrepancies across modules likely cause inconsistent dependency usage.
  - Status: Partially implemented; needs normalization to avoid mismatched get_current_user implementations.
- ORM Models Integrity
  - Oral/Score/Classroom models exist and are reasonably defined; however, import of full ORM package reveals critical issues (duplicate tables, reserved attributes, missing fields).
  - Status: Structurally unstable.
- Documentation
  - Phase docs exist and describe intended behavior; runtime contradicts some guarantees (OpenAPI failure, test collection errors).
  - Status: Implemented docs; code not in full compliance.

## Missing or Broken Components
- Router registration alignment for AI Moot endpoints (observed 404 despite "routes registered" log).
- OpenAPI generation error masked by global exception handler.
- Consistent RBAC dependency usage across routes (two different modules).
- ORM stability issues: duplicate table definitions, reserved attribute names, and missing field references in Phase 19/21 modules.
- WebSocket authentication for classroom endpoints in [websockets/classroom_ws.py](file:///Users/vanshrana/Desktop/IEEE/backend/websockets/classroom_ws.py) uses placeholders; not production-safe.
- CI prerequisites: requirements.txt absent; tools installed ad hoc in environment.

## Final Verdict
- Overall Status: 60% COMPLETE
- Rationale:
  - Broad feature surface present with substantial implementation.
  - Critical structural problems in ORM and test collection block production confidence.
  - Runtime exposes selective endpoints, but route registration/auth alignment issues persist.
  - Tooling and type/lint hygiene far from passing levels required for production hardening.

## Exact Steps Required To Reach 100%
- Router & Auth
  - Align all routes to a single RBAC module; replace legacy imports with [backend/rbac.py](file:///Users/vanshrana/Desktop/IEEE/backend/rbac.py) or consolidate into one canonical module.
  - Verify AI Moot router inclusion path; confirm prefix and include_router calls in main, and fix 404s for /ai-moot endpoints.
  - Fix OpenAPI generation; remove or adapt global exception handler that returns opaque errors on documentation paths.
- ORM Integrity
  - Resolve duplicate table definitions (e.g., tournament_rounds) by ensuring single source of model truth; use extend_existing=True only if intentional.
  - Remove reserved attribute names like 'metadata' from Declarative classes in [phase19_moot_operations.py](file:///Users/vanshrana/Desktop/IEEE/backend/orm/phase19_moot_operations.py).
  - Define missing fields before relationships (e.g., actor_id in [phase21_admin_center.py](file:///Users/vanshrana/Desktop/IEEE/backend/orm/phase21_admin_center.py)).
  - Add mapper configuration tests that import all ORM models together to catch collisions.
- WebSocket Production Readiness
  - Replace placeholder auth in [websockets/classroom_ws.py](file:///Users/vanshrana/Desktop/IEEE/backend/websockets/classroom_ws.py) with JWT validation and session membership checks consistent with [services/classroom/websocket.py](file:///Users/vanshrana/Desktop/IEEE/backend/services/classroom/websocket.py).
  - Ensure route registration for session and round WebSockets in main app and add rate limiting.
- Testing & Tooling
  - Add requirements.txt and pin dependencies; include pytest, ruff, mypy, flake8.
  - Fix pytest collection errors by resolving ORM collisions and missing imports; enable asyncio marks via pytest-asyncio plugin.
  - Reduce ruff violations; enable --fix for trivial issues (e.g., F541) and configure pyproject.toml.
  - Address top mypy errors in routes using Column types as actual values; adjust typing or use ORM-to-schema mapping correctly.
- Feature Flags & Runtime
  - Review feature flag gating in main to ensure intended modules enabled for validation; add predictable defaults in .env for auditing.
  - Add smoke tests for key endpoints: health, auth, ai moot session create/turns, classroom session lifecycle, WebSocket connection handshake.

