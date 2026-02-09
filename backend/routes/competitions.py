"""
backend/routes/competitions.py
Phase 5B: Competition management routes with institution scoping
All queries are filtered by institution_id for strict data isolation
"""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc

from backend.database import get_db
from backend.orm.competition import Competition, CompetitionType, CompetitionStatus, CompetitionRound
from backend.orm.team import Team, TeamSide, TeamStatus
from backend.orm.institution import Institution
from backend.orm.user import User, UserRole
from backend.rbac import get_current_user, require_role, require_min_role
from backend.errors import ErrorCode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/competitions", tags=["Competitions"])


# ================= SCHEMAS =================

class CompetitionCreate(BaseModel):
    """Schema for creating a competition"""
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = None
    moot_type: CompetitionType = Field(default=CompetitionType.HYBRID)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    submission_deadline: Optional[datetime] = None
    registration_deadline: Optional[datetime] = None
    proposition_text: Optional[str] = None


class CompetitionUpdate(BaseModel):
    """Schema for updating a competition"""
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = None
    moot_type: Optional[CompetitionType] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    submission_deadline: Optional[datetime] = None
    registration_deadline: Optional[datetime] = None
    proposition_text: Optional[str] = None
    status: Optional[CompetitionStatus] = None
    is_published: Optional[bool] = None


class CompetitionResponse(BaseModel):
    """Competition response schema"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    institution_id: int
    title: str
    description: Optional[str]
    moot_type: str
    start_date: Optional[str]
    end_date: Optional[str]
    submission_deadline: Optional[str]
    status: str
    is_published: bool
    team_count: int
    created_at: str
    updated_at: str


class CompetitionDetailResponse(CompetitionResponse):
    """Full competition details including proposition"""
    proposition_text: Optional[str]
    rounds: List[dict]


class TeamCreate(BaseModel):
    """Schema for creating a team"""
    name: str = Field(..., min_length=3, max_length=255)
    side: TeamSide = Field(default=TeamSide.PETITIONER)
    member_ids: List[int] = Field(default=[], description="User IDs of team members")
    email: Optional[str] = None
    phone: Optional[str] = None


# ================= HELPER FUNCTIONS =================

async def check_institution_access(
    competition_institution_id: int,
    current_user: User,
    db: AsyncSession
) -> bool:
    """
    Phase 5B: Verify user has access to competition's institution.
    SUPER_ADMIN can access any, others only their own.
    """
    if current_user.role == UserRole.SUPER_ADMIN:
        return True
    
    if current_user.institution_id is None:
        return False
    
    return current_user.institution_id == competition_institution_id


async def check_competition_in_institution(
    competition_id: int,
    institution_id: int,
    db: AsyncSession
) -> bool:
    """Verify competition belongs to institution"""
    result = await db.execute(
        select(Competition).where(
            and_(
                Competition.id == competition_id,
                Competition.institution_id == institution_id
            )
        )
    )
    return result.scalar_one_or_none() is not None


# ================= ROUTES =================

@router.post("", response_model=CompetitionResponse, status_code=201)
async def create_competition(
    data: CompetitionCreate,
    institution_id: int = Query(..., description="Institution ID for the competition"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new competition.
    Phase 5B: Admin+ can create within their institution.
    """
    # Check permissions
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": "Only Admin, Faculty, or Super Admin can create competitions",
                "code": ErrorCode.PERMISSION_DENIED
            }
        )
    
    # Verify institution access
    if not await check_institution_access(institution_id, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": "You can only create competitions in your own institution",
                "code": ErrorCode.PERMISSION_DENIED
            }
        )
    
    # Verify institution exists and is active
    inst_result = await db.execute(
        select(Institution).where(
            and_(Institution.id == institution_id, Institution.status == "active")
        )
    )
    institution = inst_result.scalar_one_or_none()
    
    if not institution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": "Not Found",
                "message": "Institution not found or suspended",
                "code": ErrorCode.NOT_FOUND
            }
        )
    
    # Create competition
    competition = Competition(
        institution_id=institution_id,
        title=data.title,
        description=data.description,
        moot_type=data.moot_type,
        start_date=data.start_date,
        end_date=data.end_date,
        submission_deadline=data.submission_deadline,
        registration_deadline=data.registration_deadline,
        proposition_text=data.proposition_text,
        status=CompetitionStatus.DRAFT,
        is_published=False,
        created_by=current_user.id
    )
    
    db.add(competition)
    await db.commit()
    await db.refresh(competition)
    
    logger.info(f"Competition created: {competition.title} (institution: {institution_id}) by user {current_user.id}")
    
    return competition.to_dict()


