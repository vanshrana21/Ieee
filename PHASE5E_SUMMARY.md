# Juris AI - Phase 5E Implementation Summary

## Ranking, Leaderboards, and Winner Selection

### Overview
Phase 5E implements automated rank computation from judge scores, tie-break rule application, leaderboard generation, and official winner selection. This phase completes the competition evaluation lifecycle.

---

## Core Entities

### TeamRanking (Computed Rank)
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `institution_id` | Integer | Institution scoping (Phase 5B) |
| `competition_id` | Integer | Competition scoping |
| `round_id` | Integer | Round scoping (optional) |
| `team_id` | Integer | Team being ranked |
| `ranking_type` | Enum | memorial / oral / overall / round |
| `rank` | Integer | Position (1 = first place) |
| `rank_display` | String | "1st", "2nd", "3rd", etc. |
| `total_score` | Float | Aggregated score |
| `normalized_score` | Float | 0-100 scale |

### Criterion Averages (Phase 5E)
| Field | Description |
|-------|-------------|
| `issue_framing_avg` | Average score across judges |
| `legal_reasoning_avg` | Average score across judges |
| `use_of_authority_avg` | Average score across judges |
| `structure_clarity_avg` | Average score across judges |
| `oral_advocacy_avg` | Average score across judges |
| `responsiveness_avg` | Average score across judges |

### Tie-Break Information (Phase 5E)
| Field | Description |
|-------|-------------|
| `is_tied` | Boolean - tied with other teams |
| `tied_with_team_ids` | List of team IDs tied with |
| `tie_break_reason` | Explanation of tie resolution |
| `tie_break_applied` | Which rule was used |

### Winner Designation
| Field | Description |
|-------|-------------|
| `medal` | gold / silver / bronze / None |
| `is_winner` | Competition winner |
| `is_runner_up` | Second place |
| `is_semifinalist` | Third place |

---

## Ranking Computation Workflow

### 1. Aggregate Judge Scores
```python
# Collect all published, finalized scores for each team
for team in teams:
    scores = get_published_judge_scores(team.id)
    
    # Calculate averages per criterion
    aggregate = {
        "issue_framing_avg": mean([s.issue_framing_score for s in scores]),
        "legal_reasoning_avg": mean([s.legal_reasoning_score for s in scores]),
        ...
        "total_score": mean([s.total_score for s in scores]),
        "normalized_score": (avg_total / 60) * 100  # 60 = max possible
    }
```

### 2. Sort by Score
```python
# Sort teams by normalized score (descending)
teams.sort(key=lambda x: x["normalized_score"], reverse=True)
```

### 3. Apply Tie-Break Rules
```python
# Detect ties (teams with equal scores)
for score, tied_teams in score_groups.items():
    if len(tied_teams) > 1:
        # Apply tie-break rules in order
        for rule in tie_break_rules:
            # Compare teams on specific criterion
            winner = team_with_higher(rule.criterion)
```

### 4. Assign Ranks
```python
# Assign sequential ranks
# Handle ties: teams with same score share rank
# Next rank skips appropriately (e.g., 1, 2, 2, 4)
```

---

## Tie-Break Rules (Phase 5E)

### Default Tie-Break Order
1. **Legal Reasoning** - Higher legal reasoning score wins
2. **Issue Framing** - Higher issue framing score wins
3. **Use of Authority** - Higher use of authority score wins
4. **Structure & Clarity** - Higher structure score wins
5. **Oral Advocacy** - Higher oral advocacy score wins
6. **Responsiveness** - Higher responsiveness score wins

### Custom Tie-Break Rules
```python
POST /api/rankings/tie-break-rules
{
    "rule_name": "higher_research",
    "criterion": "use_of_authority",
    "comparison": "higher",
    "rule_order": 1
}
```

### Tie Resolution
```python
if teams tied:
    for rule in rules:
        winners = teams_with_best_score(rule.criterion)
        if len(winners) == 1:
            # Tie broken!
            winner.tie_break_applied = rule.rule_name
            break
        else:
            # Still tied, try next rule
            continue
```

