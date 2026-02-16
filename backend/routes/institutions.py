"""
backend/routes/institutions.py
Phase 5B: Institution management routes
Multi-tenancy support with strict data isolation
"""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc

from backend.database import get_db
from backend.orm.institution import Institution
from backend.orm.user import User, UserRole
from backend.rbac import get_current_user, require_role, require_min_role
from backend.errors import ErrorCode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/institutions", tags=["Institutions"])


# ================= SCHEMAS =================

class InstitutionCreate(BaseModel):
    """Schema for creating a new institution"""
    name: str = Field(..., min_length=3, max_length=255, description="Institution name")
    code: str = Field(..., min_length=3, max_length=50, description="Unique institution code")
    domain: Optional[str] = Field(None, description="Email domain for auto-assignment (e.g., university.edu)")
    description: Optional[str] = Field(None, description="Institution description")
    email: Optional[str] = Field(None, description="Contact email")
    phone: Optional[str] = Field(None, description="Contact phone")
    address: Optional[str] = Field(None, description="Physical address")


class InstitutionUpdate(BaseModel):
    """Schema for updating an institution"""
    name: Optional[str] = Field(None, min_length=3, max_length=255)
    domain: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    email: Optional[str] = Field(None)
    phone: Optional[str] = Field(None)
    address: Optional[str] = Field(None)
    status: Optional[str] = Field(None, pattern="^(active|suspended)$")


class InstitutionResponse(BaseModel):
    """Institution response schema"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    code: str
    domain: Optional[str]
    description: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    status: str
    is_active: bool
    created_at: str
    updated_at: str
    user_count: int
    competition_count: int


class InstitutionListResponse(BaseModel):
    """Paginated institution list"""
    success: bool
    data: List[InstitutionResponse]
    total: int
    page: int
    per_page: int


# ================= ROUTES =================

@router.post("", response_model=InstitutionResponse, status_code=201)
async def create_institution(
    data: InstitutionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new institution.
    Phase 5B: Only SUPER_ADMIN can create institutions.
    """
    # Only SUPER_ADMIN can create institutions
    if current_user.role != UserRole.teacher:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": "Only Super Administrators can create institutions",
                "code": ErrorCode.PERMISSION_DENIED
            }
        )
    
    # Check if code already exists
    result = await db.execute(select(Institution).where(Institution.code == data.code))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "Bad Request",
                "message": f"Institution code '{data.code}' already exists",
                "code": ErrorCode.INVALID_INPUT
            }
        )
    
    # Check if domain already exists (if provided)
    if data.domain:
        result = await db.execute(select(Institution).where(Institution.domain == data.domain))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error": "Bad Request",
                    "message": f"Institution domain '{data.domain}' already exists",
                    "code": ErrorCode.INVALID_INPUT
                }
            )
    
    # Create institution
    institution = Institution(
        name=data.name,
        code=data.code,
        domain=data.domain,
        description=data.description,
        email=data.email,
        phone=data.phone,
        address=data.address,
        status="active",
        is_active=True
    )
    
    db.add(institution)
    await db.commit()
    await db.refresh(institution)
    
    logger.info(f"Institution created: {institution.code} by user {current_user.id}")
    
    return institution.to_dict()


@router.get("", response_model=InstitutionListResponse)
async def list_institutions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by status: active, suspended"),
    search: Optional[str] = Query(None, description="Search by name or code"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List institutions.
    Phase 5B: SUPER_ADMIN sees all, others see only their institution.
    """
    # Build query
    query = select(Institution)
    
    # Non-super-admins can only see their own institution
    if current_user.role != UserRole.teacher:
        if not current_user.institution_id:
            return {
                "success": True,
                "data": [],
                "total": 0,
                "page": page,
                "per_page": per_page
            }
        query = query.where(Institution.id == current_user.institution_id)
    else:
        # SUPER_ADMIN can filter by status
        if status:
            query = query.where(Institution.status == status)
    
    # Search filter
    if search:
        search_filter = or_(
            Institution.name.ilike(f"%{search}%"),
            Institution.code.ilike(f"%{search}%")
        )
        query = query.where(search_filter)
    
    # Get total count
    count_result = await db.execute(select(Institution).where(query.whereclause))
    total = len(count_result.scalars().all())
    
    # Pagination
    query = query.order_by(desc(Institution.created_at))
    query = query.offset((page - 1) * per_page).limit(per_page)
    
    result = await db.execute(query)
    institutions = result.scalars().all()
    
    return {
        "success": True,
        "data": [inst.to_dict() for inst in institutions],
        "total": total,
        "page": page,
        "per_page": per_page
    }


@router.get("/{institution_id}", response_model=InstitutionResponse)
async def get_institution(
    institution_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get institution details.
    Phase 5B: Users can only access their own institution.
    """
    # Check institution access
    if current_user.role != UserRole.teacher:
        if current_user.institution_id != institution_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "success": False,
                    "error": "Forbidden",
                    "message": "You can only access your own institution",
                    "code": ErrorCode.PERMISSION_DENIED
                }
            )
    
    result = await db.execute(select(Institution).where(Institution.id == institution_id))
    institution = result.scalar_one_or_none()
    
    if not institution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": "Not Found",
                "message": "Institution not found",
                "code": ErrorCode.NOT_FOUND
            }
        )
    
    return institution.to_dict()