@router.get("", response_model=dict)
async def list_competitions(
    institution_id: Optional[int] = Query(None, description="Filter by institution (defaults to user's institution)"),
    status: Optional[str] = Query(None, description="Filter by status: draft, registration, active, closed"),
    include_unpublished: bool = Query(False, description="Include unpublished competitions (Admin+ only)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List competitions.
    Phase 5B: Scoped to user's institution. Cross-institution access is IMPOSSIBLE.
    """
    # Determine effective institution_id
    effective_institution_id = institution_id
    
    if current_user.role != UserRole.SUPER_ADMIN:
        # Non-super-admins can only see their own institution
        if effective_institution_id is None:
            effective_institution_id = current_user.institution_id
        elif effective_institution_id != current_user.institution_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "success": False,
                    "error": "Forbidden",
                    "message": "You can only view competitions from your own institution",
                    "code": ErrorCode.PERMISSION_DENIED
                }
            )
    
    # If still no institution_id, return empty
    if effective_institution_id is None:
        return {
            "success": True,
            "data": [],
            "total": 0,
            "page": page,
            "per_page": per_page
        }
    
    # Build query with institution filter (CRITICAL for tenancy)
    query = select(Competition).where(Competition.institution_id == effective_institution_id)
    
    # Status filter
    if status:
        query = query.where(Competition.status == status)
    
    # Published filter - non-admin users only see published competitions
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]:
        query = query.where(Competition.is_published == True)
    elif not include_unpublished:
        query = query.where(Competition.is_published == True)
    
    # Get total count
    count_result = await db.execute(query)
    total = len(count_result.scalars().all())
    
    # Pagination
    query = query.order_by(desc(Competition.created_at))
    query = query.offset((page - 1) * per_page).limit(per_page)
    
    result = await db.execute(query)
    competitions = result.scalars().all()
    
    return {
        "success": True,
        "data": [comp.to_dict() for comp in competitions],
        "total": total,
        "page": page,
        "per_page": per_page,
        "institution_id": effective_institution_id
    }


@router.get("/{competition_id}", response_model=CompetitionDetailResponse)
async def get_competition(
    competition_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get competition details.
    Phase 5B: Only accessible within user's institution.
    """
    result = await db.execute(select(Competition).where(Competition.id == competition_id))
    competition = result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": "Not Found",
                "message": "Competition not found",
                "code": ErrorCode.NOT_FOUND
            }
        )
    
    # Phase 5B: Verify institution access
    if not await check_institution_access(competition.institution_id, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": "You can only access competitions from your own institution",
                "code": ErrorCode.PERMISSION_DENIED
            }
        )
    
    # Check if unpublished competition is accessible
    if not competition.is_published:
        if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "success": False,
                    "error": "Not Found",
                    "message": "Competition not found",
                    "code": ErrorCode.NOT_FOUND
                }
            )
    
    # Get rounds
    rounds_result = await db.execute(
        select(CompetitionRound)
        .where(CompetitionRound.competition_id == competition_id)
        .order_by(CompetitionRound.sequence)
    )
    rounds = rounds_result.scalars().all()
    
    response_data = competition.to_dict(include_proposition=True)
    response_data["rounds"] = [r.to_dict() for r in rounds]
    
    return response_data