---

## API Endpoints

### Ranking Computation
| Endpoint | Method | Access | Description |
|----------|--------|--------|-------------|
| `/api/rankings/compute` | POST | Faculty/Admin | Compute rankings from scores |
| `/api/rankings` | GET | All (scoped) | List rankings |
| `/api/rankings/{id}` | GET | All | Get ranking details |
| `/api/rankings/publish` | POST | Admin | Publish rankings |

### Leaderboard
| Endpoint | Method | Access | Description |
|----------|--------|--------|-------------|
| `/api/rankings/leaderboard/generate` | POST | Faculty/Admin | Generate leaderboard |
| `/api/rankings/leaderboard/view` | GET | All | View public leaderboard |
| `/api/rankings/leaderboard/{id}/publish` | POST | Admin | Publish leaderboard |

### Tie-Break Configuration
| Endpoint | Method | Access | Description |
|----------|--------|--------|-------------|
| `/api/rankings/tie-break-rules` | POST | Admin | Create tie-break rule |
| `/api/rankings/tie-break-rules` | GET | All | List tie-break rules |

### Winner Selection
| Endpoint | Method | Access | Description |
|----------|--------|--------|-------------|
| `/api/rankings/winners/select` | POST | Admin | Select official winners |
| `/api/rankings/winners` | GET | All | List winners |

---

## Leaderboard Features

### View Options
```python
class Leaderboard:
    show_scores: bool      # Show numeric scores?
    show_medals: bool      # Show medal icons?
    entries: JSON          # Cached ranking entries
```

### Entry Format
```json
{
    "rank": 1,
    "rank_display": "1st",
    "team_id": 123,
    "total_score": 58.5,
    "normalized_score": 97.5,
    "medal": "gold",
    "is_tied": false
}
```

---

## Winner Selection (Phase 5E)

### Automatic Winner Selection
```python
# Select top 3 from published rankings
winners = []
for i, ranking in enumerate(top_3_rankings):
    winner = WinnerSelection(
        team_id=ranking.team_id,
        rank=ranking.rank,
        title=["Winner", "Runner-up", "Third Place"][i],
        medal=["gold", "silver", "bronze"][i],
        selection_method="ranking",
        is_official=True
    )
    winners.append(winner)
```

### Winner Categories
- **Winner** (1st place) - Gold medal
- **Runner-up** (2nd place) - Silver medal
- **Third Place** (3rd place) - Bronze medal
- **Semi-finalist** - Recognition

---

## Files Created

### Models
| File | Description |
|------|-------------|
| `/backend/orm/ranking.py` | TeamRanking, Leaderboard, WinnerSelection, TieBreakRule |

### Services
| File | Description |
|------|-------------|
| `/backend/services/ranking_service.py` | RankingService with computation, tie-breaking, leaderboard generation |

### Routes
| File | Description |
|------|-------------|
| `/backend/routes/rankings.py` | Ranking CRUD, leaderboard, winner selection |
| `/backend/main.py` | Registered ranking routes |

---

## STOP - Phase 5E Complete

**Phase 5E is complete.** Do not implement advanced analytics, historical tracking, or cross-competition comparisons (Phase 5F+) unless explicitly requested.

The ranking system is now:
- ✅ Automated rank computation from judge scores
- ✅ Per-criterion aggregation
- ✅ Tie-break rule system
- ✅ Configurable tie-break priority
- ✅ Leaderboard generation
- ✅ Public/private leaderboard control
- ✅ Official winner selection
- ✅ Medal assignment (gold/silver/bronze)
- ✅ Complete competition evaluation lifecycle

**STOP** - This phase completes the competition ranking system. ALL phases 5A-5E now work together:
- 5A: Authentication & RBAC
- 5B: Institution multi-tenancy
- 5C: Submissions & deadlines
- 5D: Judge scoring & conflict resolution
- 5E: Rankings & winner selection
