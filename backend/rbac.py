"""
backend/rbac.py
Phase 5A: Role-Based Access Control (RBAC) System

Implements permission middleware for the Juris AI platform.
ALL moot-court routes must use these decorators.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Callable
from functools import wraps

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.database import get_db
from backend.orm.user import User, UserRole
from backend.errors import ErrorCode

logger = logging.getLogger(__name__)

# ================= CONFIG =================

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET_KEY", "refresh-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# ================= ROLE HIERARCHY =================
# PHASE 1: Role Freeze - Only teacher and student roles
ROLE_HIERARCHY = {
    UserRole.teacher: 2,
    UserRole.student: 1,
}

# Permission matrix for moot court features
# PHASE 1: Only teacher and student roles
MOOT_COURT_PERMISSIONS = {
    "create_project": [UserRole.student],
    "write_irac": [UserRole.student],
    "oral_round_speaker": [UserRole.student],
    "oral_round_bench": [UserRole.teacher],
    "evaluate_and_score": [UserRole.teacher],
    "view_all_teams": [UserRole.teacher],
    "create_competitions": [UserRole.teacher],
    "manage_institutions": [UserRole.teacher],
}

# ================= TOKEN UTILS =================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token with user_id, role, institution_id"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({
        "exp": expire,
        "type": "access"
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    """Create JWT refresh token"""
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh"
    }
    return jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str, is_refresh: bool = False) -> Optional[dict]:
    """Decode and validate JWT token"""
    try:
        key = REFRESH_SECRET_KEY if is_refresh else SECRET_KEY
        payload = jwt.decode(token, key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# ================= AUTH DEPENDENCIES =================

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get current authenticated user from JWT access token.
    Returns 401 if token is invalid or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "success": False,
            "error": "Unauthorized",
            "message": "Invalid or expired token",
            "code": ErrorCode.AUTH_INVALID
        },
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(token)
    if not payload:
        raise credentials_exception

    # Ensure it's an access token
    if payload.get("type") != "access":
        raise credentials_exception

    email = payload.get("sub")
    if not email:
        raise credentials_exception

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise credentials_exception

    return user


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Get current user if token exists, otherwise None. For optional auth endpoints."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]  # Remove "Bearer "
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        return None

    email = payload.get("sub")
    if not email:
        return None

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return None

    return user


# ================= RBAC MIDDLEWARE =================

def require_auth(func: Callable) -> Callable:
    """
    Decorator: Require authentication.
    Injects current_user as first parameter after self/request.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # FastAPI handles dependency injection, this is for documentation
        return await func(*args, **kwargs)
    return wrapper


def require_role(allowed_roles: List[UserRole]):
    """
    Decorator factory: Require specific role(s).
    Usage: @require_role([UserRole.teacher, UserRole.teacher])
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(
            *args,
            current_user: User = Depends(get_current_user),
            **kwargs
        ):
            if current_user.role not in allowed_roles:
                logger.warning(
                    f"Access denied: User {current_user.id} with role {current_user.role} "
                    f"attempted to access resource requiring {allowed_roles}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "success": False,
                        "error": "Forbidden",
                        "message": f"This action requires one of: {[r.value for r in allowed_roles]}",
                        "code": ErrorCode.PERMISSION_DENIED,
                        "current_role": current_user.role.value
                    }
                )
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator


def require_min_role(min_role: UserRole):
    """
    Decorator factory: Require minimum role level (hierarchy-based).
    Usage: @require_min_role(UserRole.teacher)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(
            *args,
            current_user: User = Depends(get_current_user),
            **kwargs
        ):
            user_level = ROLE_HIERARCHY.get(current_user.role, 0)
            min_level = ROLE_HIERARCHY.get(min_role, 0)

            if user_level < min_level:
                logger.warning(
                    f"Access denied: User {current_user.id} with role {current_user.role} "
                    f"attempted to access resource requiring minimum {min_role}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "success": False,
                        "error": "Forbidden",
                        "message": f"This action requires {min_role.value} or higher",
                        "code": ErrorCode.PERMISSION_DENIED,
                        "current_role": current_user.role.value
                    }
                )
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator


def require_admin(func: Callable) -> Callable:
    """
    Decorator: Require ADMIN or SUPER_ADMIN role.
    Backwards-compatible helper for legacy routes.
    """
    return require_min_role(UserRole.teacher)(func)


