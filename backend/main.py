import os
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from backend.routes import case_simplifier,progress, subjects, dashboard
from backend.routes import auth, user, curriculum, modules, content, progress
from backend.routes.practice import router as practice_router
from backend.routes import search
from backend.routes import bookmarks, saved_searches
from backend.routes import semantic_search
from backend.routes import tutor
from backend.routes import practice
from backend.routes import study_plan
from backend.routes import analytics
from backend.routes import study
from backend.routes import tutor_session
from backend.routes import evaluation
from backend.routes import tutor_chat
from backend.routes import diagnostics
from backend.routes import study_planner
from backend.routes import exam_blueprint
from backend.routes import mock_exam
from backend.routes import exam_evaluation
from backend.routes import exam_readiness
from backend.routes import benchmark
from backend.routes import ai_context
from backend.routes import feedback
from backend.routes import adaptive
from backend.routes import memory
from backend.routes import student
from backend.routes import ba_llb
from backend.routes import test_kanoon
from backend.routes import debug_super_kanoon
from backend.routes import debate
from backend.routes import classroom
from backend.routes.classroom import router as classroom_router


# ============================================
# CRITICAL: Load .env FIRST, before any backend imports
# ============================================
from dotenv import load_dotenv

# Get absolute path to project root (IEEE/)
# This file is at IEEE/backend/main.py, so go up one level
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Load environment variables from absolute path (override=True ensures .env takes precedence)
load_dotenv(dotenv_path=ENV_FILE, override=True)

# Log which env file was loaded
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info(f"✓ Loaded environment from: {ENV_FILE}")
logger.info(f"✓ GEMINI_API_KEY present: {bool(os.getenv('GEMINI_API_KEY'))}")
logger.info(f"✓ GROQ_API_KEY present: {bool(os.getenv('GROQ_API_KEY'))}")

# Verify critical env vars are loaded
if not os.getenv("GEMINI_API_KEY"):
    logger.error(f"❌ GEMINI_API_KEY not found. Checked: {ENV_FILE}")
    logger.error(f"   File exists: {ENV_FILE.exists()}")
    logger.error("   Solution: cp .env.example .env && nano .env")
    sys.exit(1)

if not os.getenv("GROQ_API_KEY"):
    logger.warning("⚠️ GROQ_API_KEY not found - some features may be limited")

# Now safe to import backend modules
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from backend.routes import rag_search
from backend.routes import notes

from backend.database import init_db, close_db, seed_moot_cases, AsyncSessionLocal
from backend.routes import router
from backend.routes import search
from backend.errors import ErrorCode, APIError, log_and_raise_internal, get_error_summary

# ============================================
# Rate Limiter Configuration
# ============================================
limiter = Limiter(key_func=get_remote_address)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

REQUIRED_ENV_VARS = ["DATABASE_URL", "JWT_SECRET_KEY", "GEMINI_API_KEY"]
missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
if missing_vars:
    logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application...")
    logger.info(f"Loaded .env from: {ENV_FILE}")
    logger.info(f"GEMINI_API_KEY present: {bool(os.getenv('GEMINI_API_KEY'))}")
    try:
        await init_db()
        logger.info("Database connected successfully")
        
        # Seed default moot cases
        async with AsyncSessionLocal() as session:
            await seed_moot_cases(session)
            
            # PHASE: Seed structured High Court cases
            from backend.services.case_library_service import seed_high_court_cases
            inserted = await seed_high_court_cases(session)
            logger.info(f"✓ High Court case library: {inserted} cases seeded")
    except Exception as e:
        logger.error(f"Failed to connect to database: {str(e)}")
        raise
    
    yield
    
    logger.info("Shutting down application...")
    try:
        await close_db()
        logger.info("Database connection closed")
    except Exception as e:
        logger.error(f"Error closing database connection: {str(e)}")

app = FastAPI(
    title="LegalAI Research API",
    description="AI-powered legal research platform backend",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENVIRONMENT", "development") == "development" else None,
    redoc_url="/redoc" if os.getenv("ENVIRONMENT", "development") == "development" else None,
    lifespan=lifespan
)

# Attach rate limiter to the app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
logger.info("✓ Rate limiter configured")

origins = [
    "http://localhost:3000",
    "http://localhost:5500",
    "http://localhost:8000",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5500",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8080",
]

