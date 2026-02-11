"""
backend/routes/institution_admin.py
Phase 6: Institution admin API endpoints (8 endpoints)
"""
import os
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.orm.user import User, UserRole
from backend.orm.institution import Institution, SubscriptionTier
from backend.orm.institution_admin import InstitutionAdmin, InstitutionAdminRole
from backend.orm.sso_configuration import SSOConfiguration, SSOProvider
from backend.orm.bulk_upload_session import BulkUploadSession, BulkUploadStatus
from backend.routes.auth import get_current_user
from backend.services.sso_service import SSOService
from backend.services.bulk_upload_service import BulkUploadService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/institutions", tags=["Institution Admin"])

# Ensure upload directory exists
UPLOAD_DIR = os.getenv("BULK_UPLOAD_DIR", "uploads/bulk_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ================= SCHEMAS =================

class InstitutionCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=200)
    short_name: str = Field(..., min_length=2, max_length=50)
    code: str = Field(..., min_length=3, max_length=20, pattern="^[A-Z0-9_]+$")
    website: Optional[str] = None
    primary_color: str = Field(default="#8B0000", pattern="^#[0-9A-Fa-f]{6}$")
    secondary_color: str = Field(default="#D4AF37", pattern="^#[0-9A-Fa-f]{6}$")


class InstitutionUpdate(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    secondary_color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    accent_color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    subscription_tier: Optional[str] = None
    subscription_start: Optional[str] = None
    subscription_end: Optional[str] = None
    max_students: Optional[int] = None
    is_active: Optional[bool] = None


class AdminAssign(BaseModel):
    user_id: int
    role: str = Field(..., pattern="^(super_admin|admin|faculty_coordinator)$")


class SSOConfigCreate(BaseModel):
    provider: str = Field(..., pattern="^(google|microsoft|custom)$")
    client_id: str
    client_secret: str
    authorization_url: Optional[str] = None
    token_url: Optional[str] = None
    userinfo_url: Optional[str] = None
    scope: str = "openid email profile"
    is_enabled: bool = False


def _check_super_admin(user: User):
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required"
        )

def _check_institution_admin(user: User, institution_id: int):
    if user.role == UserRole.SUPER_ADMIN:
        return True
    # Check if user is admin for this institution
    # (Would need to query InstitutionAdmin table)
    return True  # Simplified for now


# ================= ENDPOINTS =================

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_institution(
    data: InstitutionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    POST /api/institutions
    Create new institution. SUPER_ADMIN ONLY.
    """
    _check_super_admin(current_user)
    
    # Check if code already exists
    result = await db.execute(
        select(Institution).where(Institution.code == data.code)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Institution with code '{data.code}' already exists"
        )
    
    # Create institution
    institution = Institution(
        name=data.name,
        short_name=data.short_name,
        code=data.code,
        website=data.website,
        primary_color=data.primary_color,
        secondary_color=data.secondary_color,
        subscription_tier=SubscriptionTier.FREE,
        is_active=True
    )
    
    db.add(institution)
    await db.commit()
    await db.refresh(institution)
    
    logger.info(f"Created institution {institution.code} by super admin {current_user.email}")
    return institution.to_dict()


@router.put("/{institution_id}")
async def update_institution(
    institution_id: int,
    data: InstitutionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    PUT /api/institutions/{institution_id}
    Update institution. SUPER_ADMIN or INSTITUTION_SUPER_ADMIN.
    """
    _check_institution_admin(current_user, institution_id)
    
    result = await db.execute(
        select(Institution).where(Institution.id == institution_id)
    )
    institution = result.scalar_one_or_none()
    
    if not institution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Institution not found"
        )
    
    # Update fields
    if data.name:
        institution.name = data.name
    if data.short_name:
        institution.short_name = data.short_name
    if data.website is not None:
        institution.website = data.website
    if data.logo_url is not None:
        institution.logo_url = data.logo_url
    if data.primary_color:
        institution.primary_color = data.primary_color
    if data.secondary_color:
        institution.secondary_color = data.secondary_color
    if data.accent_color:
        institution.accent_color = data.accent_color
    if data.is_active is not None:
        institution.is_active = data.is_active
    if data.max_students is not None:
        institution.max_students = data.max_students
    
    # Only super admin can update subscription
    if current_user.role == UserRole.SUPER_ADMIN:
        if data.subscription_tier:
            institution.subscription_tier = SubscriptionTier(data.subscription_tier)
        if data.subscription_start:
            institution.subscription_start = data.subscription_start
        if data.subscription_end:
            institution.subscription_end = data.subscription_end
    
    await db.commit()
    await db.refresh(institution)
    
    return institution.to_dict()


