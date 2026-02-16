"""
Phase 18 — Scheduling & Court Allocation API Routes.

Admin-controlled court scheduling with deterministic freeze and integrity verification.
"""
from datetime import date, datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.rbac import require_role, get_current_user
from backend.orm.user import UserRole
from backend.config.feature_flags import feature_flags

from backend.services.phase18_schedule_service import (
    ScheduleService, ScheduleError, ConflictError, InvalidStatusError,
    FrozenScheduleError
)
from backend.orm.phase18_scheduling import (
    ScheduleDay, TimeSlot, Courtroom, MatchScheduleAssignment,
    ScheduleStatus, AssignmentStatus
)


router = APIRouter(prefix="/api/schedule", tags=["scheduling"])


# =============================================================================
# Pydantic Request/Response Models
# =============================================================================

class CreateScheduleDayRequest(BaseModel):
    tournament_id: UUID
    day_number: int = Field(..., gt=0, description="Sequential day number")
    date: date


class CreateTimeSlotRequest(BaseModel):
    schedule_day_id: UUID
    start_time: datetime
    end_time: datetime
    slot_order: int = Field(..., gt=0, description="Display order within day")


class AssignMatchRequest(BaseModel):
    match_id: UUID
    courtroom_id: UUID
    time_slot_id: UUID
    judge_user_id: Optional[UUID] = None


class ScheduleDayResponse(BaseModel):
    id: UUID
    tournament_id: UUID
    day_number: int
    date: str
    status: str
    integrity_hash: Optional[str]
    created_at: str


class TimeSlotResponse(BaseModel):
    id: UUID
    schedule_day_id: UUID
    start_time: str
    end_time: str
    slot_order: int
    created_at: str


class CourtroomResponse(BaseModel):
    id: UUID
    tournament_id: UUID
    name: str
    capacity: Optional[int]
    is_active: bool
    created_at: str


class AssignmentResponse(BaseModel):
    id: UUID
    match_id: UUID
    courtroom_id: UUID
    time_slot_id: UUID
    judge_user_id: Optional[UUID]
    status: str
    created_at: str


class AssignmentDetailResponse(BaseModel):
    assignment: AssignmentResponse
    courtroom: CourtroomResponse
    time_slot: TimeSlotResponse


class VerifyResponse(BaseModel):
    schedule_day_id: UUID
    is_valid: bool
    stored_hash: Optional[str]
    message: str


class CreateCourtroomRequest(BaseModel):
    tournament_id: UUID
    name: str = Field(..., max_length=100)
    capacity: Optional[int] = Field(None, gt=0)


# =============================================================================
# Feature Flag Check
# =============================================================================

def check_scheduling_enabled():
    """Check if scheduling engine is enabled."""
    if not feature_flags.FEATURE_SCHEDULING_ENGINE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Scheduling engine is disabled"
        )


# =============================================================================
# Courtroom Routes
# =============================================================================

@router.post("/courtroom", response_model=CourtroomResponse)
async def create_courtroom(
    request: CreateCourtroomRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.teacher, UserRole.teacher]))
):
    """
    Create a new courtroom for a tournament.
    
    **Roles:** Admin, SuperAdmin
    """
    check_scheduling_enabled()
    
    courtroom = Courtroom(
        tournament_id=request.tournament_id,
        name=request.name,
        capacity=request.capacity,
        is_active=True
    )
    
    db.add(courtroom)
    await db.flush()
    
    return CourtroomResponse(
        id=courtroom.id,
        tournament_id=courtroom.tournament_id,
        name=courtroom.name,
        capacity=courtroom.capacity,
        is_active=courtroom.is_active,
        created_at=courtroom.created_at.isoformat() if courtroom.created_at else ""
    )


