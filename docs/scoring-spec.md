# Phase 3: Judge Scoring Interface Specification

## Overview
This document outlines the implementation of the judge scoring interface for virtual courtroom oral rounds, including the 5-criteria rubric, draft/submit workflow, and score persistence.

---

## 📦 Components Overview

| Component | Path | Purpose | Lines |
|-----------|------|---------|-------|
| **Scoring Criteria** | `backend/schemas/scoring_criteria.py` | 5-criteria rubric Pydantic models | ✅ |
| **Scoring API** | `backend/routes/oral_round_scoring.py` | 3 scoring REST endpoints | ✅ |
| **Scoring Panel** | `html/judge-scoring-panel.html` | Embedded judge scoring UI | ✅ |
| **Scoring Controller** | `js/judge-scoring-controller.js` | Frontend scoring workflow logic | ✅ 395 lines |
| **Scoring Styles** | `css/scoring-panel.css` | Judge-only panel styling | ✅ 524 lines |

---

## 📊 5-Criteria Scoring Rubric

### Score Criteria (1-5 Scale Each)

| Criterion | Key | Description |
|-----------|-----|-------------|
| **Legal Reasoning** | `legal_reasoning` | Quality of legal arguments and precedent application |
| **Citation Format** | `citation_format` | Proper SCC citation format (AIR, SCR, SCC) |
| **Courtroom Etiquette** | `courtroom_etiquette` | Professional conduct ('My Lord'/'Your Lordship') |
| **Responsiveness** | `responsiveness` | Answers to judge questions and rebuttals |
| **Time Management** | `time_management` | Effective use of allocated time |

### Score Scale Definitions

| Score | Legal Reasoning | Citation Format | Etiquette | Responsiveness | Time Management |
|-------|-----------------|-----------------|-----------|----------------|-----------------|
| **1** | Poor analysis, fundamental errors | Consistent errors (>10) | Consistent violations | Refuses to answer | Consistent overruns |
| **2** | Weak analysis, significant gaps | Frequent errors (6-10) | Frequent lapses | Poor responsiveness | Frequent overruns |
| **3** | Adequate, some logical flaws | Several errors (3-5) | Several lapses | Adequate, some evasion | Several overruns |
| **4** | Strong, minor gaps | Minor errors (1-2) | Minor lapses | Good, minor delays | Minor overruns |
| **5** | Exceptional, clear precedent | Perfect throughout | Perfect etiquette | Excellent | Perfect |

### Total Score Calculation
```
Total Score = Average of 5 criteria (1.0 - 5.0)
Percentage = (Total Score / 5.0) × 100
Max Possible = 25 (5 criteria × 5 max)
```

---

## 🌐 API Endpoints

### 1. Create/Update Score
```http
POST /api/oral-rounds/{round_id}/scores
Authorization: Bearer {token}
Content-Type: application/json

{
  "team_id": 1,
  "team_side": "petitioner",
  "legal_reasoning": 4,
  "citation_format": 5,
  "courtroom_etiquette": 5,
  "responsiveness": 3,
  "time_management": 4,
  "written_feedback": "Strong Puttaswamy analysis...",
  "strengths": ["SCC citation perfect", "Legal reasoning clear"],
  "areas_for_improvement": ["Need proportionality test"],
  "is_draft": false
}
```

**Response:**
```json
{
  "id": 1,
  "round_id": 1,
  "judge_id": 2,
  "team_id": 1,
  "team_side": "petitioner",
  "legal_reasoning": 4,
  "citation_format": 5,
  "courtroom_etiquette": 5,
  "responsiveness": 3,
  "time_management": 4,
  "total_score": 4.2,
  "written_feedback": "Strong Puttaswamy analysis...",
  "strengths": ["SCC citation perfect", "Legal reasoning clear"],
  "areas_for_improvement": ["Need proportionality test"],
  "is_draft": false,
  "is_submitted": true,
  "submitted_at": "2026-02-11T14:30:00Z"
}
```

**Validation:**
- All 5 criteria required (1-5 scale)
- `team_id` must belong to round
- `team_side` must match `team_id`
- `written_feedback` max 1000 chars
- `strengths` max 5 items
- `areas_for_improvement` max 5 items
- Only judges can create scores

---

### 2. Get Scores
```http
GET /api/oral-rounds/{round_id}/scores?include_drafts=true
Authorization: Bearer {token}
```

**Role-Based Response:**
- **Judges:** See ALL scores (drafts + submitted)
- **Team Members:** See ONLY submitted scores for their team

