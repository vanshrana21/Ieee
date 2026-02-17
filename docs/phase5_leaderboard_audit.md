# Phase 5 – Leaderboard Engine Audit Report

## Files Found
- Feature flags: [feature_flags.py](file:///Users/vanshrana/Desktop/IEEE/backend/config/feature_flags.py)
- App router gating: [main.py](file:///Users/vanshrana/Desktop/IEEE/backend/main.py#L320-L370)
- Phase 5 API router: [leaderboard.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/leaderboard.py#L46-L92)
- Phase 5 service layer: [leaderboard_service.py](file:///Users/vanshrana/Desktop/IEEE/backend/services/leaderboard_service.py#L114-L356)
- Deterministic ranking: [leaderboard_service.py](file:///Users/vanshrana/Desktop/IEEE/backend/services/leaderboard_service.py#L524-L602)
- Checksum integrity: [leaderboard_service.py](file:///Users/vanshrana/Desktop/IEEE/backend/services/leaderboard_service.py#L605-L642)
- Snapshot/entry/audit ORM: [session_leaderboard.py](file:///Users/vanshrana/Desktop/IEEE/backend/orm/session_leaderboard.py#L35-L131), [SessionLeaderboardEntry](file:///Users/vanshrana/Desktop/IEEE/backend/o  rm/session_leaderboard.py#L201-L269), [SessionLeaderboardAudit](file:///Users/vanshrana/Desktop/IEEE/backend/orm/session_leaderboard.py#L293-L336)
- ORM immutability guards: [session_leaderboard.py](file:///Users/vanshrana/Desktop/IEEE/backend/orm/session_leaderboard.py#L354-L395)
- Phase 5 tests: [test_leaderboard.py](file:///Users/vanshrana/Desktop/IEEE/backend/tests/test_leaderboard.py#L329-L390)
- Legacy classroom leaderboard (duplicate): [classroom_sessions.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/classroom_sessions.py#L309-L343)
- Competitive (Phase 6) leaderboard: [competitive_leaderboard.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/competitive_leaderboard.py), [competitive_leaderboard_service.py](file:///Users/vanshrana/Desktop/IEEE/backend/services/competitive_leaderboard_service.py)
- Player rating models: [player_ratings.py](file:///Users/vanshrana/Desktop/IEEE/backend/orm/player_ratings.py)
- Rating service (ELO): [rating_service.py](file:///Users/vanshrana/Desktop/IEEE/backend/services/rating_service.py#L298-L352)

## Feature Checklist
- Rating calculation (ELO with K-factor) — ✅ Implemented in RatingService; updates PlayerRating and RatingHistory
- Immutable snapshot creation — ✅ Implemented; unique per session; checksum stored
- Idempotent freeze (concurrency) — ✅ Implemented via IntegrityError handling and SERIALIZABLE isolation for Postgres
- Deterministic ranking (dense rank + tiebreakers) — ⚠️ Implemented but mismatched keys (final_score vs total_score)
- Checksum integrity verification — ✅ Implemented (SHA256 over ordered entries)
- Feature flag gating — ✅ Implemented; router conditionally registered
- Freeze endpoint (faculty-only) — ⚠️ Exists but returns wrong type; service returns tuple, router assumes object
- Leaderboard retrieval with integrity flag — ✅ Implemented
- Status endpoint (pre-flight readiness) — ✅ Implemented
- Admin invalidation (soft delete) — ✅ Implemented; snapshots never physically deleted
- ORM immutability guards — ✅ Implemented; before_update prevents modifications
- Database constraints (unique session, rank integrity) — ✅ Implemented
- Pagination for Phase 5 endpoints — ❌ Missing
- Filters (institution/publication visibility on Phase 5) — ❌ Missing at Phase 5 layer; present in Phase 5E/6 views
- Database joins (avoid N+1) — ✅ Implemented in service queries
- Caching of computed leaderboards — ❌ Missing
- Admin overrides affecting rankings — ❌ Missing integration with FacultyOverride or appeals
- Tie-break transparency (explicit breakdown exposure) — ⚠️ Partial; tie_breaker_score exists but not explained in API
- Tests (unit/integration) — ⚠️ Present but inconsistent with service keys; many API tests are environment-dependent
- Documentation alignment vs code — ⚠️ Phase 5 “Elite Hardening” doc claims zero float usage; router returns floats in JSON

## Structural Issues
- Freeze endpoint type mismatch: router treats `freeze_leaderboard()` result as a Snapshot, but service returns `(snapshot, already_frozen)` tuple; will raise attribute errors during runtime ([leaderboard.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/leaderboard.py#L72-L91), [leaderboard_service.py](file:///Users/vanshrana/Desktop/IEEE/backend/services/leaderboard_service.py#L114-L156)).
- Ranking key mismatch: `_compute_deterministic_ranking` sorts by `final_score`, but `_get_participant_score_data` and tests use `total_score`; deterministic behavior compromised ([leaderboard_service.py](file:///Users/vanshrana/Desktop/IEEE/backend/services/leaderboard_service.py#L545-L556), [leaderboard_service.py](file:///Users/vanshrana/Desktop/IEEE/backend/services/leaderboard_service.py#L499-L521), [test_leaderboard.py](file:///Users/vanshrana/Desktop/IEEE/backend/tests/test_leaderboard.py#L337-L370)).
- Undefined variable in score extraction: `_get_participant_score_data` references `classroom_score` which is not defined; can zero-out scores incorrectly ([leaderboard_service.py](file:///Users/vanshrana/Desktop/IEEE/backend/services/leaderboard_service.py#L502-L505)).
- Duplicate leaderboard path: legacy classroom route at `/api/classroom/sessions/{id}/leaderboard` computes ad-hoc ranking and conflicts conceptually with immutable Phase 5 endpoint ([classroom_sessions.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/classroom_sessions.py#L309-L343)).
- Repeated relationships in ClassroomSession: `arguments`, `rounds`, `round_actions`, `leaderboard_snapshots` appear twice; maintenance hazard ([classroom_session.py](file:///Users/vanshrana/Desktop/IEEE/backend/orm/classroom_session.py#L98-L107)).
- Float usage in API response: Phase 5 router converts Decimal to float for JSON; deviates from “Decimal-only” compliance stance ([leaderboard.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/leaderboard.py#L169-L177)).
- Minor RBAC helper duplication: `_is_faculty` checks the same role repeatedly; cosmetic but sloppy ([leaderboard.py](file:///Users/vanshrana/Desktop/IEEE/backend/routes/leaderboard.py#L27-L31)).

## Runtime Issues
- Freeze endpoint will error at runtime due to tuple/object mismatch (attribute access on tuple).
- Ranking may be non-deterministic or error due to key mismatch (`final_score` vs `total_score`) and test input using `evaluation_timestamp` vs code expecting `evaluation_epoch`.
- `_get_participant_score_data` undefined variable can zero scores and degrade ranking integrity.
- Integrity verification uses Decimal formatting properly; router float conversion is acceptable for client JSON but contradicts compliance goals.

## Missing Components
- Pagination and query filters for Phase 5 snapshot retrieval (page/limit, side, rank ranges).
- Caching layer for leaderboard payloads.
- Integration of faculty/admin overrides (e.g., FacultyOverride, appeals) into freeze computation and visibility rules.
- Consistent institution/visibility policy on Phase 5 snapshots (present later in Phase 5E/6, not in Phase 5 core).
- Auto-freeze on completion and governance approval workflow linkage (partial flags exist; not wired end-to-end).

## Final Verdict
- OVERALL STATUS: 60% COMPLETE
- Rationale:
  - Core snapshotting, checksum, immutability, gating, and integrity checks are implemented.
  - Critical functional mismatches (freeze endpoint return type, ranking key differences, undefined variable) break runtime behavior.
  - Operational features (pagination, filters, caching, override integration) are missing for production-grade usage.

## Exact Steps Required To Reach 100%
- Fix freeze endpoint to handle `(snapshot, already_frozen)` correctly and surface `already_frozen` flag in API.
- Align ranking keys: use a single canonical field (`final_score` or `total_score`) across `_get_participant_score_data`, ranking, and tests; remove `evaluation_timestamp` in favor of integer `evaluation_epoch`.
- Remove undefined `classroom_score` reference from `_get_participant_score_data`; rely on evaluation status checks already performed.
- Deduplicate legacy classroom leaderboard route or mark it explicitly as legacy to avoid conceptual conflicts with Phase 5 immutable snapshots.
- Clean up duplicate relationships in `ClassroomSession` to reduce confusion and potential mapper warnings.
- Add pagination and filter params to Phase 5 retrieval endpoints; include sort options and side filters.
- Optionally return Decimal as strings to align with compliance claims; or update documentation to reflect float serialization at API layer.
- Add caching for snapshot payloads (e.g., store serialized entries with checksum key).
- Integrate admin/faculty overrides into freeze computation and visibility policy; document precedence and audit trail effects.
- Update and run tests to reflect corrected keys and API behavior; ensure deterministic ranking and checksum stability pass with consistent inputs.
