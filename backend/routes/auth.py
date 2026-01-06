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
    No changes to logic - role is automatically included with User object.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception

    return user


# ================= ROUTES =================

@router.post("/register", response_model=Token, status_code=201)
async def register(user_data: UserRegister, db: AsyncSession = Depends(get_db)):
    """
    Register new user with role.
    
    Changes:
    - Now requires and stores 'role' field
    - Returns role in token response for frontend routing
    """
    logger.info(f"Registration attempt for email: {user_data.email}, role: {user_data.role}")
    
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        logger.warning(f"Email already registered: {user_data.email}")
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create user with role
    user = User(
        email=user_data.email,
        full_name=user_data.name,
        password_hash=hash_password(user_data.password),
        role=user_data.role,  # NEW: Set user role
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Create token with role in payload
    token = create_access_token(
        {"sub": user.email, "role": user.role.value},  # NEW: Include role in JWT
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    logger.info(f"✓ User registered successfully: {user_data.email} as {user_data.role}")
    
    # Return token with role for frontend routing
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role.value  # NEW: Return role
    }


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    Login user and return token with role.
    
    Changes:
    - Returns user role in response for frontend routing
    """
    logger.info(f"Login attempt for username: {form_data.username}")
    
    # Find user by email
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    # Verify credentials
    if not user or not verify_password(form_data.password, user.password_hash):
        logger.warning(f"Invalid credentials for username: {form_data.username}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create token with role in payload
    token = create_access_token(
        {"sub": user.email, "role": user.role.value},  # NEW: Include role in JWT
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    logger.info(f"✓ User logged in successfully: {form_data.username} as {user.role}")
    
    # Return token with role for frontend routing
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role.value  # NEW: Return role
    }


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """
    Get current user information.
    No changes needed - role is automatically included with User object.
    """
    return current_user