allowed_origins = os.getenv("ALLOWED_ORIGINS", "").split(",")
if allowed_origins and allowed_origins[0]:
    origins.extend(allowed_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error on {request.url.path}: {exc.errors()}")
    
    error_details = []
    for error in exc.errors():
        error_dict = {
            "loc": error.get("loc"),
            "msg": error.get("msg"),
            "type": error.get("type")
        }
        error_details.append(error_dict)
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": "Validation Error",
            "details": error_details
        }
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(f"HTTP exception on {request.url.path}: {exc.detail}")
    
    if isinstance(exc.detail, dict):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail
        )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": "Error",
            "message": str(exc.detail),
            "code": ErrorCode.INTERNAL_ERROR if exc.status_code >= 500 else ErrorCode.INVALID_INPUT
        }
    )


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    logger.warning(f"API error on {request.url.path}: {exc.code} - {exc.message}")
    return exc.to_response()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import uuid
    log_id = str(uuid.uuid4())[:8]
    logger.error(f"[{log_id}] Unhandled exception on {request.url.path}: {type(exc).__name__}: {str(exc)}")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "Internal Error",
            "message": "An unexpected error occurred. Please try again later.",
            "code": ErrorCode.INTERNAL_ERROR,
            "details": {"log_id": log_id}
        }
    )

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "version": "1.0.0"
    }


@app.get("/api/errors/health", tags=["Health"])
async def error_handling_health():
    return get_error_summary()

@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "LegalAI Research API",
        "version": "1.0.0",
        "docs": "/docs" if os.getenv("ENVIRONMENT", "development") == "development" else None
    }