**Response:**
```json
[
  {
    "id": 1,
    "team_id": 1,
    "team_side": "petitioner",
    "legal_reasoning": 4,
    "citation_format": 5,
    "courtroom_etiquette": 5,
    "responsiveness": 3,
    "time_management": 4,
    "total_score": 4.2,
    "is_draft": false,
    "is_submitted": true,
    "submitted_at": "2026-02-11T14:30:00Z"
  }
]
```

---

### 3. Submit Draft Score
```http
POST /api/oral-rounds/{round_id}/scores/{score_id}/submit
Authorization: Bearer {token}
```

**Permissions:**
- Only the judge who created the score can submit it
- Returns 403 if non-creator attempts submit

**Response:**
```json
{
  "message": "Score submitted successfully",
  "score_id": 1,
  "total_score": 4.2,
  "submitted_at": "2026-02-11T14:30:00Z"
}
```

---

## 🖥️ UI Components

### Judge Scoring Panel (`html/judge-scoring-panel.html`)

**Structure:**
```html
<div class="scoring-panel" id="judge-scoring-panel">
  <!-- Header with close button -->
  <!-- Team selection dropdown -->
  <!-- 5 criteria sliders with descriptions -->
  <!-- Total score preview with progress bar -->
  <!-- Written feedback textarea -->
  <!-- Strengths checkboxes (max 5) -->
  <!-- Improvements checkboxes (max 5) -->
  <!-- Save Draft / Submit Score buttons -->
  <!-- Status messages -->
</div>
```

**Features:**
- Floating panel (fixed position, top-right)
- Draggable header for repositioning
- Real-time total score calculation
- Score value color coding (red/yellow/green)
- Character counter for feedback (1000 max)
- Checkbox limits (5 max each)
- Draft indicator badge

---

## 🎨 CSS Specifications (`css/scoring-panel.css`)

### Panel Layout
```css
.scoring-panel {
    position: fixed;
    top: 20px;
    right: 20px;
    width: 380px;
    max-height: 90vh;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border: 2px solid #e94560;
    border-radius: 16px;
    padding: 20px;
    box-shadow: 0 10px 40px rgba(233, 69, 96, 0.3);
    z-index: 1000;
}
```