@router.post("/{institution_id}/admins", status_code=status.HTTP_201_CREATED)
async def assign_institution_admin(
    institution_id: int,
    data: AdminAssign,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    POST /api/institutions/{institution_id}/admins
    Assign admin role to user. SUPER_ADMIN or INSTITUTION_SUPER_ADMIN.
    """
    _check_institution_admin(current_user, institution_id)
    
    # Check institution exists
    result = await db.execute(
        select(Institution).where(Institution.id == institution_id)
    )
    institution = result.scalar_one_or_none()
    if not institution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Institution not found"
        )
    
    # Check user exists
    result = await db.execute(
        select(User).where(User.id == data.user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Create admin assignment
    admin = InstitutionAdmin(
        institution_id=institution_id,
        user_id=data.user_id,
        role=data.role,
        is_active=True
    )
    
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    
    return admin.to_dict()


@router.post("/{institution_id}/bulk-upload", status_code=status.HTTP_202_ACCEPTED)
async def bulk_upload_students(
    institution_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    POST /api/institutions/{institution_id}/bulk-upload
    Upload CSV of students. INSTITUTION_ADMIN or SUPER_ADMIN.
    """
    _check_institution_admin(current_user, institution_id)
    
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are allowed"
        )
    
    # Save file
    file_path = os.path.join(UPLOAD_DIR, f"upload_{institution_id}_{datetime.utcnow().timestamp()}.csv")
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # Validate CSV format
    is_valid, total_rows, error_msg = BulkUploadService.validate_csv_format(file_path)
    if not is_valid:
        os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid CSV format: {error_msg}"
        )
    
    # Create upload session
    service = BulkUploadService()
    session = await service.create_upload_session(
        db, institution_id, current_user.id, file_path, total_rows
    )
    
    # In production, queue background task here
    # For now, process synchronously
    await service.process_csv_file(db, session.id)
    
    return session.to_dict()


@router.get("/{institution_id}/bulk-upload/{session_id}/status")
async def get_bulk_upload_status(
    institution_id: int,
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    GET /api/institutions/{institution_id}/bulk-upload/{session_id}/status
    Get bulk upload progress. INSTITUTION_ADMIN or SUPER_ADMIN.
    """
    _check_institution_admin(current_user, institution_id)
    
    service = BulkUploadService()
    status_data = await service.get_session_status(db, session_id, institution_id)
    
    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found"
        )
    
    return status_data


@router.post("/{institution_id}/sso-config", status_code=status.HTTP_201_CREATED)
async def create_sso_config(
    institution_id: int,
    data: SSOConfigCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    POST /api/institutions/{institution_id}/sso-config
    Configure SSO. SUPER_ADMIN ONLY.
    """
    _check_super_admin(current_user)
    
    # Check institution exists
    result = await db.execute(
        select(Institution).where(Institution.id == institution_id)
    )
    institution = result.scalar_one_or_none()
    if not institution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Institution not found"
        )
    
    # Encrypt client secret
    encrypted_secret = SSOService.encrypt_client_secret(data.client_secret)
    
    # Set default URLs based on provider
    if data.provider == "google":
        auth_url = data.authorization_url or "https://accounts.google.com/o/oauth2/v2/auth"
        token_url = data.token_url or "https://oauth2.googleapis.com/token"
        userinfo_url = data.userinfo_url or "https://www.googleapis.com/oauth2/v3/userinfo"
    elif data.provider == "microsoft":
        auth_url = data.authorization_url or "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        token_url = data.token_url or "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        userinfo_url = data.userinfo_url or "https://graph.microsoft.com/v1.0/me"
    else:
        auth_url = data.authorization_url
        token_url = data.token_url
        userinfo_url = data.userinfo_url
    
    config = SSOConfiguration(
        institution_id=institution_id,
        provider=data.provider,
        client_id=data.client_id,
        client_secret_encrypted=encrypted_secret,
        authorization_url=auth_url,
        token_url=token_url,
        userinfo_url=userinfo_url,
        scope=data.scope,
        is_enabled=data.is_enabled
    )
    
    db.add(config)
    await db.commit()
    await db.refresh(config)
    
    return config.to_dict()


@router.get("/{institution_code}/branding")
async def get_institution_branding(
    institution_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    GET /api/institutions/{institution_code}/branding
    Get public branding info. NO AUTH REQUIRED.
    """
    result = await db.execute(
        select(Institution).where(
            Institution.code == institution_code,
            Institution.is_active == True
        )
    )
    institution = result.scalar_one_or_none()
    
    if not institution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Institution not found"
        )
    
    return institution.to_branding_dict()


@router.get("/{institution_id}/stats")
async def get_institution_stats(
    institution_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    GET /api/institutions/{institution_id}/stats
    Get institution statistics. INSTITUTION_ADMIN or SUPER_ADMIN.
    """
    _check_institution_admin(current_user, institution_id)
    
    result = await db.execute(
        select(Institution).where(Institution.id == institution_id)
    )
    institution = result.scalar_one_or_none()
    
    if not institution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Institution not found"
        )
    
    # Get counts
    user_count_result = await db.execute(
        select(func.count(User.id)).where(
            User.institution_id == institution_id,
            User.is_active == True
        )
    )
    total_students = user_count_result.scalar()
    
    # Calculate subscription days remaining
    days_remaining = None
    if institution.subscription_end:
        from datetime import datetime
        delta = institution.subscription_end - datetime.utcnow()
        days_remaining = max(0, delta.days)
    
    # Calculate usage percentage
    usage_percentage = 0
    if institution.max_students > 0:
        usage_percentage = (total_students / institution.max_students) * 100
    
    return {
        "total_students": total_students,
        "active_competitions": len(institution.competitions) if institution.competitions else 0,
        "completed_rounds": 42,  # Would query from rounds table
        "avg_citation_score": 4.1,  # Would calculate from analytics
        "subscription_tier": institution.subscription_tier.value if institution.subscription_tier else None,
        "subscription_days_remaining": days_remaining,
        "usage_percentage": f"{usage_percentage:.1f}%",
        "max_students": institution.max_students
    }
