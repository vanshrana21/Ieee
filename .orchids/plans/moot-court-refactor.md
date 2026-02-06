# Moot Court Module Refactor Plan

## Overview

Transform the existing "Debate Practice" feature into a comprehensive **Moot Court Workspace** for law students. This refactor renames all references from "Debate" to "Moot Court" and restructures the feature to support proper moot court preparation workflows including issue framing, IRAC argument building, and organized navigation.

---

## Requirements

**Core Problem Being Solved:**
Law students struggle with moot court preparation because they lack:
- Clear argument structure
- Guidance on framing legal issues
- A way to practice systematically
- Feedback outside classroom coaching

**Product Philosophy:**
Juris AI does NOT replace thinking. Juris AI structures thinking.

**Success Criteria:**
- A student can prepare a full moot argument without Word/Docs
- Issues are clearly framed
- Arguments are structured in IRAC format
- The product is useful even if AI is disabled

---

## Current State Analysis

### Existing Files to Refactor

| Type | Current Path | Description |
|------|--------------|-------------|
| HTML | `/html/debate.html` | Entry point, stepper UI, debate arena |
| JS | `/js/debate.js` | State management, timer logic, AI debate simulation |
| CSS | `/css/debate.css` | Styling with FOR/AGAINST colors |
| Backend | `/backend/routes/debate.py` | AI-powered moot court API (already labeled "Moot Court") |
| Reference | `/html/dashboard-student.html` | Links to debate.html |

### Current Feature Flow (to be replaced)
1. Entry screen ("Start a Debate")
2. Random topic assignment with FOR/AGAINST sides
3. 60-second preparation timer
4. Timed debate rounds against AI
5. Scoring and feedback

### Target Feature Flow (Phase 1 MVP)
1. Moot Workspace List (saved projects)
2. Create New Moot Project (name, proposition, side, court/forum)
3. Issue Framing (add/edit/reorder/delete legal issues)
4. IRAC Builder per issue (Issue, Rule, Application, Conclusion)
5. Navigation & Progress indicators

---

## Implementation Phases

### Phase 1: File Renaming & Basic Structure

**1.1 Rename Files**
- Rename `html/debate.html` to `html/moot-court.html`
- Rename `js/debate.js` to `js/moot-court.js`
- Rename `css/debate.css` to `css/moot-court.css`
- Rename `backend/routes/debate.py` to `backend/routes/moot_court.py`

**1.2 Update Import References**
- Update `backend/main.py`: Change `from backend.routes import debate` to `from backend.routes import moot_court`
- Update `backend/main.py`: Change `app.include_router(debate.router)` to `app.include_router(moot_court.router)`
- Update `html/moot-court.html`: Change CSS link from `../css/debate.css` to `../css/moot-court.css`
- Update `html/moot-court.html`: Change JS link from `../js/debate.js` to `../js/moot-court.js`

**1.3 Update Dashboard Links**
- Update `html/dashboard-student.html`: Change all `./debate.html` references to `./moot-court.html`
- Update link labels from "Debate" to "Moot Court"
- Update subtitle from "Live argument practice" to "Prepare & structure legal arguments"

---

### Phase 2: HTML Restructure (moot-court.html)

**2.1 Page Title & Meta**
- Change `<title>` from "Debate Practice | Juris AI" to "Moot Court | Juris AI"

**2.2 Navigation Updates**
- Keep navbar structure
- Update back button to return to dashboard

**2.3 Progress Steps Redesign**
- Replace current steps: Topic, Position, Preparation, Debate, Feedback
- New steps: Projects, Setup, Issues, Arguments, Review

**2.4 Entry Screen Redesign**
- Title: "Moot Court Workspace"
- Subtitle: "Structure and prepare your legal arguments like a trained advocate"
- Button: "New Moot Project"
- Secondary: Display list of saved projects (from localStorage)
- Project cards showing: name, side, court/forum, issue count, last modified

**2.5 Project Setup Screen (New)**
```html
- Moot Name input (text field)
- Proposition textarea (paste or upload moot problem)
- Side selection: Petitioner / Respondent (radio buttons)
- Court/Forum input (free text)
- Save & Continue button
```

