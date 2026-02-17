### Phase 4 — Competitive Match Engine

**Schema created**
- Extended existing `matches` table with:
  - `state`, `player_1_score`, `player_2_score`
  - `player_1_legal_reasoning`, `player_2_legal_reasoning`
  - `is_ai_match`, `is_locked`, `finalized_at`
  - Check constraint `ck_matches_scores_before_finalize`
- Added `match_rounds` table with:
  - `(match_id, player_id, round_number)` unique constraint
  - `is_submitted`, `is_locked`, `final_score`, `submitted_at`
  - Check constraint enforcing `round_number` in \[1, 3\]

**Match lifecycle defined**
- States: `queued` → `matched` → `in_progress` → `completed` → `finalized`
- Matches are created via `MatchmakingService.request_ranked_match` and locked at the end of scoring (`is_locked = True`, `finalized_at` set).

**Round enforcement working**
- Each match pre-allocates 3 rounds per player when both players are known.
- Submission flow:
  - `POST /api/match/{match_id}/round/{round_number}/submit` records `argument_text`.
  - Deterministic AI scorer sets `final_score` and immediately locks the round.
  - Cannot submit round 2 or 3 until all players’ previous rounds are locked.
  - Cannot edit or delete rounds once `is_locked` is `True` (ORM-level guards).

**Tie-break deterministic**
- Match scores computed from finalized rounds only:
  - Opening (R1)  → 40%
  - Rebuttal (R2) → 40%
  - Closing (R3)  → 20%
- Winner selection:
  - Higher `player_*_score` wins.
  - If still tied, deterministic fallback to lower `user_id`.
  - Legal reasoning aggregates tracked on `player_*_legal_reasoning` for future tie-break refinements.

**Rating pairing implemented**
- Uses `PlayerRating.current_rating` with fixed ±100 window.
- Excludes users already in active matches (`state` in `queued|matched|in_progress|completed` and `is_locked = False`).
- Implemented in `MatchmakingService.request_ranked_match`.

**AI fallback implemented**
- Status endpoint `GET /api/match/{id}/status`:
  - If match has been `queued` for ≥ 10 seconds without opponent, converts to `is_ai_match = True` and `state = "in_progress"`.
  - Player completes the same 3-round flow; AI scoring uses deterministic pseudo-AI scorer.
  - AI fallback matches do not update ratings in Phase 4.

**Lock enforcement confirmed**
- ORM-level guards:
  - `Match`: `before_update` / `before_delete` prevent mutation when `is_locked = True`.
  - `MatchRound`: `before_update` / `before_delete` prevent mutation when `is_locked = True`.
- All scoring reads from `final_score` only; non-finalized rounds are excluded from aggregation.

**Final status**

MATCH ENGINE STRUCTURALLY COMPLETE

---

### SAFETY HARDENING PATCH

**Checklist**
- AI fallback is **server-driven**:
  - Background worker started at match creation converts queued matches to `is_ai_match = True` and `state = "in_progress"` after the timeout.
  - Status endpoint no longer controls fallback or mutates match state.
- Strict validation before match finalization:
  - Finalization only occurs when the full expected set of `MatchRound` rows exists for the match.
  - All rounds must be `is_submitted = True`, `is_locked = True`, and `final_score` is not `NULL`.
  - Attempts to finalize with incomplete rounds raise a clear backend error.
- AI matches are excluded from rating logic:
  - Rating service stub `process_rating_update_for_match` short-circuits when `match.is_ai_match` or `match.state != "finalized"`.
  - Guards ensure future rating updates cannot accidentally process AI matches or non-finalized matches.
- Match lock enforced at ORM level:
  - `before_update` / `before_delete` listeners on `Match` and `MatchRound` prevent any mutation once `is_locked = True`.
- No premature finalization possible:
  - Backend will not transition a match to `state = "finalized"` unless strict round completeness checks pass.

**OVERALL_STATUS:** STRUCTURALLY SAFE

