"""
backend/routes/auth.py
Updated authentication routes with role support and rate limiting
"""
import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Optional
from functools import partial

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, ConfigDict

from backend.security.rbac import (
    create_access_token, 
    create_refresh_token, 
    get_current_user as rbac_get_current_user,
    validate_user_role_on_creation
)
from backend.database import get_db
from backend.orm.user import User, UserRole
from backend.errors import ErrorCode, raise_bad_request, raise_unauthorized

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])
limiter = Limiter(key_func=get_remote_address)

# ================= CONFIG =================

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Use asyncio-friendly password hashing
# bcrypt can block the event loop - run in thread pool for high concurrency
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__truncate_error=False,
    bcrypt__rounds=10,  # Slightly reduce rounds for performance (default is 12)
)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Thread pool for running blocking operations
_executor = None

def get_executor():
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4)
    return _executor

async def hash_password_async(password: str) -> str:
    """Async-friendly password hashing that doesn't block the event loop."""
    password = normalize_password(password)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(get_executor(), pwd_context.hash, password)

async def verify_password_async(plain: str, hashed: str) -> bool:
    """Async-friendly password verification that doesn't block the event loop."""
    plain = normalize_password(plain)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(get_executor(), pwd_context.verify, plain, hashed)

# ================= SCHEMAS =================

class UserRegister(BaseModel):
    """
    Registration schema with role field.
    
    Changes:
    - Added 'role' field (required, must be 'teacher' or 'student')
    """
    email: EmailStr
    password: str
    name: str
    role: UserRole  # NEW: Required role field (teacher or student only)


class UserLogin(BaseModel):
    """JSON login schema"""
    email: EmailStr
    password: str


class Token(BaseModel):
    """
    Token response schema with role information and refresh token.
    Phase 5A: Added refresh_token for session management.
    """
    access_token: str
    refresh_token: str  # NEW: Refresh token for session persistence
    token_type: str = "bearer"
    role: str  # User role
    user_id: int  # NEW: User ID for frontend
    institution_id: Optional[int] = None  # NEW: Institution context


class UserResponse(BaseModel):
    """
    User response schema with role.
    
    Changes:
    - Added 'role' field to user info
    """
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    email: str
    full_name: str
    role: str  # NEW: Include role in user response


# ================= UTILS =================

def normalize_password(password: str) -> str:
    """
    bcrypt only supports 72 bytes.
    We safely truncate AFTER UTF-8 encoding to preserve compatibility.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        encoded = encoded[:72]
    return encoded.decode("utf-8", errors="ignore")


def hash_password(password: str) -> str:
    """Synchronous password hash for backward compatibility."""
    password = normalize_password(password)
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Synchronous password verify for backward compatibility."""
    plain = normalize_password(plain)
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """
    Create JWT access token (Phase 5A: Delegated to rbac.py)
    """
    # Import here to avoid circular dependency
    from backend.rbac import create_access_token as rbac_create_access_token
    return rbac_create_access_token(data, expires_delta)


# ================= AUTH =================

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get current authenticated user from JWT token.
    Phase 11.1: Consistent error responses
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "success": False,
                    "error": "Unauthorized",
                    "message": "Invalid token payload",
                    "code": ErrorCode.AUTH_INVALID
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": "Unauthorized",
                "message": "Invalid or expired token",
                "code": ErrorCode.AUTH_EXPIRED if "expired" in str(e).lower() else ErrorCode.AUTH_INVALID
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": "Unauthorized",
                "message": "User not found",
                "code": ErrorCode.USER_NOT_FOUND
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


# ================= ROUTES =================