@router.patch("/{institution_id}", response_model=InstitutionResponse)
async def update_institution(
    institution_id: int,
    data: InstitutionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update institution.
    Phase 5B: SUPER_ADMIN can update any, ADMIN can update their own.
    """
    # Check permissions
    if current_user.role not in [UserRole.teacher, UserRole.teacher]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": "Insufficient permissions to update institution",
                "code": ErrorCode.PERMISSION_DENIED
            }
        )
    
    # ADMIN can only update their own institution
    if current_user.role == UserRole.teacher and current_user.institution_id != institution_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": "You can only update your own institution",
                "code": ErrorCode.PERMISSION_DENIED
            }
        )
    
    result = await db.execute(select(Institution).where(Institution.id == institution_id))
    institution = result.scalar_one_or_none()
    
    if not institution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": "Not Found",
                "message": "Institution not found",
                "code": ErrorCode.NOT_FOUND
            }
        )
    
    # Update fields
    if data.name is not None:
        institution.name = data.name
    if data.domain is not None:
        # Check domain uniqueness
        if data.domain != institution.domain:
            existing = await db.execute(select(Institution).where(Institution.domain == data.domain))
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "success": False,
                        "error": "Bad Request",
                        "message": f"Domain '{data.domain}' already exists",
                        "code": ErrorCode.INVALID_INPUT
                    }
                )
        institution.domain = data.domain
    if data.description is not None:
        institution.description = data.description
    if data.email is not None:
        institution.email = data.email
    if data.phone is not None:
        institution.phone = data.phone
    if data.address is not None:
        institution.address = data.address
    if data.status is not None:
        institution.status = data.status
        institution.is_active = (data.status == "active")
    
    institution.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(institution)
    
    logger.info(f"Institution updated: {institution.code} by user {current_user.id}")
    
    return institution.to_dict()


@router.delete("/{institution_id}", status_code=200)
async def suspend_institution(
    institution_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Suspend (soft-delete) an institution.
    Phase 5B: Only SUPER_ADMIN can suspend institutions.
    This is a SOFT DELETE - data is preserved but access is disabled.
    """
    if current_user.role != UserRole.teacher:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": "Only Super Administrators can suspend institutions",
                "code": ErrorCode.PERMISSION_DENIED
            }
        )
    
    result = await db.execute(select(Institution).where(Institution.id == institution_id))
    institution = result.scalar_one_or_none()
    
    if not institution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": "Not Found",
                "message": "Institution not found",
                "code": ErrorCode.NOT_FOUND
            }
        )
    
    # Soft delete: mark as suspended
    institution.status = "suspended"
    institution.is_active = False
    institution.updated_at = datetime.utcnow()
    
    await db.commit()
    
    logger.info(f"Institution suspended: {institution.code} by user {current_user.id}")
    
    return {
        "success": True,
        "message": f"Institution '{institution.name}' has been suspended",
        "institution_id": institution_id
    }


@router.post("/{institution_id}/reactivate", status_code=200)
async def reactivate_institution(
    institution_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Reactivate a suspended institution.
    Phase 5B: Only SUPER_ADMIN can reactivate institutions.
    """
    if current_user.role != UserRole.teacher:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": "Only Super Administrators can reactivate institutions",
                "code": ErrorCode.PERMISSION_DENIED
            }
        )
    
    result = await db.execute(select(Institution).where(Institution.id == institution_id))
    institution = result.scalar_one_or_none()
    
    if not institution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": "Not Found",
                "message": "Institution not found",
                "code": ErrorCode.NOT_FOUND
            }
        )
    
    institution.status = "active"
    institution.is_active = True
    institution.updated_at = datetime.utcnow()
    
    await db.commit()
    
    logger.info(f"Institution reactivated: {institution.code} by user {current_user.id}")
    
    return {
        "success": True,
        "message": f"Institution '{institution.name}' has been reactivated",
        "institution_id": institution_id
    }


@router.get("/{institution_id}/stats", status_code=200)
async def get_institution_stats(
    institution_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get institution statistics.
    Phase 5B: Users can only see their own institution stats.
    """
    # Check institution access
    if current_user.role != UserRole.teacher:
        if current_user.institution_id != institution_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "success": False,
                    "error": "Forbidden",
                    "message": "You can only access your own institution",
                    "code": ErrorCode.PERMISSION_DENIED
                }
            )
    
    result = await db.execute(select(Institution).where(Institution.id == institution_id))
    institution = result.scalar_one_or_none()
    
    if not institution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": "Not Found",
                "message": "Institution not found",
                "code": ErrorCode.NOT_FOUND
            }
        )
    
    # Get counts
    from backend.orm.competition import Competition
    from backend.orm.team import Team
    
    comp_result = await db.execute(
        select(Competition).where(Competition.institution_id == institution_id)
    )
    competitions = comp_result.scalars().all()
    
    team_result = await db.execute(
        select(Team).where(Team.institution_id == institution_id)
    )
    teams = team_result.scalars().all()
    
    user_result = await db.execute(
        select(User).where(User.institution_id == institution_id)
    )
    users = user_result.scalars().all()
    
    return {
        "success": True,
        "institution_id": institution_id,
        "name": institution.name,
        "stats": {
            "total_users": len(users),
            "total_competitions": len(competitions),
            "total_teams": len(teams),
            "active_competitions": sum(1 for c in competitions if c.status == "active"),
            "draft_competitions": sum(1 for c in competitions if c.status == "draft"),
            "users_by_role": {
                "student": sum(1 for u in users if u.role == UserRole.student),
                "judge": sum(1 for u in users if u.role == UserRole.teacher),
                "faculty": sum(1 for u in users if u.role == UserRole.teacher),
                "admin": sum(1 for u in users if u.role == UserRole.teacher),
            }
        }
    }
