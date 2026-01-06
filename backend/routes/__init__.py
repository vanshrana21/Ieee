from fastapi import APIRouter
from backend.routes.auth import router as auth_router
from backend.routes.search import router as search_router
from backend.routes.user import router as user_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(search_router)
router.include_router(user_router)