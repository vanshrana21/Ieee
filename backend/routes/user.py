"""
backend/routes/user.py
Updated user routes with role information
"""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict

from backend.database import get_db
from backend.routes.auth import get_current_user
from backend.orm.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


class UserCreditsResponse(BaseModel):
    """
    Response model for user credits information.
    
    Changes:
    - Added 'role' field to help frontend customize UI
    """
    model_config = ConfigDict(from_attributes=True)
    
    credits_remaining: int
    is_premium: bool
    role: str  # NEW: Include role for frontend UI customization


@router.get("/credits", response_model=UserCreditsResponse)
async def get_user_credits(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's credit information.
    
    Changes:
    - Now includes user role in response
    
    Returns:
        UserCreditsResponse with credits_remaining, is_premium, and role
    """
    logger.info(f"User {current_user.id} ({current_user.role}) requesting credit information")
    
    return UserCreditsResponse(
        credits_remaining=current_user.credits_remaining,
        is_premium=current_user.is_premium,
        role=current_user.role.value  # NEW: Return role
    )