**2.6 Issue Framing Screen (New)**
```html
- Header with moot name context
- Add Issue button
- Issue list (draggable/reorderable):
  - Issue number
  - Issue text (editable inline)
  - Completion indicator (has IRAC content?)
  - Delete button
  - Drag handle for reordering
- Continue to Arguments button
```

**2.7 IRAC Argument Builder Screen (New)**
```html
- Issue navigation sidebar (list of issues)
- Main workspace with:
  - Current issue title
  - Four text areas:
    - Issue (pre-populated from issue list, editable)
    - Rule (placeholder: "State the legal principle or statute...")
    - Application (placeholder: "Apply the rule to the facts of this case...")
    - Conclusion (placeholder: "State your conclusion on this issue...")
  - Save button per section
  - Navigation: Previous Issue / Next Issue
```

**2.8 Review Screen (New)**
```html
- Full overview of all issues with IRAC content
- Completion status per issue
- Edit buttons to jump back to specific issues
- Export/Copy all arguments option
```

**2.9 Remove Deprecated Screens**
- Remove: topicScreen (random topic assignment)
- Remove: prepScreen (60-second timer)
- Remove: debateScreen (timed rounds vs AI)
- Remove: feedbackScreen (scoring)

---

### Phase 3: JavaScript Refactor (moot-court.js)

**3.1 Storage Keys**
```javascript
const STORAGE_KEY = 'juris_moot_projects';
```

**3.2 Data Model**
```javascript
// Moot Project Structure
{
  id: string,
  name: string,
  proposition: string,
  side: 'petitioner' | 'respondent',
  courtForum: string,
  issues: [
    {
      id: string,
      order: number,
      text: string,
      irac: {
        issue: string,
        rule: string,
        application: string,
        conclusion: string
      }
    }
  ],
  createdAt: string,
  updatedAt: string
}
```

**3.3 State Management**
```javascript
const state = {
  projects: [],           // All saved moot projects
  currentProject: null,   // Active project being edited
  currentIssueIndex: 0,   // Which issue is being edited
  currentStep: 1          // Projects, Setup, Issues, Arguments, Review
};
```

**3.4 Core Functions to Implement**
```javascript
// Storage
loadProjects()           // Load from localStorage
saveProjects()           // Persist to localStorage
deleteProject(id)        // Remove project

// Project CRUD
createNewProject()       // Initialize new project
openProject(id)          // Load existing project
saveProjectSetup()       // Save name, proposition, side, court

// Issue Management
addIssue()               // Add new issue to current project
updateIssue(id, text)    // Edit issue text
deleteIssue(id)          // Remove issue
reorderIssues(newOrder)  // Drag-drop reorder

// IRAC Management
saveIRAC(issueId, field, value)  // Auto-save IRAC fields
getIssueCompletionStatus(issue)  // Check if all IRAC fields filled

// Navigation
showScreen(screenId)     // Screen transitions
updateProgressSteps(step)
navigateToIssue(index)   // Jump to specific issue in IRAC builder
```

**3.5 Remove Deprecated Code**
- Remove: TOPICS array (random topics)
- Remove: AI_RESPONSES object
- Remove: FEEDBACK_DATA object
- Remove: Timer logic (prepTimerId, debateTimerId)
- Remove: Debate round logic
- Remove: AI response generation
- Remove: Scoring logic

**3.6 Event Handlers**
```javascript
// Project list
document.getElementById('newProjectBtn').onclick = createNewProject;
// Setup form
document.getElementById('saveSetupBtn').onclick = saveProjectSetup;
// Issue management
document.getElementById('addIssueBtn').onclick = addIssue;
// IRAC auto-save on blur for each textarea
// Drag-drop for issue reordering (use HTML5 drag API)
```

---

### Phase 4: CSS Updates (moot-court.css)

**4.1 Variable Updates**
- Keep existing color scheme (professional, academic)
- Rename semantic classes: `.for` -> `.petitioner`, `.against` -> `.respondent`

**4.2 New Component Styles**

