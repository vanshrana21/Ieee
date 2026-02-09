# JURIS AI — COMPLETE PROJECT AUDIT

## 1. Project Overview

**Purpose**: AI-powered learning platform for Indian law students combining solo AI practice with real moot court competitions

**Target Users**: Indian law students (BA LLB, BBA LLB, LLB), faculty members, judges, institutional administrators

**Core Value Prop**: Hybrid model offering safe AI-powered solo practice that prepares students for graded moot court competitions — zero-risk practice before real submissions

---

## 2. Architecture Diagram (Text-Based)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            JURIS AI PLATFORM                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  FRONTEND (Vanilla JS/HTML/CSS)                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  html/                                                              │   │
│  │   ├── dashboard-student.html  → Student dashboard                   │   │
│  │   ├── dashboard-lawyer.html   → Lawyer dashboard                     │   │
│  │   ├── faculty-dashboard.html → Faculty management                  │   │
│  │   ├── ai-practice.html      → Phase 3: AI Moot Practice            │   │
│  │   ├── moot-court.html       → Phase 5: Competition mode              │   │
│  │   ├── case-simplifier.html  → Case law simplification               │   │
│  │   ├── learn-content.html    → BA LLB curriculum content              │   │
│  │   ├── tutor.html            → AI Tutor interface                     │   │
│  │   └── [30+ other pages]                                             │   │
│  │                                                                     │   │
│  │  js/                                                                │   │
│  │   ├── ai-judge-interface.js → Phase 3 AI practice UI                │   │
│  │   ├── moot-court.js         → Competition workflows                  │   │
│  │   ├── auth.js               → Authentication + RBAC                  │   │
│  │   ├── dashboard-student.js  → Student dashboard logic                │   │
│  │   └── [50+ other modules]                                           │   │
│  │                                                                     │   │
│  │  css/                                                               │   │
│  │   ├── ai-practice.css       → Phase 3 styles + behavior badges       │   │
│  │   ├── dashboard.css         → Dashboard layouts                       │   │
│  │   └── [40+ stylesheets]                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  API LAYER (FastAPI)                                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  /api/auth/*                → Login, signup, tokens                  │   │
│  │  /api/users/*             → User management                          │   │
│  │  /api/ai-moot/*           → Phase 3: AI Practice (solo)             │   │
│  │  /api/moot-court/*        → Phase 5: Competitions (teams)           │   │
│  │  /api/ba-llb/*            → Phase 0: Curriculum content              │   │
│  │  /api/search/*            → Case law search                          │   │
│  │  /api/tutor/*             → AI Tutor endpoints                       │   │
│  │  /api/competitions/*      → Competition management                   │   │
│  │  /api/teams/*             → Team management                          │   │
│  │  /api/judge/*             → Judging workflows                        │   │
│  │  /api/analytics/*         → Progress tracking                        │   │
│  │  /api/submissions/*       → Moot submissions                         │   │
│  │  [70+ additional routes]                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  BUSINESS LOGIC (Services)                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  ai_judge_service.py       → Phase 3+4: AI judge + India behaviors   │   │
│  │  india_behavior_rules.py   → Phase 4: 5 India courtroom norms        │   │
│  │  llm_client.py            → Groq/DeepSeek/Gemini integration        │   │
│  │  ai_tutor.py              → AI Tutor engine                        │   │
│  │  case_summarizer.py       → Case law simplification                  │   │
│  │  ranking_service.py       → Leaderboards & benchmarking              │   │
│  │  study_planner_service.py → Personalized study plans                 │   │
│  │  [60+ additional services]                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ORM MODELS (SQLAlchemy)                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  user.py                  → Users with roles + institution           │   │
│  │  ai_oral_session.py       → Phase 2/3: Solo AI practice sessions     │   │
│  │  moot_project.py          → Phase 5: Competition projects            │   │
│  │  competition.py           → Competition definitions                  │   │
│  │  team.py                  → Team management                            │   │
│  │  submission.py            → Moot submissions                         │   │
│  │  judge_evaluation.py      → Judging rubrics & scores                 │   │
│  │  ba_llb_curriculum.py     → Phase 0: Curriculum structure            │   │
│  │  [50+ additional models]                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  KNOWLEDGE BASE                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  knowledge_base/india.py  → Phase 1: 15 landmark cases, SCC format   │   │
│  │  knowledge_base/problems.py → 3 validation moot problems             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  DATABASE (SQLite + Async)                                                  │
│  ├─ legalai.db              → Main application database                  │
│  └─ data/                   → Seed data & migrations                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Complete Directory Structure

### Root Level
| File/Directory | Purpose |
|----------------|---------|
| `backend/` | FastAPI application (logic, models, routes) |
| `html/` | Frontend HTML pages (38 pages) |
| `js/` | Frontend JavaScript logic (54 modules) |
| `css/` | Stylesheets (43 stylesheets) |
| `knowledge_base/` | India legal knowledge base |
| `data/` | Seed data and reference materials |
| `assets/` | Images, icons, static assets |
| `uploads/` | User uploaded files |
| `legalai.db` | SQLite database file |
| `.env` | Environment configuration |

### Backend Structure
| Directory | Purpose | Key Files |
|-----------|---------|-----------|
| `backend/routes/` | 70+ API route handlers | `auth.py`, `ai_moot.py`, `competitions.py`, `ba_llb.py`, `teams.py`, `judge.py` |
| `backend/orm/` | 50+ SQLAlchemy models | `user.py`, `ai_oral_session.py`, `moot_project.py`, `competition.py`, `team.py` |
| `backend/services/` | 60+ business logic services | `ai_judge_service.py`, `india_behavior_rules.py`, `llm_client.py`, `ai_tutor.py` |
| `backend/schemas/` | Pydantic validation schemas | Request/response models for all endpoints |
| `backend/seed/` | Database seeding scripts | `seed_data.py` |
| `backend/ai/` | AI-specific utilities | Context management, governance |
| `backend/knowledge_base/` | Legal knowledge data | `india.py`, `problems.py` |
| `backend/logging/` | Log configuration | Structured logging setup |

### Frontend Structure
| Directory | Purpose | Key Files |
|-----------|---------|-----------|
| `html/` | 38 HTML pages | `dashboard-student.html`, `ai-practice.html`, `moot-court.html`, `case-simplifier.html` |
| `js/` | 54 JavaScript modules | `auth.js`, `ai-judge-interface.js`, `moot-court.js`, `dashboard-student.js` |
| `css/` | 43 stylesheets | `ai-practice.css`, `dashboard.css`, `sidebar.css` |

---

## 4. Core Features Mapping

### 4.1 BA LLB Curriculum (Phase 0) — COMPLETE
**Purpose**: 5-year law curriculum with 10 semesters, subjects, and modules

| Aspect | Details |
|--------|---------|
| **Entry Point** | `dashboard-student.html` → "Subjects" → `curriculum.html` |
| **Backend Routes** | `/api/ba-llb/semesters`, `/api/ba-llb/semesters/{n}/subjects` |
| **Frontend Files** | `curriculum.html`, `learn-content.html`, `js/curriculum.js` |
| **ORM Models** | `ba_llb_curriculum.py` (BALLBSemester, BALLBSubject, BALLBModule) |
| **Key Features** | • 10-semester structure<br>• Subject modules with content<br>• Progress tracking per module |

**User Flow**:
```
Dashboard → Subjects → Select Semester → Select Subject → View Modules → Read Content
```

### 4.2 AI Practice Mode (Phase 2-4) — COMPLETE
**Purpose**: Solo practice with AI judge enforcing Indian courtroom norms

| Aspect | Details |
|--------|---------|
| **Entry Point** | `dashboard-student.html` → "AI Practice" → `ai-practice.html` |
| **Backend Routes** | `/api/ai-moot/problems`, `/api/ai-moot/sessions`, `/api/ai-moot/turns` |
| **Frontend Files** | `ai-practice.html`, `js/ai-judge-interface.js`, `css/ai-practice.css` |
| **Service Layer** | `ai_judge_service.py`, `india_behavior_rules.py`, `llm_client.py` |
| **ORM Models** | `ai_oral_session.py` (AIOralSession, AIOralTurn) |

**User Flow**:
```
Dashboard → AI Practice → Select Problem → Choose Side (Petitioner/Respondent)
    ↓
Turn 1: Submit Opening Argument → Get AI Feedback (My Lord check, SCC citation check)
    ↓
Turn 2: Submit Rebuttal → Get Feedback (interruption if >60 words)
    ↓
Turn 3: Submit Sur-rebuttal → Final Feedback → Debrief
```

**India-Specific Elements**:
- ✅ "My Lord" etiquette enforcement (progressive deductions: 0/2/3 points)
- ✅ SCC citation policing: `(2017) 10 SCC 1` format required
- ✅ Judicial interruptions after 60 words
- ✅ Landmark case nudges: Puttaswamy, Swamy, Modi, Sibbia
- ✅ Proportionality test for constitutional law problems

### 4.3 Moot Court Competition Mode (Phase 5) — COMPLETE
**Purpose**: Real graded competitions with teams, submissions, and judging

| Aspect | Details |
|--------|---------|
| **Entry Point** | `dashboard-student.html` → "Moot Court" → `moot-court.html` |
| **Backend Routes** | `/api/competitions`, `/api/teams`, `/api/submissions`, `/api/judge/evaluations` |
| **Frontend Files** | `moot-court.html`, `js/moot-court.js` |
| **Service Layer** | `judge_evaluation.py`, `scoring.py`, `rubric_engine.py` |
| **ORM Models** | `competition.py`, `team.py`, `submission.py`, `judge_evaluation.py` |

**User Flow (Student)**:
```
Dashboard → Moot Court → View Competitions → Join/Create Team
    ↓
Team Workspace → Write Memorial (IRAC format) → Submit Draft
    ↓
Oral Rounds → Present Arguments → Get Judge Feedback
    ↓
Results → View Scores → See Rankings
```

**User Flow (Judge)**:
```
Dashboard → Moot Court → Judge Panel → View Assigned Teams
    ↓
Evaluate Memorials (rubric scoring) → Provide Written Feedback
    ↓
Oral Round Judging → Score Presentation + Q&A
    ↓
Submit Evaluations → Finalize Results
```

### 4.4 Case Simplifier — COMPLETE
**Purpose**: Simplify complex Indian case law for students

| Aspect | Details |
|--------|---------|
| **Entry Point** | `dashboard-student.html` → "Case Simplifier" → `case-simplifier.html` |
| **Backend Routes** | `/api/case-simplifier` |
| **Frontend Files** | `case-simplifier.html`, `js/case-simplifier.js` |
| **Service Layer** | `case_summarizer.py` |

**Features**:
- AI-powered case summarization
- Headnotes generation
- Key holdings extraction
- Statute references mapping

### 4.5 AI Tutor — COMPLETE
**Purpose**: Context-aware legal tutoring

| Aspect | Details |
|--------|---------|
| **Entry Point** | `dashboard-student.html` → "AI Tutor" → `tutor.html` |
| **Backend Routes** | `/api/tutor`, `/api/tutor/chat` |
| **Frontend Files** | `tutor.html`, `tutor-chat.html`, `js/tutor-chat.js` |
| **Service Layer** | `ai_tutor.py`, `tutor_engine.py`, `context_aware_tutor.py` |

### 4.6 Analytics & Dashboard — COMPLETE
| Aspect | Details |
|--------|---------|
| **Entry Point** | `dashboard-student.html`, `benchmark.html` |
| **Backend Routes** | `/api/analytics`, `/api/benchmark` |
| **Frontend Files** | `js/dashboard-student.js`, `js/benchmark.js` |
| **Service Layer** | `analytics.py`, `ranking_service.py`, `progress_calculator.py` |

**Features**:
- Progress tracking across curriculum
- Benchmarking against cohort
- Subject mastery visualization
- Study plan recommendations

---

## 5. Hybrid Model Architecture

### 5.1 AI Practice vs Competition: Key Differences

| Feature | AI Practice Mode | Competition Mode |
|---------|------------------|------------------|
| **Purpose** | Solo zero-risk practice | Real graded evaluation |
| **Entry** | Individual | Team-based |
| **Judging** | AI (LLM) | Human judges |
| **Feedback** | Instant, detailed | Delayed (post-round) |
| **Database** | `AIOralSession` | `MootProject` + `Submission` |
| **Scoring** | 3 categories (accuracy/citation/etiquette) | Full rubric (10+ criteria) |
| **Problems** | 3 validation problems (KB) | Custom per competition |
| **Turns** | 3 rounds (opening/rebuttal/sur-rebuttal) | Competition-defined rounds |

### 5.2 Shared Infrastructure

| Component | Shared? | Notes |
|-----------|---------|-------|
| **User authentication** | ✅ Yes | Same JWT tokens, same user table |
| **Problem definitions** | ⚠️ Partial | AI practice uses KB problems; competitions use custom |
| **Team management** | ❌ No | Competition only |
| **Case law search** | ✅ Yes | Same Indian case law database |
| **Scoring logic** | ⚠️ Partial | AI uses simplified 3-category; competitions use full rubric |
| **Activity logging** | ✅ Yes | `TeamActivityLog` tracks both modes |

### 5.3 Data Flow Architecture

```
Student Dashboard
    ├── AI Practice Mode (Solo)
    │   └── Creates: AIOralSession → AIOralTurn
    │   └── Uses: knowledge_base/india.py
    │   └── AI Judge: LLM + IndiaBehaviorRules
    │   └── No team required
    │
    └── Moot Court Competition (Team)
        └── Creates: Team → MootProject → Submission
        └── Uses: Competition-specific problems
        └── Human Judges: Faculty/External
        └── Requires team formation
```

**Critical**: AI Practice sessions do NOT convert to competition submissions. They are completely separate flows with separate database tables. Students must re-create submissions for competitions.

---

## 6. India-Specific Legal Features

### 6.1 Phase 1: Knowledge Base (COMPLETE)
**File**: `knowledge_base/india.py`

| Feature | Implementation |
|---------|----------------|
| **15 Landmark Cases** | Puttaswamy, Navtej Singh, Vishaka, M.C. Mehta, etc. |
| **SCC Citation Format** | Pattern: `(YYYY) VOL SCC PAGE` — e.g., `(2017) 10 SCC 1` |
| **Statute Mappings** | IPC sections, CrPC sections, Constitutional articles |
| **Case Validation** | Regex for SCC, AIR, SCR formats |
| **Domain Detection** | Constitutional, Criminal, Civil, IPR law categorization |

### 6.2 Phase 2: AI Oral Sessions (COMPLETE)
**Files**: `backend/orm/ai_oral_session.py`

- Solo practice session tracking
- Turn-by-turn argument storage
- AI feedback persistence

### 6.3 Phase 3: LLM Integration (COMPLETE)
**Files**: `backend/services/llm_client.py`, `backend/services/ai_judge_service.py`

| Feature | Implementation |
|---------|----------------|
| **LLM Providers** | Groq, DeepSeek, Gemini, OpenRouter (fallback chain) |
| **Prompt Engineering** | Justice Chandrachud persona |
| **Response Limits** | 80 words max (judicial brevity) |
| **Knowledge Base Integration** | Case lookup before LLM call |

### 6.4 Phase 4: India Behavior Rules (COMPLETE)
**File**: `backend/services/india_behavior_rules.py`

| Behavior | Enforcement | UI Badge |
|----------|-------------|----------|
| **My Lord Etiquette** | First 15 chars check; 0/2/3 pt deductions by turn | ✅/❌ My Lord (green/red) |
| **SCC Citation** | Regex policing vs "Puttaswamy case" informal refs | ✅/❌ SCC Format (blue/red) |
| **Judicial Interruption** | Triggers at >60 words | ⚡ Interrupted (pulsing orange) |
| **Landmark Case Nudges** | KB-triggered: suggests Puttaswamy for privacy, Swamy for defamation | ✅/❌ CaseName (amber/red) |
| **Proportionality Test** | Privacy/free speech problems require 4-prong analysis | ✅/❌ Proportionality (purple/red) |

### 6.5 Competition Judging Rubrics (COMPLETE)
**File**: `backend/orm/judge_evaluation.py`

- Indian legal English scoring
- SCC citation format in rubric
- Landmark case citation requirements
- Proportionality test evaluation (constitutional problems)

### 6.6 Missing India-Specific Features

| Feature | Status | Gap Analysis |
|---------|--------|--------------|
| **AIR Citation Support** | ⚠️ Partial | Only SCC validated; AIR format not enforced |
| **Indian Legal Databases** | ⚠️ Partial | Uses local KB; no live IndianKanoon/SC Indra integration |
| **Regional Language Support** | ❌ Missing | English only; no Hindi/other Indian language support |
| **Court-Specific Rules** | ❌ Missing | No High Court vs Supreme Court etiquette differentiation |
| **State-Specific Laws** | ❌ Missing | Only central Indian law; no state amendments tracking |
| **Recent Judgments** | ❌ Missing | Static KB; no auto-update from recent Supreme Court judgments |

---

## 7. Authentication & User Flows

### 7.1 Auth System Architecture

| Component | Details |
|-----------|---------|
| **Protocol** | JWT (JSON Web Tokens) |
| **Token Storage** | localStorage (access_token, refresh_token) |
| **Password Hashing** | bcrypt |
| **Token Expiry** | Access: 30 minutes, Refresh: 7 days |
| **Role-Based Access** | 5 roles: STUDENT, JUDGE, FACULTY, ADMIN, SUPER_ADMIN |

### 7.2 Auth Endpoints

| Endpoint | Purpose | Frontend Usage |
|----------|---------|----------------|
| `POST /api/auth/login` | Authenticate, receive tokens | `login.html` → `js/auth.js` |
| `POST /api/auth/register` | Create new account | `signup.html` → `js/auth.js` |
| `POST /api/auth/refresh` | Refresh access token | Automatic in `js/auth.js` |
| `POST /api/auth/logout` | Invalidate tokens | Logout button → `js/auth.js` |

### 7.3 Role Hierarchy & Permissions

```
SUPER_ADMIN (5)
  └── Full system access
      
ADMIN (4)
  └── Institution management
      └── Competition creation
          └── All faculty permissions
              
FACULTY (3)
  └── Student management
      └── Judging
          └── Team oversight
              
JUDGE (2)
  └── Evaluation only
      └── No student data access
          
STUDENT (1)
  └── Learning features
      └── AI Practice
          └── Competition participation
```

**Permission Matrix (Moot Court)**:
| Action | Roles |
|--------|-------|
| CREATE_PROJECT | STUDENT |
| EVALUATE_AND_SCORE | JUDGE, FACULTY, ADMIN, SUPER_ADMIN |
| CREATE_COMPETITIONS | ADMIN, SUPER_ADMIN |
| MANAGE_INSTITUTIONS | SUPER_ADMIN |

### 7.4 User Journey

```
1. SIGNUP
   signup.html → POST /api/auth/register → Dashboard

2. ONBOARDING
   onboarding.html → Select course (BA LLB/BBA LLB/LLB) → Select semester

3. DASHBOARD ACCESS
   dashboard-student.html → Load progress → Display subjects/AI Practice/Moot Court

4. FEATURE USAGE
   ├── AI Practice: ai-practice.html (solo, no team needed)
   ├── Moot Court: moot-court.html (team formation required)
   ├── Learning: learn-content.html (curriculum)
   └── Case Search: case-simplifier.html

5. LOGOUT
   Sidebar → Logout → Clear localStorage → Redirect to login.html
```

### 7.5 Protected Routes

All routes use `get_current_user` dependency:
```python
@router.get("/some-route")
async def protected_endpoint(
    current_user: User = Depends(get_current_user)
):
    # User authenticated
```

Role-restricted routes use `require_role`:
```python
@router.post("/create-competition")
async def create_competition(
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    # Admin only
```

---

## 8. Tech Stack & Deployment

### 8.1 Backend Stack

| Component | Technology | Version |
|-----------|------------|---------|
| **Framework** | FastAPI | Latest |
| **Python** | Python | 3.11+ |
| **Database** | SQLite (async) | 3.40+ |
| **ORM** | SQLAlchemy | 2.0+ |
| **Migrations** | Alembic | Latest |
| **Auth** | python-jose + passlib | Latest |
| **Validation** | Pydantic | v2 |

### 8.2 Frontend Stack

| Component | Technology |
|-----------|------------|
| **Framework** | Vanilla JavaScript (no framework) |
| **Styling** | Vanilla CSS (no preprocessor) |
| **Templating** | Native HTML with JS string templates |
| **Icons** | SVG inline |
| **Fonts** | Google Fonts (DM Sans, Bricolage Grotesque) |

### 8.3 AI Integration

| Provider | Usage | Fallback Priority |
|----------|-------|-------------------|
| **Groq** | Primary LLM (Llama 3, Mixtral) | 1st |
| **DeepSeek** | Secondary LLM | 2nd |
| **Gemini** | Tertiary (Google) | 3rd |
| **OpenRouter** | Final fallback | 4th |

### 8.4 Deployment

| Component | Deployment |
|-----------|------------|
| **Backend** | Uvicorn ASGI server |
| **Frontend** | Static files (no build step) |
| **Database** | SQLite file |
| **Dev Command** | `uvicorn backend.main:app --reload` |

### 8.5 Environment Variables

```bash
DATABASE_URL=sqlite+aiosqlite:///./legalai.db
JWT_SECRET_KEY=your-secret-key
GEMINI_API_KEY=your-gemini-key
GROQ_API_KEY=your-groq-key
DEEPSEEK_API_KEY=your-deepseek-key
```

---

## 9. Development Phase Status

### 9.1 Phase Completion Matrix

| Phase | Description | Status | Key Files |
|-------|-------------|--------|-----------|
| **Phase 0** | BA LLB Curriculum | ✅ COMPLETE | `ba_llb.py`, `ba_llb_curriculum.py` |
| **Phase 1** | Knowledge Base (India) | ✅ COMPLETE | `knowledge_base/india.py` |
| **Phase 2** | AI Oral Sessions | ✅ COMPLETE | `ai_oral_session.py`, `ai_moot.py` |
| **Phase 3** | AI Judge + LLM | ✅ COMPLETE | `ai_judge_service.py`, `llm_client.py` |
| **Phase 4** | India Behavior Rules | ✅ COMPLETE | `india_behavior_rules.py` |
| **Phase 5A** | RBAC + Auth | ✅ COMPLETE | `auth.py`, `rbac.py`, `user.py` |
| **Phase 5B** | Competitions | ✅ COMPLETE | `competitions.py`, `competition.py` |
| **Phase 5C** | Teams | ✅ COMPLETE | `teams.py`, `team.py` |
| **Phase 5D** | Submissions | ✅ COMPLETE | `submissions.py`, `submission.py` |
| **Phase 5E** | Judging | ✅ COMPLETE | `judge.py`, `judge_evaluation.py` |
| **Phase 6A** | Search + Bookmarks | ✅ COMPLETE | `search.py`, `bookmarks.py` |
| **Phase 6B** | Tutor | ✅ COMPLETE | `ai_tutor.py`, `tutor.py` |
| **Phase 6C** | Analytics | ✅ COMPLETE | `analytics.py`, `ranking_service.py` |
| **Phase 7** | Case Simplifier | ✅ COMPLETE | `case_simplifier.py`, `case-detail.html` |
| **Phase 8** | Study Planner | ✅ COMPLETE | `study_planner.py`, `study-planner.html` |
| **Phase 9** | Debate | ✅ COMPLETE | `debate.py`, `debate.html` |

### 9.2 Critical Blockers: NONE

All phases (0-9) are complete. The platform is feature-complete for MVP.

### 9.3 Technical Debt Areas

| Area | Issue | Severity |
|------|-------|----------|
| **Frontend Framework** | No framework (vanilla JS) makes complex UIs harder | Medium |
| **Database** | SQLite limits concurrent users | Low (MVP scale) |
| **LLM Costs** | Multiple providers for redundancy adds complexity | Low |
| **Test Coverage** | No visible test suite | Medium |

### 9.4 Enhancement Opportunities

| Feature | Priority | Effort |
|---------|----------|--------|
| **Live Case Law API** | High | Medium (IndianKanoon integration) |
| **Mobile App** | Medium | High (React Native/Flutter) |
| **Real-time Notifications** | Medium | Medium (WebSocket) |
| **Advanced Analytics** | Low | Medium |
| **Video Oral Rounds** | Low | High |

---

## 10. Key API Endpoint Reference

### 10.1 AI Practice Mode (Phase 2-4)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/ai-moot/problems` | GET | List 3 validation problems |
| `/api/ai-moot/sessions` | POST | Create AI practice session |
| `/api/ai-moot/sessions/{id}` | GET | Get session details |
| `/api/ai-moot/turns` | POST | Submit argument turn |
| `/api/ai-moot/turns/{id}` | GET | Get turn details |

### 10.2 Competition Mode (Phase 5)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/competitions` | GET/POST | List/create competitions |
| `/api/competitions/{id}` | GET | Get competition details |
| `/api/teams` | GET/POST | List/create teams |
| `/api/teams/{id}/join` | POST | Join team |
| `/api/submissions` | POST | Submit memorial |
| `/api/judge/evaluations` | POST | Submit evaluation |

### 10.3 Curriculum (Phase 0)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/ba-llb/semesters` | GET | All semesters |
| `/api/ba-llb/semesters/{n}/subjects` | GET | Subjects per semester |
| `/api/ba-llb/subjects/{id}/modules` | GET | Modules per subject |

### 10.4 Case Law

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/search` | GET | Case law search |
| `/api/case-simplifier` | POST | Simplify case |
| `/api/bookmarks` | GET/POST | Saved cases |

---

## 11. Summary & Future Development Guidance

### 11.1 Project Maturity

**Status**: Production-ready MVP
- ✅ All 10 phases complete (0-9)
- ✅ Core learning loop functional
- ✅ AI Practice + Competition hybrid model working
- ✅ India-specific legal features implemented
- ✅ RBAC with 5 roles operational

### 11.2 Safe Development Zones

| Safe to Modify | Caution Areas |
|----------------|---------------|
| `backend/services/india_behavior_rules.py` | `backend/orm/` (schema stability) |
| `js/ai-judge-interface.js` | `backend/routes/auth.py` (security) |
| `css/ai-practice.css` | `backend/rbac.py` (permissions) |
| New API routes | Existing competition scoring logic |
| Frontend UI enhancements | Database migrations |

### 11.3 Adding New India-Specific Behaviors

To add a new courtroom behavior (e.g., "standing up when judge enters"):

1. **Modify** `backend/services/india_behavior_rules.py`
2. **Add** check method to `IndiaBehaviorRules` class
3. **Update** `enforce_india_behaviors()` to include new check
4. **Modify** `backend/services/ai_judge_service.py` to use new check
5. **Add** badge rendering in `js/ai-judge-interface.js`
6. **Add** styles in `css/ai-practice.css`

### 11.4 Database Schema Stability

**Never modify without migration**:
- `backend/orm/user.py` (authentication)
- `backend/orm/competition.py` (competition integrity)
- `backend/orm/team.py` (team assignments)
- `backend/orm/judge_evaluation.py` (scoring records)

**Safe to extend**:
- Add columns to `backend/orm/ai_oral_session.py`
- Create new tables for features

---

**Audit Date**: February 8, 2026  
**Auditor**: Cascade AI Assistant  
**Project**: Juris AI — Indian Legal Education Platform