### Color Scheme
- **Panel Background:** Dark gradient (#1a1a2e → #16213e)
- **Border Accent:** #e94560 (coral red)
- **Score Low (1-2):** #F44336 (red)
- **Score Medium (3):** #FFC107 (amber)
- **Score High (4-5):** #4CAF50 (green)
- **Total Bar Gradient:** Red → Yellow → Green
- **Draft Badge:** #FFC107 (amber)
- **Submitted Badge:** #4CAF50 (green)

### Team Button Colors
- **Petitioner:** Gradient #667eea → #764ba2 (purple)
- **Respondent:** Gradient #f093fb → #f5576c (pink/red)

---

## 🔧 JavaScript Controller (`js/judge-scoring-controller.js`)

### Class: `JudgeScoringController`

**Constructor:**
```javascript
const controller = new JudgeScoringController(roundId, {
    apiBaseUrl: '/api',
    onScoreSaved: (score) => console.log('Saved:', score),
    onScoreSubmitted: (score) => console.log('Submitted:', score)
});
controller.initialize();
```

**Key Methods:**

| Method | Description |
|--------|-------------|
| `initialize()` | Setup event listeners and load existing scores |
| `handleSliderChange(key, value)` | Update score value and preview |
| `handleTeamChange(side)` | Switch team for scoring |
| `handleCheckboxChange(category, checkbox)` | Manage strengths/improvements |
| `updatePreview()` | Recalculate and display total score |
| `calculateTotal()` | Average of 5 criteria |
| `saveScore(asDraft)` | POST to API (draft or submit) |
| `submitScore()` | Finalize draft score |
| `loadExistingScores()` | GET scores from API |
| `togglePanel()` | Show/hide scoring panel |

**State Management:**
```javascript
{
  currentTeamId: number|null,
  currentTeamSide: string|null,
  scoreId: number|null,
  scores: {
    legalReasoning: 3,
    citationFormat: 3,
    courtroomEtiquette: 3,
    responsiveness: 3,
    timeManagement: 3
  },
  writtenFeedback: '',
  strengths: [],
  areasForImprovement: [],
  isDraft: true
}
```

---

## 🔄 Draft vs Submit Workflow

### Draft Workflow
1. Judge selects team
2. Adjusts 5 criteria sliders
3. Adds optional feedback/strengths/improvements
4. Clicks "Save Draft"
5. Score saved with `is_draft=true`, `is_submitted=false`
6. **Teams CANNOT see draft scores**

### Submit Workflow
1. Judge has saved draft
2. Clicks "Submit Score"
3. Confirmation dialog appears
4. On confirm: `is_draft=false`, `is_submitted=true`
5. `submitted_at` timestamp set
6. WebSocket broadcasts `score_update` event
7. **Teams CAN see submitted scores**

---

## ✅ Verification Checklist

- [x] Judge sees scoring panel in courtroom (role-based visibility)
- [x] 5 sliders update total score instantly (e.g., "Total: 4.2/5.0")
- [x] "Save Draft" persists score with `is_draft=true`
- [x] "Submit Score" finalizes with `is_submitted=true`
- [x] Teams see submitted scores (API filters drafts)
- [x] Non-judge attempting to score → 403 Forbidden
- [x] Total score calculated correctly (average, not sum)
- [x] Written feedback max 1000 chars enforced
- [x] Strengths/Improvements limited to 5 items each
- [x] WebSocket broadcast on score submission
- [x] Phase 0-2 infrastructure unchanged

---

## 🚀 Usage Example

```javascript
// Initialize controller
const scoringController = new JudgeScoringController(1);
scoringController.initialize();

// Programmatic team selection
scoringController.selectTeam('petitioner');

// Set scores programmatically
scoringController.scores.legalReasoning = 5;
scoringController.scores.citationFormat = 4;
scoringController.updatePreview();

// Save draft
scoringController.saveScore(true);

// Submit final score
scoringController.submitScore();

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    scoringController.cleanup();
});
```

---

## 🎯 Success Criteria

1. **Panel Visibility:** Judge opens courtroom → scoring panel visible (judge role only)
2. **Slider Updates:** Move any slider → total score updates instantly
3. **Draft Save:** Click "Save Draft" → success message, draft badge appears
4. **Score Submit:** Click "Submit Score" → confirmation, broadcast to all
5. **Team View:** Team member logs in → sees only submitted scores
6. **Permission Denied:** Student attempts API call → 403 Forbidden

---

## 📋 Integration with Phases 0-2

### Phase 0 Components (Unchanged)
- `OralRoundScore` ORM model (already has all fields)
- `CourtroomState` - Scores added to state tree
- `CourtroomAuth` - Role validation (judge check)
- `WebSocketManager` - Broadcast score updates

### Phase 1 Components (Unchanged)
- `oral-courtroom.html` - Scoring panel embedded
- `courtroom.css` - No modifications (isolated scoring-panel.css)
- `CourtroomUI` - Scoring controller instantiated

### Phase 2 Components (Unchanged)
- `CourtroomTimer` - No changes
- `CourtroomRuling` - No changes
- `TranscriptRecorder` - No changes
- Timer, objection, transcript all work independently

---

## 🔐 Security & Permissions

| Action | Required Role | Validation |
|--------|---------------|------------|
| Create Score | `JUDGE` | `require_judge_role()` middleware |
| Update Score | `JUDGE` (creator only) | `score.judge_id == current_user.id` |
| Submit Score | `JUDGE` (creator only) | Same as above |
| View Drafts | `JUDGE` | Role check in GET handler |
| View Submitted | Any participant | Filter by `is_submitted=true` + team_id |

---

## 📚 File Dependencies

```
Backend:
├── schemas/scoring_criteria.py → Pydantic models
├── routes/oral_round_scoring.py → API endpoints
└── orm/oral_round_score.py → Database model (Phase 0)

Frontend:
├── html/judge-scoring-panel.html → UI structure
├── js/judge-scoring-controller.js → Business logic
└── css/scoring-panel.css → Styling

Integration:
└── courtroom-ui.js → Instantiates controller (judge only)
```

---

## 🎓 Scoring Tips for Judges

1. **Legal Reasoning:** Look for proper application of precedent (Puttaswamy, Maneka Gandhi)
2. **Citation Format:** Check SCC format accuracy (e.g., "(2020) 10 SCC 1")
3. **Etiquette:** "My Lord" for single judge, "Your Lordships" for bench
4. **Responsiveness:** Do they answer the question or evade?
5. **Time Management:** Watch for overruns in memorials and arguments

---

*Document Version: Phase 3.0*
*Last Updated: February 2026*
