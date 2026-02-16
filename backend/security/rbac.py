"""
backend/security/rbac.py
Phase 1: Role & Permission Freeze - Centralized RBAC Module

This module provides centralized role-based access control for the Moot Court system.
ONLY two roles are supported: "teacher" and "student"

All route files must use these decorators. No manual role checks allowed.
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

# ================= ROLE VALIDATION =================

# STRICT: Only these two roles are allowed
VALID_ROLES = {"teacher", "student"}


def validate_role(role: str) -> bool:
    """
    Strict role validation.
    Only 'teacher' and 'student' are valid.
    """
    return role in VALID_ROLES


def validate_role_or_raise(role: str) -> None:
    """
    Validate role and raise exception if invalid.
    """
    if not validate_role(role):
        logger.error(f"Invalid role detected: {role}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid role: {role}. Only 'teacher' and 'student' are allowed."
        )


# ================= TOKEN UTILS =================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token with user_id, role, institution_id"""
    # Validate role before encoding
    if "role" in data:
        validate_role_or_raise(data["role"])
    
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
        
        # Validate role in token
        if "role" in payload:
            if not validate_role(payload["role"]):
                logger.error(f"Invalid role in token: {payload['role']}")
                return None
        
        return payload
    except JWTError:
        return None


# ================= AUTH DEPENDENCIES =================

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get current authenticated user from JWT token.
    Validates role strictly.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        role: str = payload.get("role")
        
        if user_id is None:
            raise credentials_exception
        
        # Strict role validation
        if role and not validate_role(role):
            logger.error(f"Invalid role in JWT: {role}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid role: {role}"
            )
            
    except JWTError:
        raise credentials_exception
    
    # Fetch user from database
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    # Validate database role matches token role
    if role and user.role.value != role:
        logger.warning(f"Role mismatch: token={role}, db={user.role.value}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role mismatch detected"
        )
    
    return user


# ================= ROLE-BASED DECORATORS =================

def require_teacher(current_user: User = Depends(get_current_user)) -> User:
    """
    Require teacher role.
    Use as: Depends(require_teacher)
    """
    if current_user.role != UserRole.teacher:
        logger.warning(f"Access denied: user {current_user.id} has role {current_user.role.value}, expected teacher")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can perform this action"
        )
    return current_user


def require_student(current_user: User = Depends(get_current_user)) -> User:
    """
    Require student role.
    Use as: Depends(require_student)
    """
    if current_user.role != UserRole.student:
        logger.warning(f"Access denied: user {current_user.id} has role {current_user.role.value}, expected student")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can perform this action"
        )
    return current_user


def require_any_role(current_user: User = Depends(get_current_user)) -> User:
    """
    Require any valid role (teacher or student).
    Use as: Depends(require_any_role)
    """
    if current_user.role not in [UserRole.teacher, UserRole.student]:
        logger.error(f"Invalid role in database: {current_user.role.value}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid user role"
        )
    return current_user


# ================= PERMISSION MATRIX =================

# Simplified permission matrix for Moot Court
# Only teacher and student roles
MOOT_COURT_PERMISSIONS = {
    "create_session": [UserRole.teacher],
    "join_session": [UserRole.student],
    "manage_session": [UserRole.teacher],
    "submit_argument": [UserRole.student],
    "evaluate_arguments": [UserRole.teacher],  # AI or manual
    "view_scores": [UserRole.teacher, UserRole.student],
    "create_project": [UserRole.student],
    "write_irac": [UserRole.student],
    "oral_round_speaker": [UserRole.student],
    "oral_round_bench": [UserRole.teacher],
    "view_all_teams": [UserRole.teacher],
}


def check_permission(permission: str, user: User) -> bool:
    """
    Check if user has permission.
    """
    allowed_roles = MOOT_COURT_PERMISSIONS.get(permission, [])
    return user.role in allowed_roles


def require_permission(permission: str):
    """
    Decorator factory for permission-based access.
    Usage: @require_permission("create_session")
    """
    def decorator(current_user: User = Depends(get_current_user)) -> User:
        if not check_permission(permission, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}"
            )
        return current_user
    return decorator


# ================= FAIL-SAFE MIDDLEWARE =================

class RoleValidationMiddleware:
    """
    Fail-safe middleware to validate roles on every request.
    Rejects any request with invalid role immediately.
    """
    
    async def __call__(self, request: Request, call_next):
        # Check for role in headers or token
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            payload = decode_token(token)
            if payload and "role" in payload:
                role = payload["role"]
                if not validate_role(role):
                    logger.error(f"Fail-safe: Invalid role '{role}' rejected")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Invalid role in token"
                    )
        
        response = await call_next(request)
        return response


# ================= USER CREATION VALIDATION =================

def validate_user_role_on_creation(role: str) -> None:
    """
    Strict validation for user registration.
    Only 'teacher' or 'student' allowed.
    """
    if role not in VALID_ROLES:
        logger.error(f"User creation rejected: invalid role '{role}'")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: '{role}'. Must be 'teacher' or 'student'."
        )


# ================= BACKWARD COMPATIBILITY ALIASES =================

# These aliases help with gradual migration
def require_faculty(current_user: User = Depends(get_current_user)) -> User:
    """
    DEPRECATED: Use require_teacher instead.
    Kept for backward compatibility during migration.
    """
    return require_teacher(current_user)