@router.get("/courtroom/{tournament_id}", response_model=List[CourtroomResponse])
async def list_courtrooms(
    tournament_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all courtrooms for a tournament.
    
    **Roles:** Any authenticated user
    """
    check_scheduling_enabled()
    
    from sqlalchemy import select
    
    query = select(Courtroom).where(
        Courtroom.tournament_id == tournament_id,
        Courtroom.is_active == True
    ).order_by(Courtroom.name)
    
    result = await db.execute(query)
    courtrooms = result.scalars().all()
    
    return [
        CourtroomResponse(
            id=c.id,
            tournament_id=c.tournament_id,
            name=c.name,
            capacity=c.capacity,
            is_active=c.is_active,
            created_at=c.created_at.isoformat() if c.created_at else ""
        )
        for c in courtrooms
    ]


# =============================================================================
# Schedule Day Routes
# =============================================================================

@router.post("/day", response_model=ScheduleDayResponse)
async def create_schedule_day(
    request: CreateScheduleDayRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.teacher, UserRole.teacher]))
):
    """
    Create a new schedule day.
    
    **Roles:** Admin, SuperAdmin
    
    The day starts in DRAFT status.
    """
    check_scheduling_enabled()
    
    try:
        schedule_day = await ScheduleService.create_schedule_day(
            db=db,
            tournament_id=request.tournament_id,
            day_number=request.day_number,
            schedule_date=request.date,
            created_by_user_id=current_user["id"]
        )
        
        return ScheduleDayResponse(
            id=schedule_day.id,
            tournament_id=schedule_day.tournament_id,
            day_number=schedule_day.day_number,
            date=schedule_day.date.isoformat() if schedule_day.date else "",
            status=schedule_day.status,
            integrity_hash=schedule_day.integrity_hash,
            created_at=schedule_day.created_at.isoformat() if schedule_day.created_at else ""
        )
    except ScheduleError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/day/{schedule_day_id}", response_model=ScheduleDayResponse)
async def get_schedule_day(
    schedule_day_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get schedule day details.
    
    **Roles:** Any authenticated user
    """
    check_scheduling_enabled()
    
    schedule_day = await ScheduleService.get_schedule_day(db, schedule_day_id)
    
    if not schedule_day:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule day not found"
        )
    
    return ScheduleDayResponse(
        id=schedule_day.id,
        tournament_id=schedule_day.tournament_id,
        day_number=schedule_day.day_number,
        date=schedule_day.date.isoformat() if schedule_day.date else "",
        status=schedule_day.status,
        integrity_hash=schedule_day.integrity_hash,
        created_at=schedule_day.created_at.isoformat() if schedule_day.created_at else ""
    )


@router.post("/day/{schedule_day_id}/lock", response_model=ScheduleDayResponse)
async def lock_schedule_day(
    schedule_day_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.teacher, UserRole.teacher]))
):
    """
    Lock a schedule day (DRAFT → LOCKED).
    
    **Roles:** Admin, SuperAdmin
    
    Once locked, no new time slots or assignments can be added.
    """
    check_scheduling_enabled()
    
    try:
        schedule_day = await ScheduleService.lock_schedule_day(
            db=db,
            schedule_day_id=schedule_day_id,
            locked_by_user_id=current_user["id"]
        )
        
        return ScheduleDayResponse(
            id=schedule_day.id,
            tournament_id=schedule_day.tournament_id,
            day_number=schedule_day.day_number,
            date=schedule_day.date.isoformat() if schedule_day.date else "",
            status=schedule_day.status,
            integrity_hash=schedule_day.integrity_hash,
            created_at=schedule_day.created_at.isoformat() if schedule_day.created_at else ""
        )
    except InvalidStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except ScheduleError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/day/{schedule_day_id}/freeze", response_model=ScheduleDayResponse)
async def freeze_schedule_day(
    schedule_day_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.teacher, UserRole.teacher]))
):
    """
    Freeze a schedule day (LOCKED → FROZEN).
    
    **Roles:** Admin, SuperAdmin
    
    Creates deterministic SHA256 integrity hash.
    Frozen schedules are immutable.
    """
    check_scheduling_enabled()
    
    try:
        schedule_day, integrity_hash = await ScheduleService.freeze_schedule_day(
            db=db,
            schedule_day_id=schedule_day_id,
            frozen_by_user_id=current_user["id"]
        )
        
        return ScheduleDayResponse(
            id=schedule_day.id,
            tournament_id=schedule_day.tournament_id,
            day_number=schedule_day.day_number,
            date=schedule_day.date.isoformat() if schedule_day.date else "",
            status=schedule_day.status,
            integrity_hash=schedule_day.integrity_hash,
            created_at=schedule_day.created_at.isoformat() if schedule_day.created_at else ""
        )
    except InvalidStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except ScheduleError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/day/{schedule_day_id}/verify", response_model=VerifyResponse)
