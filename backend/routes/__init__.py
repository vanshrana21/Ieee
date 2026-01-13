"""
backend/routes/__init__.py
Route registration - UPDATED FOR PHASE 8
"""
from fastapi import APIRouter
from backend.routes import auth, user, curriculum, content, progress
from backend.routes import ai_tutor, recommendations  # PHASE 8

router = APIRouter()

# Existing routes
router.include_router(auth.router)
router.include_router(user.router)
router.include_router(curriculum.router)
router.include_router(content.router)
router.include_router(progress.router)

# PHASE 8: Intelligence routes
router.include_router(ai_tutor.router)
router.include_router(recommendations.router)