app.include_router(case_simplifier.router)
app.include_router(router, prefix="/api")
app.include_router(subjects.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(user.router, prefix="/api")
app.include_router(curriculum.router, prefix="/api")
app.include_router(modules.router, prefix="/api")
app.include_router(content.router, prefix="/api")
app.include_router(progress.router, prefix="/api")
app.include_router(practice_router, prefix="/api")
app.include_router(search.router)
app.include_router(bookmarks.router)
app.include_router(saved_searches.router)
app.include_router(notes.router)
app.include_router(semantic_search.router)
app.include_router(tutor.router)
app.include_router(practice.router)
app.include_router(study_plan.router)
app.include_router(analytics.router, prefix="/api")
app.include_router(study.router)
app.include_router(tutor_session.router)
app.include_router(evaluation.router, prefix="/api")
app.include_router(evaluation.questions_router, prefix="/api")
app.include_router(tutor_chat.router)
app.include_router(diagnostics.router)
app.include_router(study_planner.router)
app.include_router(exam_blueprint.router)
app.include_router(mock_exam.router)
app.include_router(exam_evaluation.router)
app.include_router(exam_readiness.router)
app.include_router(benchmark.router)
app.include_router(ai_context.router)
app.include_router(feedback.router)
app.include_router(adaptive.router)
app.include_router(memory.router)
app.include_router(student.router, prefix="/api")
app.include_router(ba_llb.router, prefix="/api")
app.include_router(test_kanoon.router)
app.include_router(debug_super_kanoon.router)
app.include_router(debate.router)

# Phase 5B: Institution and Competition routes (Multi-tenancy)
from backend.routes import institutions, competitions
app.include_router(institutions.router, prefix="/api")
app.include_router(competitions.router, prefix="/api")

# Phase 5C: Submissions and Oral Round Slots
from backend.routes import submissions, slots
app.include_router(submissions.router, prefix="/api")
app.include_router(slots.router, prefix="/api")

# Phase 5C: Moot Project Persistence (Replaces localStorage)
from backend.routes import moot_projects, moot_evaluations
app.include_router(moot_projects.router, prefix="/api")
#app.include_router(oral_rounds.router, prefix="/api")
app.include_router(moot_evaluations.router, prefix="/api")

# Phase 5D: Competition Workflow, Deadlines & Submission Locking
from backend.routes import competition_workflow
app.include_router(competition_workflow.router, prefix="/api")

# Phase 5D: Scoring and Conflict Resolution
from backend.routes import scoring
app.include_router(scoring.router, prefix="/api")

# Phase 5E: Rankings and Leaderboards
from backend.routes import rankings
app.include_router(rankings.router, prefix="/api")

# Phase 6A: Team Structure & Membership
from backend.routes import teams
app.include_router(teams.router, prefix="/api")

# Phase 7: Faculty Oversight & Academic Monitoring
from backend.routes import faculty
app.include_router(faculty.router, prefix="/api")

# Phase 8: AI Governance, Safety & Explainability Layer
from backend.routes import ai_governance
app.include_router(ai_governance.router, prefix="/api")

# Phase 9: Judging, Evaluation & Competition Scoring
from backend.routes import judge, evaluation_admin, results
app.include_router(judge.router, prefix="/api")
app.include_router(evaluation_admin.router, prefix="/api")
app.include_router(results.router, prefix="/api")

# Phase 2 MVP: AI Moot Court Practice Mode
from backend.routes.ai_moot import ai_moot_router
app.include_router(ai_moot_router, prefix="/api")

# Phase 7: Classroom Mode (Moot Court Classroom Sessions)
app.include_router(classroom_router)

# Phase 3: Round Engine (conditionally enabled)
from backend.config.feature_flags import feature_flags
if feature_flags.FEATURE_CLASSROOM_ROUND_ENGINE:
    from backend.routes.classroom_rounds import router as round_engine_router
    app.include_router(round_engine_router)
    logger.info("✅ Phase 3 Round Engine enabled")
else:
    logger.info("⏸️ Phase 3 Round Engine disabled (set FEATURE_CLASSROOM_ROUND_ENGINE=True to enable)")

# Phase 4: AI Judge Evaluation Engine (conditionally enabled)
if feature_flags.FEATURE_AI_JUDGE_EVALUATION:
    from backend.routes.ai_judge import router as ai_judge_router
    app.include_router(ai_judge_router)
    logger.info("✅ Phase 4 AI Judge Evaluation enabled")
else:
    logger.info("⏸️ Phase 4 AI Judge Evaluation disabled (set FEATURE_AI_JUDGE_EVALUATION=True to enable)")

# Phase 5: Leaderboard Engine (conditionally enabled)
if feature_flags.FEATURE_LEADERBOARD_ENGINE:
    from backend.routes.leaderboard import router as leaderboard_router
    app.include_router(leaderboard_router)
    logger.info("✅ Phase 5 Leaderboard Engine enabled")
else:
    logger.info("⏸️ Phase 5 Leaderboard Engine disabled (set FEATURE_LEADERBOARD_ENGINE=True to enable)")

# Phase 14: Deterministic Round Engine (conditionally enabled)
if feature_flags.FEATURE_CLASSROOM_ROUND_ENGINE:
    from backend.routes.phase14_round_engine import router as phase14_router
    app.include_router(phase14_router)
    logger.info("✅ Phase 14 Deterministic Round Engine enabled")
    
    # Run crash recovery on startup
    from backend.services.phase14_crash_recovery import startup_recovery
    import asyncio
    try:
        recovery_result = asyncio.get_event_loop().run_until_complete(startup_recovery())
        if recovery_result.get("recovered", 0) > 0:
            logger.warning(f"🔧 Crash recovery: Restored {recovery_result['recovered']} LIVE matches")
    except Exception as e:
        logger.error(f"Crash recovery failed: {e}")
else:
    logger.info("⏸️ Phase 14 Deterministic Round Engine disabled (set FEATURE_CLASSROOM_ROUND_ENGINE=True to enable)")

# Phase 15: AI Judge Intelligence Layer (conditionally enabled)
if feature_flags.FEATURE_AI_JUDGE_OFFICIAL or feature_flags.FEATURE_AI_JUDGE_SHADOW:
    from backend.routes.phase15_ai_judge import router as phase15_router
    app.include_router(phase15_router)
    logger.info("✅ Phase 15 AI Judge Intelligence Layer enabled")
    if feature_flags.FEATURE_AI_JUDGE_OFFICIAL:
        logger.info("  └─ Official evaluation: enabled")
    if feature_flags.FEATURE_AI_JUDGE_SHADOW:
        logger.info("  └─ Shadow scoring: enabled")
else:
    logger.info("⏸️ Phase 15 AI Judge Intelligence Layer disabled (set FEATURE_AI_JUDGE_OFFICIAL=True or FEATURE_AI_JUDGE_SHADOW=True to enable)")

# Phase 16: Performance Analytics & Ranking Intelligence Layer (conditionally enabled)
if (feature_flags.FEATURE_ANALYTICS_ENGINE or 
    feature_flags.FEATURE_RANKING_ENGINE or 
    feature_flags.FEATURE_JUDGE_ANALYTICS or 
    feature_flags.FEATURE_TREND_ENGINE):
    from backend.routes.phase16_analytics import router as phase16_router
    app.include_router(phase16_router)
    logger.info("✅ Phase 16 Performance Analytics & Ranking Intelligence Layer enabled")
    if feature_flags.FEATURE_ANALYTICS_ENGINE:
        logger.info("  └─ Analytics engine: enabled")
    if feature_flags.FEATURE_RANKING_ENGINE:
        logger.info("  └─ Ranking engine: enabled")
    if feature_flags.FEATURE_JUDGE_ANALYTICS:
        logger.info("  └─ Judge analytics: enabled")
    if feature_flags.FEATURE_TREND_ENGINE:
        logger.info("  └─ Trend engine: enabled")
else:
    logger.info("⏸️ Phase 16 Performance Analytics & Ranking Intelligence Layer disabled (set any FEATURE_*=True to enable)")

# Phase 17: Appeals & Governance Override Engine (conditionally enabled)
if feature_flags.FEATURE_APPEALS_ENGINE:
    from backend.routes.phase17_appeals import router as phase17_router
    app.include_router(phase17_router)
    logger.info("✅ Phase 17 Appeals & Governance Override Engine enabled")
    if feature_flags.FEATURE_MULTI_JUDGE_APPEALS:
        logger.info("  └─ Multi-judge appeals: enabled")
    if feature_flags.FEATURE_APPEAL_OVERRIDE_RANKING:
        logger.info("  └─ Appeal override ranking: enabled")
    if feature_flags.FEATURE_APPEAL_AUTO_CLOSE:
        logger.info("  └─ Auto-close: enabled")
else:
    logger.info("⏸️ Phase 17 Appeals & Governance Override Engine disabled (set FEATURE_APPEALS_ENGINE=True to enable)")

# Phase 18: Scheduling & Court Allocation Engine (conditionally enabled)
if feature_flags.FEATURE_SCHEDULING_ENGINE:
    from backend.routes.phase18_scheduling import router as phase18_router
    app.include_router(phase18_router)
    logger.info("✅ Phase 18 Scheduling & Court Allocation Engine enabled")
    if feature_flags.FEATURE_JUDGE_AVAILABILITY:
        logger.info("  └─ Judge availability: enabled")
else:
    logger.info("⏸️ Phase 18 Scheduling & Court Allocation Engine disabled (set FEATURE_SCHEDULING_ENGINE=True to enable)")

# Phase 19: Moot Courtroom Operations & Live Session Management (conditionally enabled)
if feature_flags.FEATURE_MOOT_OPERATIONS:
    from backend.routes.phase19_moot_operations import router as phase19_router
    app.include_router(phase19_router)
    logger.info("✅ Phase 19 Moot Courtroom Operations enabled")
    if feature_flags.FEATURE_SESSION_RECORDING:
        logger.info("  └─ Session recording: enabled")
else:
    logger.info("⏸️ Phase 19 Moot Courtroom Operations disabled (set FEATURE_MOOT_OPERATIONS=True to enable)")

# Phase 20: Tournament Lifecycle Orchestrator (conditionally enabled)
if feature_flags.FEATURE_TOURNAMENT_LIFECYCLE:
    from backend.routes.phase20_lifecycle import router as phase20_router
    app.include_router(phase20_router)
    logger.info("✅ Phase 20 Tournament Lifecycle Orchestrator enabled")
else:
    logger.info("⏸️ Phase 20 Tournament Lifecycle Orchestrator disabled (set FEATURE_TOURNAMENT_LIFECYCLE=True to enable)")

# Phase 21: Admin Command Center (conditionally enabled)
if feature_flags.FEATURE_ADMIN_COMMAND_CENTER:
    from backend.routes.phase21_admin_center import router as phase21_router
    app.include_router(phase21_router)
    logger.info("✅ Phase 21 Admin Command Center enabled")
else:
    logger.info("⏸️ Phase 21 Admin Command Center disabled (set FEATURE_ADMIN_COMMAND_CENTER=True to enable)")

# DEBUG: Log all registered routes on startup
from fastapi.routing import APIRoute
registered_paths = sorted([route.path for route in app.routes if isinstance(route, APIRoute)])
logger.info(f"✓ Registered API routes ({len(registered_paths)}): {registered_paths[:10]}...")  # Log first 10
if "/api/ai-moot/problems" in registered_paths:
    logger.info("✓ AI Moot routes properly registered")
else:
    logger.warning("⚠️  AI Moot routes MISSING - check router registration")

# Configure SQLAlchemy mappers
from sqlalchemy.orm import configure_mappers
configure_mappers()
logger.info("✓ SQLAlchemy mappers configured")

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    reload = os.getenv("ENVIRONMENT", "development") == "development"
    
    logger.info(f"Starting server on {host}:{port}")
    logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    logger.info(f"Auto-reload: {reload}")
    
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
# Phase 2: Competition Infrastructure
from backend.routes.competitions import router as competition_router
app.include_router(competition_router)