@router.patch("/{competition_id}", response_model=CompetitionResponse)
async def update_competition(
    competition_id: int,
    data: CompetitionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a competition.
    Phase 5B: Admin+ can update within their institution.
    """
    result = await db.execute(select(Competition).where(Competition.id == competition_id))
    competition = result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": "Not Found",
                "message": "Competition not found",
                "code": ErrorCode.NOT_FOUND
            }
        )
    
    # Check permissions
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": "Only Admin, Faculty, or Super Admin can update competitions",
                "code": ErrorCode.PERMISSION_DENIED
            }
        )
    
    # Verify institution access
    if not await check_institution_access(competition.institution_id, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": "You can only update competitions in your own institution",
                "code": ErrorCode.PERMISSION_DENIED
            }
        )
    
    # Update fields
    if data.title is not None:
        competition.title = data.title
    if data.description is not None:
        competition.description = data.description
    if data.moot_type is not None:
        competition.moot_type = data.moot_type
    if data.start_date is not None:
        competition.start_date = data.start_date
    if data.end_date is not None:
        competition.end_date = data.end_date
    if data.submission_deadline is not None:
        competition.submission_deadline = data.submission_deadline
    if data.registration_deadline is not None:
        competition.registration_deadline = data.registration_deadline
    if data.proposition_text is not None:
        competition.proposition_text = data.proposition_text
    if data.status is not None:
        competition.status = data.status
    if data.is_published is not None:
        competition.is_published = data.is_published
    
    competition.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(competition)
    
    logger.info(f"Competition updated: {competition.title} by user {current_user.id}")
    
    return competition.to_dict()


@router.delete("/{competition_id}", status_code=200)
async def delete_competition(
    competition_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a competition.
    Phase 5B: Admin+ can delete within their institution.
    This cascades to delete teams and rounds.
    """
    result = await db.execute(select(Competition).where(Competition.id == competition_id))
    competition = result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": "Not Found",
                "message": "Competition not found",
                "code": ErrorCode.NOT_FOUND
            }
        )
    
    # Check permissions
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": "Only Admin or Super Admin can delete competitions",
                "code": ErrorCode.PERMISSION_DENIED
            }
        )
    
    # Verify institution access
    if not await check_institution_access(competition.institution_id, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": "You can only delete competitions in your own institution",
                "code": ErrorCode.PERMISSION_DENIED
            }
        )
    
    await db.delete(competition)
    await db.commit()
    
    logger.info(f"Competition deleted: {competition_id} by user {current_user.id}")
    
    return {
        "success": True,
        "message": "Competition deleted successfully",
        "competition_id": competition_id
    }


# ================= TEAM MANAGEMENT =================

@router.post("/{competition_id}/teams", response_model=dict, status_code=201)
async def create_team(
    competition_id: int,
    data: TeamCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a team for a competition.
    Phase 5B: Only within user's institution.
    """
    result = await db.execute(select(Competition).where(Competition.id == competition_id))
    competition = result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": "Not Found",
                "message": "Competition not found",
                "code": ErrorCode.NOT_FOUND
            }
        )
    
    # Verify institution access
    if not await check_institution_access(competition.institution_id, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": "You can only create teams in your own institution",
                "code": ErrorCode.PERMISSION_DENIED
            }
        )
    
    # Check if competition is accepting registrations
    if competition.status not in [CompetitionStatus.REGISTRATION, CompetitionStatus.ACTIVE]:
        if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error": "Bad Request",
                    "message": "This competition is not accepting new teams",
                    "code": ErrorCode.INVALID_INPUT
                }
            )
    
    # Create team
    team = Team(
        institution_id=competition.institution_id,
        competition_id=competition_id,
        name=data.name,
        side=data.side,
        status=TeamStatus.ACTIVE,
        email=data.email,
        phone=data.phone,
        created_by=current_user.id
    )
    
    db.add(team)
    await db.commit()
    await db.refresh(team)
    
    # Add members
    for user_id in data.member_ids:
        user_result = await db.execute(
            select(User).where(
                and_(User.id == user_id, User.institution_id == competition.institution_id)
            )
        )
        user = user_result.scalar_one_or_none()
        if user:
            team.members.append(user)
    
    await db.commit()
    
    logger.info(f"Team created: {team.name} for competition {competition_id} by user {current_user.id}")
    
    return {
        "success": True,
        "team": team.to_dict(include_members=True)
    }


@router.get("/{competition_id}/teams", response_model=dict)
async def list_teams(
    competition_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List teams in a competition.
    Phase 5B: Only within user's institution.
    """
    result = await db.execute(select(Competition).where(Competition.id == competition_id))
    competition = result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": "Not Found",
                "message": "Competition not found",
                "code": ErrorCode.NOT_FOUND
            }
        )
    
    # Verify institution access
    if not await check_institution_access(competition.institution_id, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": "You can only view teams from your own institution",
                "code": ErrorCode.PERMISSION_DENIED
            }
        )
    
    teams_result = await db.execute(
        select(Team).where(Team.competition_id == competition_id)
    )
    teams = teams_result.scalars().all()
    
    return {
        "success": True,
        "competition_id": competition_id,
        "teams": [team.to_dict(include_members=False) for team in teams]
    }