```css
/* Project List */
.project-list { }
.project-card { }
.project-card:hover { }
.project-meta { }

/* Setup Form */
.setup-form { }
.form-group { }
.side-selector { }
.side-option { }
.side-option.active { }

/* Issue Framing */
.issues-list { }
.issue-item { }
.issue-item.dragging { }
.issue-number { }
.issue-text { }
.issue-status { }
.drag-handle { }

/* IRAC Builder */
.irac-workspace { }
.issue-nav-sidebar { }
.issue-nav-item { }
.issue-nav-item.active { }
.issue-nav-item.complete { }
.irac-editor { }
.irac-section { }
.irac-label { }
.irac-textarea { }
.irac-hint { }

/* Review Screen */
.review-container { }
.review-issue { }
.review-irac { }
```

**4.3 Remove Deprecated Styles**
- Remove: `.debate-arena`
- Remove: `.speaker-column`
- Remove: `.argument-bubble`
- Remove: `.debate-timer`
- Remove: `.score-display`
- Remove: `.feedback-card`

---

### Phase 5: Backend Route Updates (moot_court.py)

**5.1 API Prefix Update**
```python
router = APIRouter(prefix="/api/moot-court", tags=["Moot Court"])
```

**5.2 Keep Existing Endpoints** (for future AI features)
- Keep `POST /api/moot-court` - Can be repurposed for AI assistance
- Keep `GET /api/moot-court/judge-verdict` - Future use

**5.3 Update Documentation**
- Update docstrings to reflect moot court terminology
- Keep petitioner/respondent terminology (already correct)

**Note:** Phase 1 MVP does NOT use backend AI heavily. The backend routes are preserved for future phases but the frontend will work with localStorage only.

---

### Phase 6: Integration Testing Checklist

**6.1 Navigation**
- [ ] Dashboard link goes to moot-court.html
- [ ] Back button returns to dashboard
- [ ] All internal navigation works

**6.2 Project Management**
- [ ] Can create new project
- [ ] Can view project list
- [ ] Can open existing project
- [ ] Can delete project
- [ ] Projects persist in localStorage

**6.3 Issue Framing**
- [ ] Can add issues
- [ ] Can edit issue text inline
- [ ] Can delete issues
- [ ] Can reorder issues via drag-drop
- [ ] Issue completion indicators update correctly

**6.4 IRAC Builder**
- [ ] Can navigate between issues
- [ ] All four IRAC fields are editable
- [ ] Content auto-saves on blur
- [ ] Placeholder hints are visible
- [ ] Previous/Next navigation works

**6.5 Review**
- [ ] All issues and IRAC content displayed
- [ ] Can jump back to edit specific issues
- [ ] Export/copy functionality works

---

## Files to Modify Summary

| File | Action | Priority |
|------|--------|----------|
| `html/debate.html` | Rename to `moot-court.html`, complete rewrite | High |
| `js/debate.js` | Rename to `moot-court.js`, complete rewrite | High |
| `css/debate.css` | Rename to `moot-court.css`, update styles | High |
| `backend/routes/debate.py` | Rename to `moot_court.py`, update prefix | Medium |
| `backend/main.py` | Update import and router registration | Medium |
| `html/dashboard-student.html` | Update link references and labels | Medium |

---

## Design Principles to Follow

1. **Clarity over beauty** - Clean, readable UI
2. **Structure over animation** - Minimal transitions, focus on content
3. **Usability over novelty** - Standard patterns, no surprises
4. **User control** - No auto-writing, user edits everything
5. **Academic tone** - Professional language, no casual copy
6. **Persistence** - All work saves to localStorage automatically

---

## What NOT to Build (Phase 1 Exclusions)

- No case law auto-summarization
- No citation generation
- No scoring systems
- No "AI writes your argument" features
- No judge simulation
- No voice or speech features
- No backend database changes
- No heavy AI integration

---

## Estimated Complexity

| Component | Effort | Notes |
|-----------|--------|-------|
| HTML restructure | Medium | 5 new screens, remove 4 old |
| JS rewrite | High | New data model, CRUD operations, drag-drop |
| CSS updates | Low | Mostly renaming + new components |
| Backend updates | Low | Rename only |
| Integration | Medium | Dashboard links, testing |

---

## Post-Implementation Verification

After implementation, verify:
1. Student can create a moot project from scratch
2. Student can add and organize legal issues
3. Student can fill out IRAC for each issue
4. All content persists across browser sessions
5. Navigation between screens is intuitive
6. UI feels professional and academic
7. Feature works completely offline (no backend dependency)
