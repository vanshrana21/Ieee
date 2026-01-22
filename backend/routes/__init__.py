"""
backend/routes/__init__.py
Route registration - UPDATED FOR PHASE 8 + PHASE 3.3
"""
from fastapi import APIRouter
from backend.routes import auth, user, curriculum, content, progress, case_detail, case_simplifier
from backend.routes import ai_tutor, recommendations  # PHASE 8
from backend.routes import practice  # PHASE 3.3

router = APIRouter()

# Existing routes
router.include_router(auth.router)
router.include_router(user.router)
router.include_router(curriculum.router)
router.include_router(content.router)
router.include_router(progress.router)
router.include_router(case_detail.router)
router.include_router(case_simplifier.router)

# PHASE 8: Intelligence routes
router.include_router(ai_tutor.router)
router.include_router(recommendations.router)

# PHASE 3.3: Practice Mode
router.include_router(practice.router)