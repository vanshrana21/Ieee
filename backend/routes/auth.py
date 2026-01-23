"""
backend/routes/auth.py
Updated authentication routes with role support
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, ConfigDict

from backend.database import get_db
from backend.orm.user import User, UserRole
from backend.errors import ErrorCode, raise_bad_request, raise_unauthorized

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ================= CONFIG =================

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# ================= SCHEMAS =================

class UserRegister(BaseModel):
    """
    Registration schema with role field.
    
    Changes:
    - Added 'role' field (required, must be 'lawyer' or 'student')
    """
    email: EmailStr
    password: str
    name: str
    role: UserRole  # NEW: Required role field


class UserLogin(BaseModel):
    """JSON login schema"""
    email: EmailStr
    password: str


class Token(BaseModel):
    """
    Token response schema with role information.
    
    Changes:
    - Added 'role' field to return user role on login
    """
    access_token: str
    token_type: str = "bearer"
    role: str  # NEW: Return role so frontend knows where to redirect


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

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """
    Create JWT access token.
    
    Changes:
    - Now includes 'role' in JWT payload for role-based access control
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


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
async def register(user_data: UserRegister, db: AsyncSession = Depends(get_db)):
    """
    Register new user with role.
    Phase 11.1: Consistent error responses
    """
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

    user = User(
        email=user_data.email,
        full_name=user_data.name,
        password_hash=hash_password(user_data.password),
        role=user_data.role,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(
        {"sub": user.email, "role": user.role.value},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    logger.info(f"User registered successfully: {user_data.email} as {user_data.role}")
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role.value
    }


@router.post("/login", response_model=Token)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """
    Login user with JSON body and return token with role.
    """
    logger.info(f"Login attempt for email: {credentials.email}")
    
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.password_hash):
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

    token = create_access_token(
        {"sub": user.email, "role": user.role.value},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    logger.info(f"User logged in successfully: {credentials.email} as {user.role}")
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role.value
    }


@router.post("/login/form", response_model=Token)
async def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    Login user with form data (for OAuth2 compatibility).
    """
    logger.info(f"Form login attempt for username: {form_data.username}")
    
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.password_hash):
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

    token = create_access_token(
        {"sub": user.email, "role": user.role.value},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    logger.info(f"User logged in successfully: {form_data.username} as {user.role}")
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role.value
    }


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """
    Get current user information.
    No changes needed - role is automatically included with User object.
    """
    return current_user