@router.post("/register", response_model=Token, status_code=201)
@limiter.limit("10/minute")  # Rate limit: 10 registrations per minute
async def register(
    request: Request,  # Required by slowapi
    user_data: UserRegister, 
    db: AsyncSession = Depends(get_db)
):
    """
    Register new user with role.
    Phase 5A: Added refresh token for session management.
    """
    from datetime import datetime, timedelta
    
    # DEBUG: Validate input before processing
    if not user_data.email or not user_data.password or not user_data.name:
        logger.warning(f"Malformed registration: email={user_data.email}, password_present={bool(user_data.password)}, name_present={bool(user_data.name)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "Bad Request",
                "message": "Email, password, and name required",
                "code": ErrorCode.INVALID_INPUT
            }
        )
    
    # STRICT ROLE VALIDATION - Phase 1: Only teacher or student allowed
    try:
        validate_user_role_on_creation(user_data.role.value)
    except HTTPException as e:
        logger.warning(f"Invalid role in registration: {user_data.role.value}")
        raise e
    
    logger.info(f"Registration attempt for email: {user_data.email}, role: {user_data.role}")
    
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        logger.warning(f"Email already registered: {user_data.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "Bad Request",
                "message": "Email already registered",
                "code": ErrorCode.INVALID_INPUT,
                "details": {"field": "email"}
            }
        )

    # Hash password asynchronously to not block event loop
    password_hash = await hash_password_async(user_data.password)
    
    user = User(
        email=user_data.email,
        full_name=user_data.name,
        password_hash=password_hash,
        role=user_data.role,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Create tokens
    access_token = create_access_token(
        {
            "sub": user.email,
            "user_id": user.id,
            "role": user.role.value,
            "institution_id": user.institution_id
        },
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = create_refresh_token(user.id)
    
    # Store refresh token
    user.refresh_token = refresh_token
    user.refresh_token_expires = int((datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).timestamp())
    await db.commit()

    logger.info(f"User registered successfully: {user_data.email} as {user_data.role}")
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": user.role.value,
        "user_id": user.id,
        "institution_id": user.institution_id
    }


@router.post("/login", response_model=Token)
@limiter.limit("30/minute")  # Rate limit: 30 logins per minute per IP
async def login(
    request: Request,  # Required by slowapi
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """
    Login user with JSON body and return tokens with role.
    Phase 5A: Added refresh token for session persistence.
    """
    from datetime import datetime, timedelta
    
    # DEBUG: Validate input before processing
    if not credentials.email or not credentials.password:
        logger.warning(f"Malformed login: email={credentials.email}, password_present={bool(credentials.password)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "Bad Request",
                "message": "Email and password required",
                "code": ErrorCode.INVALID_INPUT
            }
        )
    
    logger.info(f"Login attempt for email: {credentials.email}")
    
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()

    # Use async password verification to not block event loop
    password_valid = False
    if user:
        password_valid = await verify_password_async(credentials.password, user.password_hash)
    
    if not user or not password_valid:
        logger.warning(f"Invalid credentials for email: {credentials.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": "Unauthorized",
                "message": "Invalid email or password",
                "code": ErrorCode.AUTH_INVALID
            }
        )

    # Create tokens with full payload
    access_token = create_access_token(
        {
            "sub": user.email,
            "user_id": user.id,
            "role": user.role.value,
            "institution_id": user.institution_id
        },
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = create_refresh_token(user.id)
    
    # Store refresh token
    user.refresh_token = refresh_token
    user.refresh_token_expires = int((datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).timestamp())
    await db.commit()

    logger.info(f"User logged in successfully: {credentials.email} as {user.role}")
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": user.role.value,
        "user_id": user.id,
        "institution_id": user.institution_id
    }


@router.post("/login/form", response_model=Token)
@limiter.limit("30/minute")  # Rate limit: 30 logins per minute per IP
async def login_form(
    request: Request,  # Required by slowapi
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    Login user with form data (for OAuth2 compatibility).
    Phase 5A: Added refresh token for session persistence.
    """
    from datetime import datetime, timedelta
    
    logger.info(f"Form login attempt for username: {form_data.username}")
    
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    # Use async password verification to not block event loop
    password_valid = False
    if user:
        password_valid = await verify_password_async(form_data.password, user.password_hash)

    if not user or not password_valid:
        logger.warning(f"Invalid credentials for username: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": "Unauthorized",
                "message": "Invalid email or password",
                "code": ErrorCode.AUTH_INVALID
            }
        )

    # Create tokens with full payload
    access_token = create_access_token(
        {
            "sub": user.email,
            "user_id": user.id,
            "role": user.role.value,
            "institution_id": user.institution_id
        },
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = create_refresh_token(user.id)
    
    # Store refresh token
    user.refresh_token = refresh_token
    user.refresh_token_expires = int((datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).timestamp())
    await db.commit()

    logger.info(f"User logged in successfully: {form_data.username} as {user.role}")
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": user.role.value,
        "user_id": user.id,
        "institution_id": user.institution_id
    }


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """
    Get current user information.
    No changes needed - role is automatically included with User object.
    """
    return current_user


class RefreshTokenRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=Token)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh access token using refresh token.
    Phase 5A: Token refresh flow for session persistence.
    """
    from backend.rbac import refresh_access_token as rbac_refresh
    return await rbac_refresh(request.refresh_token, db)


@router.post("/logout")
async def logout(
    request: RefreshTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Logout user by invalidating refresh token.
    Phase 5A: Secure logout with token invalidation.
    """
    # Verify the refresh token belongs to current user
    if current_user.refresh_token == request.refresh_token:
        current_user.refresh_token = None
        current_user.refresh_token_expires = None
        await db.commit()
        logger.info(f"User {current_user.id} logged out successfully")
    
    return {
        "success": True,
        "message": "Logged out successfully"
    }


@router.post("/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Change user password.
    Phase 5A: Password change with old password verification.
    """
    if not verify_password(old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "Bad Request",
                "message": "Current password is incorrect",
                "code": ErrorCode.INVALID_INPUT
            }
        )
    
    current_user.password_hash = hash_password(new_password)
    await db.commit()
    
    # Invalidate all sessions by clearing refresh token
    current_user.refresh_token = None
    current_user.refresh_token_expires = None
    await db.commit()
    
    logger.info(f"User {current_user.id} changed password and sessions invalidated")
    
    return {
        "success": True,
        "message": "Password changed successfully. Please login again."
    }