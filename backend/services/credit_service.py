import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from backend.orm.user import User

logger = logging.getLogger(__name__)

async def check_credits(user_id: int, required: int, db: AsyncSession) -> bool:
    """
    Check if user has enough credits.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        return False
    
    return user.credits_remaining >= required


async def deduct_credits(user_id: int, amount: int, db: AsyncSession) -> bool:
    """
    Deduct credits from user account.
    """
    try:
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(credits_remaining=User.credits_remaining - amount)
        )
        await db.commit()
        logger.info(f"Deducted {amount} credits from user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to deduct credits: {str(e)}")
        await db.rollback()
        return False


async def get_user_credits(user_id: int, db: AsyncSession) -> int:
    """
    Get current credit balance for user.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        return 0
    
    return user.credits_remaining