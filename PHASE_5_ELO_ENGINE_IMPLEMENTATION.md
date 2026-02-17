### Phase 5 — Official ELO Engine Implementation

**Models added / updated**
- `PlayerRating` (in `backend/orm/player_ratings.py`):
  - Existing ELO model reused with fields: `current_rating`, `matches_played`, `wins`, `losses`, `draws`.
  - Added `last_match_id` to track the last processed match per player.
- `RatingHistory` (in `backend/orm/player_ratings.py`):
  - Tracks immutable rating changes per match.
  - Added uniqueness constraint `uq_rating_history_user_match` on `(user_id, match_id)` to prevent duplicate history entries.
- `Match` (in `backend/orm/online_match.py`):
  - Added `rating_processed: Boolean = False` to enforce exactly-once rating updates per match.

**Service created**
- `backend/services/elo_rating_service.py`:
  - Class `EloRatingService` with `async def process_rating_update_for_match(match_id: int, db: AsyncSession)`.
  - Implements chess-style ELO updates using:
    - Expected score: `Ea = 1 / (1 + 10 ** ((Rb - Ra) / 400))`.
    - K-factor:
      - `< 30` games → `K = 40`
      - `< 100` games → `K = 20`
      - `>= 100` games → `K = 10`
    - Update formula: `new_rating = old_rating + K * (actual - expected)` with integer rounding.
    - Zero-sum guarantee: `delta2 = -delta1`, so gains/losses balance exactly.
  - Creates two `RatingHistory` rows (one per player) for every processed match.

**Finalization hook location**
- Hooked into `backend/services/matchmaking_service.py`, inside `MatchmakingService.submit_round`:
  - After:
    - All `MatchRound` rows for the match are validated as `is_submitted=True`, `is_locked=True`, and `final_score` not `NULL`.
    - Aggregate scores are computed and `match.winner_id` is set.
    - `match.state` is set to `"finalized"` and `match.is_locked = True`.
  - Then:
    - `await EloRatingService.process_rating_update_for_match(match.id, db)` is called **before** the final `db.commit()`, ensuring rating updates and match finalization are part of the same transaction.

**Validation logic**
- Inside `EloRatingService.process_rating_update_for_match`:
  - Loads and locks the `Match` row with `SELECT ... FOR UPDATE`.
  - Guards:
    - If `match.is_ai_match` → returns immediately (no rating update, no history, `rating_processed` remains `False`).
    - Requires:
      - `match.state == "finalized"`
      - `match.is_locked is True`
      - `match.rating_processed is False`
      - `match.winner_id` is not `NULL`
      - `match.player1_id` and `match.player2_id` are not `NULL`
    - Violations raise `ValueError`, causing the surrounding transaction to fail.
  - Player ratings:
    - Fetches `PlayerRating` rows for both players with `SELECT ... FOR UPDATE`.
    - Creates default rows (`current_rating = 1000`, `peak_rating = 1000`) if missing.
  - Result classification:
    - If `player_1_score == player_2_score` → both players get `actual = 0.5` (draw).
    - Else `actual = 1/0` based on `match.winner_id`.
  - ELO math:
    - Computes expected scores `E1`, `E2`.
    - Applies K-factors based on `matches_played`.
    - Calculates raw deltas, rounds new rating for player 1, and sets player 2’s delta to `-delta1` for strict zero-sum.
  - Stats updates:
    - Increments `matches_played`, `wins`, `losses`, `draws` appropriately.
    - Updates `last_active_at` and `last_match_id` for both players.
  - History:
    - Inserts two `RatingHistory` rows with `(old_rating, new_rating, rating_change, opponent_rating, result)` for each player.
  - Deduplication:
    - Sets `match.rating_processed = True` to prevent any subsequent rating run for the same match.

**Test results (conceptual)**
- **Test 1: 1000 vs 1000, Player 1 wins**
  - `K = 40` for both (new players).
  - Expected score ≈ 0.5 each.
  - `delta1 ≈ +20`, `delta2 ≈ -20` after rounding.
  - `rating_processed` set to `True`; second invocation raises `ValueError`.
- **Test 2: 1000 vs 1200, underdog wins**
  - Underdog’s expected score is lower, so positive delta magnitude is larger for the underdog.
  - Zero-sum enforced via `delta2 = -delta1`.
- **Test 3: Draw**
  - `actual = 0.5` for both players.
  - Higher-rated player loses points; lower-rated player gains points.
- **Test 4: AI match**
  - `match.is_ai_match == True` → method returns early.
  - No `PlayerRating` changes, no `RatingHistory` rows, `rating_processed` remains `False`.
- **Test 5: Double execution attempt**
  - First call sets `match.rating_processed = True`.
  - Second call raises `ValueError("Rating already processed for this match")`.
- **Test 6: Non-finalized match**
  - Any call where `match.state != "finalized"` or `match.is_locked is False` raises `ValueError` and prevents rating updates.

**Example rating calculation**
- Starting ratings: `P1 = 1000`, `P2 = 1000`, `matches_played = 0`.
- Player 1 wins:
  - Expected scores: `E1 = 0.5`, `E2 = 0.5`.
  - `K = 40` for both.
  - `delta1_raw = 40 * (1.0 - 0.5) = +20`, `new_R1 = 1020`.
  - Zero-sum: `delta2 = -20`, `new_R2 = 980`.
  - History:
    - P1: `1000 → 1020`, `+20`.
    - P2: `1000 → 980`, `-20`.

**Duplicate prevention confirmation**
- `Match.rating_processed` is set to `True` atomically within the same transaction that:
  - Finalizes the match,
  - Updates both `PlayerRating` rows,
  - Inserts two `RatingHistory` rows.
- Combined with the unique constraint on `(user_id, match_id)` in `RatingHistory`, this ensures:
  - No duplicate rating writes per player/match pair.
  - Any attempt to re-run rating updates for the same match fails early before mutating state.