async def verify_schedule_integrity(
    schedule_day_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Verify integrity of a frozen schedule.
    
    **Roles:** Any authenticated user
    
    Recomputes hash and compares with stored value using constant-time comparison.
    """
    check_scheduling_enabled()
    
    try:
        is_valid, stored_hash = await ScheduleService.verify_schedule_integrity(
            db=db,
            schedule_day_id=schedule_day_id
        )
        
        message = "Schedule integrity verified" if is_valid else "Schedule integrity check failed"
        
        return VerifyResponse(
            schedule_day_id=schedule_day_id,
            is_valid=is_valid,
            stored_hash=stored_hash,
            message=message
        )
    except ScheduleError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# =============================================================================
# Time Slot Routes
# =============================================================================

@router.post("/day/{schedule_day_id}/slot", response_model=TimeSlotResponse)
async def add_time_slot(
    schedule_day_id: UUID,
    request: CreateTimeSlotRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.teacher, UserRole.teacher]))
):
    """
    Add a time slot to a schedule day.
    
    **Roles:** Admin, SuperAdmin
    
    Validates:
    - Schedule not frozen
    - No overlapping slots
    - start_time < end_time
    """
    check_scheduling_enabled()
    
    try:
        time_slot = await ScheduleService.add_time_slot(
            db=db,
            schedule_day_id=schedule_day_id,
            start_time=request.start_time,
            end_time=request.end_time,
            slot_order=request.slot_order
        )
        
        return TimeSlotResponse(
            id=time_slot.id,
            schedule_day_id=time_slot.schedule_day_id,
            start_time=time_slot.start_time.isoformat() if time_slot.start_time else "",
            end_time=time_slot.end_time.isoformat() if time_slot.end_time else "",
            slot_order=time_slot.slot_order,
            created_at=time_slot.created_at.isoformat() if time_slot.created_at else ""
        )
    except FrozenScheduleError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ScheduleError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# =============================================================================
# Match Assignment Routes
# =============================================================================

@router.post("/assign", response_model=AssignmentResponse)
async def assign_match(
    request: AssignMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.teacher, UserRole.teacher]))
):
    """
    Assign a match to a courtroom, time slot, and optionally a judge.
    
    **Roles:** Admin, SuperAdmin
    
    Conflict checks:
    1. Match not already scheduled
    2. Courtroom not already booked in slot
    3. Judge not double-booked
    4. Teams not double-booked
    
    Returns HTTP 409 on any conflict.
    """
    check_scheduling_enabled()
    
    try:
        assignment = await ScheduleService.assign_match(
            db=db,
            match_id=request.match_id,
            courtroom_id=request.courtroom_id,
            time_slot_id=request.time_slot_id,
            judge_user_id=request.judge_user_id
        )
        
        return AssignmentResponse(
            id=assignment.id,
            match_id=assignment.match_id,
            courtroom_id=assignment.courtroom_id,
            time_slot_id=assignment.time_slot_id,
            judge_user_id=assignment.judge_user_id,
            status=assignment.status,
            created_at=assignment.created_at.isoformat() if assignment.created_at else ""
        )
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except FrozenScheduleError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ScheduleError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/day/{schedule_day_id}/assignments", response_model=List[AssignmentDetailResponse])
async def get_day_assignments(
    schedule_day_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all assignments for a schedule day.
    
    **Roles:** Any authenticated user
    """
    check_scheduling_enabled()
    
    assignments = await ScheduleService.get_assignments_by_day(db, schedule_day_id)
    
    return [
        AssignmentDetailResponse(
            assignment=AssignmentResponse(
                id=UUID(a["assignment"]["id"]),
                match_id=UUID(a["assignment"]["match_id"]),
                courtroom_id=UUID(a["assignment"]["courtroom_id"]),
                time_slot_id=UUID(a["assignment"]["time_slot_id"]),
                judge_user_id=UUID(a["assignment"]["judge_user_id"]) if a["assignment"]["judge_user_id"] else None,
                status=a["assignment"]["status"],
                created_at=a["assignment"]["created_at"]
            ),
            courtroom=CourtroomResponse(
                id=UUID(a["courtroom"]["id"]),
                tournament_id=UUID(a["courtroom"]["tournament_id"]),
                name=a["courtroom"]["name"],
                capacity=a["courtroom"]["capacity"],
                is_active=a["courtroom"]["is_active"],
                created_at=a["courtroom"]["created_at"]
            ),
            time_slot=TimeSlotResponse(
                id=UUID(a["time_slot"]["id"]),
                schedule_day_id=UUID(a["time_slot"]["schedule_day_id"]),
                start_time=a["time_slot"]["start_time"],
                end_time=a["time_slot"]["end_time"],
                slot_order=a["time_slot"]["slot_order"],
                created_at=a["time_slot"]["created_at"]
            )
        )
        for a in assignments
    ]


@router.get("/match/{match_id}", response_model=AssignmentResponse)
async def get_match_assignment(
    match_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get assignment for a specific match.
    
    **Roles:** Any authenticated user
    """
    check_scheduling_enabled()
    
    assignment = await ScheduleService.get_assignment_by_match(db, match_id)
    
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match not scheduled"
        )
    
    return AssignmentResponse(
        id=assignment.id,
        match_id=assignment.match_id,
        courtroom_id=assignment.courtroom_id,
        time_slot_id=assignment.time_slot_id,
        judge_user_id=assignment.judge_user_id,
        status=assignment.status,
        created_at=assignment.created_at.isoformat() if assignment.created_at else ""
    )


@router.post("/assignment/{assignment_id}/confirm", response_model=AssignmentResponse)
async def confirm_assignment(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.teacher, UserRole.teacher, UserRole.teacher]))
):
    """
    Confirm a match assignment (ASSIGNED → CONFIRMED).
    
    **Roles:** Judge, Admin, SuperAdmin
    """
    check_scheduling_enabled()
    
    try:
        assignment = await ScheduleService.confirm_assignment(
            db=db,
            assignment_id=assignment_id,
            confirmed_by_user_id=current_user["id"]
        )
        
        return AssignmentResponse(
            id=assignment.id,
            match_id=assignment.match_id,
            courtroom_id=assignment.courtroom_id,
            time_slot_id=assignment.time_slot_id,
            judge_user_id=assignment.judge_user_id,
            status=assignment.status,
            created_at=assignment.created_at.isoformat() if assignment.created_at else ""
        )
    except ScheduleError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
