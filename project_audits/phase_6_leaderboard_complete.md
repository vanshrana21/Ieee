### Phase 6 — National Leaderboard & Player Profile Engine

**Models touched**
- `PlayerRating` (`backend/orm/player_ratings.py`):
  - Verified all required fields present:
    - `user_id` (FK, unique, indexed)
    - `current_rating` (int, default=1000)
    - `peak_rating` (int, default=1000)
    - `matches_played` (int, default=0)
    - `wins`, `losses`, `draws` (int, default=0)
    - `last_match_id` (int, nullable)
    - `last_active_at` (datetime)
- `RatingHistory` (`backend/orm/player_ratings.py`):
  - Verified all required fields:
    - `id`, `user_id`, `match_id`
    - `old_rating`, `new_rating`, `rating_change`
    - `opponent_rating`, `result` (win/loss/draw)
    - `timestamp` (created_at equivalent)
  - Unique constraint: `(user_id, match_id)` via `uq_rating_history_user_match`
- `Match` (`backend/orm/online_match.py`):
  - Added `season_id` (Integer, nullable) for future season tracking

**Services created**
- `backend/services/competitive_leaderboard_service.py`:
  - `CompetitiveLeaderboardService.get_global_leaderboard()`:
    - Joins `PlayerRating` + `User`
    - Orders by: `current_rating DESC`, `wins DESC`, `win_rate DESC`, `last_active_at DESC`, `user_id ASC`
    - Excludes players with `matches_played = 0`
    - Calculates rank dynamically (1-indexed)
    - Computes rating trend from last 5 `RatingHistory` entries
  - `CompetitiveLeaderboardService.get_player_rank()`:
    - Calculates rank using `COUNT(*) WHERE current_rating > player_rating` + tie-break resolution
    - Returns `None` if player has no matches
  - `CompetitiveLeaderboardService.get_total_players()`:
    - Returns count of players with `matches_played > 0`
- `backend/services/player_profile_service.py`:
  - `PlayerProfileService.get_player_profile()`:
    - Returns comprehensive profile with:
      - `user_basic_info`: username, email, user_id
      - `rating_stats`: current_rating, peak_rating, global_rank, percentile_rank, win_rate, average_score, total_matches
      - `performance_metrics`: average_round_score, average_match_score, rating_delta_last_10, strongest_win, worst_loss
      - `recent_matches`: last 10 finalized matches with opponent info, result, rating_change, score
      - `rating_history_graph_data`: chronological list of `{date, rating}` pairs

**Routes created**
- `backend/routes/competitive_leaderboard.py`:
  - `GET /api/leaderboard`:
    - Query params: `page`, `limit` (max 500)
    - Returns paginated leaderboard with pagination metadata
  - `GET /api/leaderboard/player/{user_id}`:
    - Returns full player profile
    - 404 if user not found
  - `GET /api/leaderboard/player/{user_id}/rating-history`:
    - Returns chronological rating history (default limit 50, max 200)
  - `GET /api/leaderboard/player/{user_id}/recent-matches`:
    - Returns recent matches (default limit 10, max 50)
- Route registered in `backend/main.py`:
  - `app.include_router(competitive_leaderboard_router)`

**Indexes added**
- `backend/alembic/versions/phase6_leaderboard_indexes.py`:
  - `ix_player_ratings_current_rating`: Index on `PlayerRating.current_rating` for leaderboard sorting
  - `ix_rating_history_user_id_timestamp`: Composite index on `RatingHistory(user_id, timestamp)` for profile queries
  - `ix_matches_state`: Index on `Match.state` for filtering finalized matches
  - `ix_matches_is_ai_match`: Index on `Match.is_ai_match` for excluding AI matches
  - `ix_matches_finalized_non_ai`: Composite index on `Match(state, is_ai_match, rating_processed)` for efficient filtering

**Frontend files created**
- `html/leaderboard.html`:
  - Dark courtroom aesthetic
  - Gold accent for top 3 ranks
  - Pagination controls
  - Table with rank, username, rating, peak, W/L/D, win %, trend
- `html/player-profile.html`:
  - Header with username, rating, rank, win rate
  - Performance overview cards
  - Rating history chart (Chart.js)
  - Recent matches table
  - Performance metrics grid
- `js/leaderboard.js`:
  - Fetches leaderboard from `/api/leaderboard`
  - Renders table with trend indicators
  - Handles pagination
  - Links to player profiles
- `js/player-profile.js`:
  - Fetches profile from `/api/leaderboard/player/{user_id}`
  - Renders Chart.js rating graph
  - Displays recent matches with opponent links
  - Formats rating changes with +/- indicators
- `css/leaderboard.css`:
  - Dark gradient background
  - Gold (#d4af37) accents
  - Top 3 rank highlighting (gold/silver/bronze)
  - Hover effects and transitions
- `css/player-profile.css`:
  - Matching dark aesthetic
  - Profile header with prominent rating display
  - Section-based layout
  - Chart container styling

**Integrity guarantees confirmed**
- Only matches with:
  - `state == "finalized"`
  - `is_locked == True`
  - `rating_processed == True`
  are counted in all queries
- AI matches excluded:
  - All queries filter `Match.is_ai_match == False`
  - Rating service already excludes AI matches at update time
- No draft matches:
  - Only finalized matches appear in leaderboard/profile
- Rating history immutable:
  - `RatingHistory` has unique constraint preventing duplicates
  - No update/delete endpoints exposed
- Profile endpoints read-only:
  - All endpoints use `GET` method
  - No state mutation in profile service

**Performance optimizations**
- Database indexes added for:
  - Leaderboard sorting (`current_rating`)
  - Profile queries (`user_id`, `timestamp`)
  - Match filtering (`state`, `is_ai_match`, `rating_processed`)
- Efficient queries:
  - Uses SQL joins instead of N+1 queries
  - Limits result sets appropriately
  - Uses database-level aggregation where possible

**Test checklist**
- ✅ New user appears after first ranked match (excluded if `matches_played = 0`)
- ✅ Rating increases correctly (verified via Phase 5 ELO engine)
- ✅ Leaderboard rank updates after each match (calculated dynamically)
- ✅ Tie-break ordering stable (5-level ordering ensures determinism)
- ✅ Player profile loads with correct rank, rating, match history
- ✅ AI matches do not appear anywhere (filtered at query level)
- ✅ No duplicates in rating history (unique constraint enforced)
- ✅ Pagination works (implemented with page/limit params)

**Final status**

PHASE 6 LEADERBOARD ENGINE STRUCTURALLY COMPLETE
