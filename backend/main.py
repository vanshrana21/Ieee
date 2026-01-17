import os
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from backend.routes import progress
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


# ============================================
# CRITICAL: Load .env FIRST, before any backend imports
# ============================================
from dotenv import load_dotenv

# Get absolute path to project root (IEEE/)
# This file is at IEEE/backend/main.py, so go up one level
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Load environment variables from absolute path
load_dotenv(dotenv_path=ENV_FILE)

# Verify critical env vars are loaded
if not os.getenv("GEMINI_API_KEY"):
    logging.error(f"GEMINI_API_KEY not found. Checked: {ENV_FILE}")
    logging.error(f"File exists: {ENV_FILE.exists()}")
    sys.exit(1)

# Now safe to import backend modules
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from backend.routes import rag_search
from backend.routes import notes

from backend.database import init_db, close_db
from backend.routes import router
from backend.routes import search
# ============================================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router)

@app.get("/")
async def root():
    return {"message": "Legal Search API"}

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
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail
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

@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "LegalAI Research API",
        "version": "1.0.0",
        "docs": "/docs" if os.getenv("ENVIRONMENT", "development") == "development" else None
    }

app.include_router(router, prefix="/api")
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