def require_permission(permission: str):
    """
    Decorator factory: Require specific moot-court permission.
    Uses MOOT_COURT_PERMISSIONS matrix.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(
            *args,
            current_user: User = Depends(get_current_user),
            **kwargs
        ):
            allowed_roles = MOOT_COURT_PERMISSIONS.get(permission, [])
            
            if not allowed_roles:
                logger.error(f"Permission '{permission}' not defined in MOOT_COURT_PERMISSIONS")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "success": False,
                        "error": "Internal Error",
                        "message": "Permission configuration error",
                        "code": ErrorCode.INTERNAL_ERROR
                    }
                )

            if current_user.role not in allowed_roles:
                logger.warning(
                    f"Permission denied: User {current_user.id} with role {current_user.role} "
                    f"attempted '{permission}' requiring {allowed_roles}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "success": False,
                        "error": "Forbidden",
                        "message": f"You do not have permission to {permission.replace('_', ' ')}",
                        "code": ErrorCode.PERMISSION_DENIED,
                        "required_roles": [r.value for r in allowed_roles]
                    }
                )
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator


def require_institution_match(func: Callable) -> Callable:
    """
    Decorator: Ensure user can only access data from their own institution.
    For use with routes that have institution_id parameter.
    """
    @wraps(func)
    async def wrapper(
        *args,
        institution_id: Optional[int] = None,
        current_user: User = Depends(get_current_user),
        **kwargs
    ):
        # Super admin can access any institution
        if current_user.role == UserRole.teacher:
            return await func(*args, institution_id=institution_id, current_user=current_user, **kwargs)

        # Users without institution can only access public data
        if current_user.institution_id is None:
            if institution_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "success": False,
                        "error": "Forbidden",
                        "message": "Institution membership required",
                        "code": ErrorCode.PERMISSION_DENIED
                    }
                )
            return await func(*args, institution_id=None, current_user=current_user, **kwargs)

        # Users can only access their own institution
        if institution_id is not None and institution_id != current_user.institution_id:
            logger.warning(
                f"Institution mismatch: User {current_user.id} from institution {current_user.institution_id} "
                f"attempted to access institution {institution_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "success": False,
                    "error": "Forbidden",
                    "message": "You can only access data from your own institution",
                    "code": ErrorCode.PERMISSION_DENIED
                }
            )

        return await func(*args, institution_id=current_user.institution_id, current_user=current_user, **kwargs)
    return wrapper


# ================= UTILITY FUNCTIONS =================

def check_permission(current_user: User, permission: str) -> bool:
    """Check if user has specific permission (for UI rendering decisions)."""
    allowed_roles = MOOT_COURT_PERMISSIONS.get(permission, [])
    return current_user.role in allowed_roles


def get_role_level(role: UserRole) -> int:
    """Get numeric level for role hierarchy comparison."""
    return ROLE_HIERARCHY.get(role, 0)


# ================= TOKEN REFRESH =================

async def refresh_access_token(
    refresh_token: str,
    db: AsyncSession
) -> dict:
    """
    Refresh access token using valid refresh token.
    Returns new tokens or raises 401.
    """
    payload = decode_token(refresh_token, is_refresh=True)
    
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": "Unauthorized",
                "message": "Invalid refresh token",
                "code": ErrorCode.AUTH_INVALID
            }
        )

    user_id = int(payload.get("sub", 0))
    
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.refresh_token == refresh_token,
            User.is_active == True
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": "Unauthorized",
                "message": "Refresh token invalid or expired",
                "code": ErrorCode.AUTH_EXPIRED
            }
        )

    # Check if refresh token is expired in DB
    if user.refresh_token_expires and datetime.utcnow().timestamp() > user.refresh_token_expires:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": "Unauthorized",
                "message": "Refresh token expired, please login again",
                "code": ErrorCode.AUTH_EXPIRED
            }
        )

    # Generate new tokens
    new_access_token = create_access_token(
        {
            "sub": user.email,
            "user_id": user.id,
            "role": user.role.value,
            "institution_id": user.institution_id
        }
    )
    new_refresh_token = create_refresh_token(user.id)

    # Update refresh token in DB
    user.refresh_token = new_refresh_token
    user.refresh_token_expires = int((datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).timestamp())
    await db.commit()

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "role": user.role.value,
        "user_id": user.id
    }
