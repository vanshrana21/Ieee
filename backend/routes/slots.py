"""
backend/routes/slots.py
Phase 5C: Oral round slot management with calendar/availability system
"""
import os
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, asc
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.orm.submission_slot import SubmissionSlot, SlotStatus, SlotType, SlotBookingLog, TeamSlotPreference
from backend.orm.competition import Competition
from backend.orm.team import Team
from backend.orm.user import User, UserRole
from backend.rbac import get_current_user
from backend.errors import ErrorCode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/slots", tags=["Submission Slots"])


# ================= SCHEMAS =================

class SlotCreate(BaseModel):
    """Schema for creating a time slot"""
    start_time: datetime
    end_time: datetime
    slot_type: SlotType = SlotType.PRELIMINARY
    venue: Optional[str] = None
    room_url: Optional[str] = None
    duration_minutes: int = Field(default=30, ge=15, le=180)
    notes: Optional[str] = None


class SlotUpdate(BaseModel):
    """Schema for updating a slot"""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    venue: Optional[str] = None
    room_url: Optional[str] = None
    status: Optional[SlotStatus] = None
    presiding_judge_id: Optional[int] = None
    wing_judge_1_id: Optional[int] = None
    wing_judge_2_id: Optional[int] = None
    notes: Optional[str] = None


class SlotBookRequest(BaseModel):
    """Schema for booking a slot"""
    team_id: int
    petitioner_team_id: Optional[int] = None
    respondent_team_id: Optional[int] = None
    notes: Optional[str] = None


class SlotResponse(BaseModel):
    """Slot response schema"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    start_time: str
    end_time: str
    duration_minutes: int
    slot_type: str
    status: str
    venue: Optional[str]
    room_url: Optional[str]
    booked_by_team_id: Optional[int]
    is_bookable: bool
    is_past: bool


# ================= HELPER FUNCTIONS =================

def generate_slots_bulk(
    start_date: datetime,
    end_date: datetime,
    daily_start_hour: int = 9,
    daily_end_hour: int = 17,
    slot_duration_minutes: int = 30,
    skip_weekends: bool = True
) -> List[dict]:
    """
    Generate time slots in bulk for a date range.
    Returns list of slot dicts ready for insertion.
    """
    slots = []
    current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    
    while current_date <= end_date:
        # Skip weekends
        if skip_weekends and current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue
        
        # Generate slots for the day
        day_start = current_date.replace(hour=daily_start_hour, minute=0)
        current_time = day_start
        
        while current_time.hour < daily_end_hour:
            slot_end = current_time + timedelta(minutes=slot_duration_minutes)
            
            # Don't go past daily end
            if slot_end.hour > daily_end_hour or (slot_end.hour == daily_end_hour and slot_end.minute > 0):
                break
            
            slots.append({
                "start_time": current_time,
                "end_time": slot_end,
                "duration_minutes": slot_duration_minutes
            })
            
            current_time = slot_end
        
        current_date += timedelta(days=1)
    
    return slots


async def check_slot_conflict(
    competition_id: int,
    start_time: datetime,
    end_time: datetime,
    exclude_slot_id: Optional[int] = None,
    db: AsyncSession = None
) -> Optional[SubmissionSlot]:
    """
    Check if there's a conflicting slot (overlapping time).
    Returns conflicting slot if found.
    """
    query = select(SubmissionSlot).where(
        and_(
            SubmissionSlot.competition_id == competition_id,
            SubmissionSlot.start_time < end_time,
            SubmissionSlot.end_time > start_time
        )
    )
    
    if exclude_slot_id:
        query = query.where(SubmissionSlot.id != exclude_slot_id)
    
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_available_slots(
    competition_id: int,
    slot_type: Optional[SlotType] = None,
    start_after: Optional[datetime] = None,
    start_before: Optional[datetime] = None,
    db: AsyncSession = None
) -> List[SubmissionSlot]:
    """
    Get available (bookable) slots for a competition.
    """
    now = datetime.utcnow()
    
    query = select(SubmissionSlot).where(
        and_(
            SubmissionSlot.competition_id == competition_id,
            SubmissionSlot.status == SlotStatus.AVAILABLE,
            SubmissionSlot.start_time > now
        )
    )
    
    if slot_type:
        query = query.where(SubmissionSlot.slot_type == slot_type)
    
    if start_after:
        query = query.where(SubmissionSlot.start_time >= start_after)
    
    if start_before:
        query = query.where(SubmissionSlot.start_time <= start_before)
    
    query = query.order_by(asc(SubmissionSlot.start_time))
    
    result = await db.execute(query)
    return result.scalars().all()


# ================= SLOT MANAGEMENT =================

@router.post("/bulk-generate", status_code=201)
async def generate_slots_bulk_endpoint(
    competition_id: int = Query(...),
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    daily_start_hour: int = Query(9),
    daily_end_hour: int = Query(17),
    slot_duration_minutes: int = Query(30),
    slot_type: SlotType = Query(SlotType.PRELIMINARY),
    skip_weekends: bool = Query(True),
    venue_prefix: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate time slots in bulk for a competition.
    Admin+ only.
    """
    # Check permissions
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    # Verify competition access
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Generate slots
    slot_dicts = generate_slots_bulk(
        start_date=start_date,
        end_date=end_date,
        daily_start_hour=daily_start_hour,
        daily_end_hour=daily_end_hour,
        slot_duration_minutes=slot_duration_minutes,
        skip_weekends=skip_weekends
    )
    
    created_count = 0
    for slot_dict in slot_dicts:
        # Check for conflicts
        conflict = await check_slot_conflict(
            competition_id,
            slot_dict["start_time"],
            slot_dict["end_time"],
            db=db
        )
        
        if conflict:
            continue  # Skip conflicting slots
        
        slot = SubmissionSlot(
            institution_id=competition.institution_id,
            competition_id=competition_id,
            slot_type=slot_type,
            status=SlotStatus.AVAILABLE,
            start_time=slot_dict["start_time"],
            end_time=slot_dict["end_time"],
            duration_minutes=slot_dict["duration_minutes"],
            venue=f"{venue_prefix} {created_count + 1}" if venue_prefix else None,
            created_by=current_user.id
        )
        
        db.add(slot)
        created_count += 1
    
    await db.commit()
    
    logger.info(f"Generated {created_count} slots for competition {competition_id}")
    
    return {
        "success": True,
        "slots_created": created_count,
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        }
    }


@router.post("", status_code=201)
async def create_slot(
    data: SlotCreate,
    competition_id: int = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a single time slot.
    """
    # Check permissions
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    # Verify competition
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check for conflicts
    conflict = await check_slot_conflict(
        competition_id,
        data.start_time,
        data.end_time,
        db=db
    )
    
    if conflict:
        raise HTTPException(
            status_code=400,
            detail=f"Time slot conflicts with existing slot {conflict.id} ({conflict.start_time} - {conflict.end_time})"
        )
    
    # Create slot
    slot = SubmissionSlot(
        institution_id=competition.institution_id,
        competition_id=competition_id,
        slot_type=data.slot_type,
        status=SlotStatus.AVAILABLE,
        start_time=data.start_time,
        end_time=data.end_time,
        duration_minutes=data.duration_minutes,
        venue=data.venue,
        room_url=data.room_url,
        admin_notes=data.notes,
        created_by=current_user.id
    )
    
    db.add(slot)
    await db.commit()
    await db.refresh(slot)
    
    logger.info(f"Slot created: {slot.id} for competition {competition_id}")
    
    return {
        "success": True,
        "slot": slot.to_dict()
    }


@router.get("/calendar", status_code=200)
async def get_slot_calendar(
    competition_id: int = Query(...),
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get slots formatted for calendar view.
    Returns slots grouped by date.
    """
    # Verify competition access
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get slots in date range
    result = await db.execute(
        select(SubmissionSlot).where(
            and_(
                SubmissionSlot.competition_id == competition_id,
                SubmissionSlot.start_time >= start_date,
                SubmissionSlot.start_time <= end_date
            )
        ).order_by(asc(SubmissionSlot.start_time))
    )
    slots = result.scalars().all()
    
    # Group by date
    calendar = {}
    for slot in slots:
        date_key = slot.start_time.strftime("%Y-%m-%d")
        if date_key not in calendar:
            calendar[date_key] = []
        calendar[date_key].append(slot.to_dict())
    
    return {
        "success": True,
        "competition_id": competition_id,
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "calendar": calendar
    }


@router.get("/available", status_code=200)
async def list_available_slots(
    competition_id: int = Query(...),
    slot_type: Optional[SlotType] = Query(None),
    start_after: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List available slots for booking.
    Students see only available slots.
    """
    # Verify competition access
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    slots = await get_available_slots(
        competition_id=competition_id,
        slot_type=slot_type,
        start_after=start_after or datetime.utcnow(),
        db=db
    )
    
    return {
        "success": True,
        "competition_id": competition_id,
        "available_slots": [s.to_dict() for s in slots],
        "count": len(slots)
    }


@router.post("/{slot_id}/book", status_code=200)
async def book_slot(
    slot_id: int,
    data: SlotBookRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Book a time slot for a team's oral round.
    """
    # Get slot
    result = await db.execute(
        select(SubmissionSlot).where(SubmissionSlot.id == slot_id)
    )
    slot = result.scalar_one_or_none()
    
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    
    # Check if slot is available
    if slot.status != SlotStatus.AVAILABLE:
        raise HTTPException(status_code=400, detail=f"Slot is not available (status: {slot.status.value})")
    
    # Check if slot is in the past
    if slot.start_time < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Cannot book a slot in the past")
    
    # Verify team
    team_result = await db.execute(
        select(Team).where(
            and_(
                Team.id == data.team_id,
                Team.competition_id == slot.competition_id
            )
        )
    )
    team = team_result.scalar_one_or_none()
    
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Check permissions
    if current_user.role == UserRole.STUDENT:
        # Must be team member
        if current_user.id not in [m.id for m in team.members]:
            raise HTTPException(status_code=403, detail="You are not a member of this team")
    elif current_user.role in [UserRole.ADMIN, UserRole.FACULTY]:
        # Must be same institution
        if current_user.institution_id != slot.institution_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if team already has a booking for this competition
    existing_booking = await db.execute(
        select(SubmissionSlot).where(
            and_(
                SubmissionSlot.competition_id == slot.competition_id,
                SubmissionSlot.booked_by_team_id == data.team_id,
                SubmissionSlot.status == SlotStatus.BOOKED
            )
        )
    )
    if existing_booking.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Team already has a booked slot for this competition")
    
    # Book the slot
    slot.status = SlotStatus.BOOKED
    slot.booked_by_team_id = data.team_id
    slot.booked_at = datetime.utcnow()
    slot.petitioner_team_id = data.petitioner_team_id
    slot.respondent_team_id = data.respondent_team_id
    slot.admin_notes = data.notes
    
    # Create log
    log = SlotBookingLog(
        slot_id=slot_id,
        action="book",
        performed_by=current_user.id,
        new_value=f"team_id: {data.team_id}"
    )
    db.add(log)
    
    await db.commit()
    await db.refresh(slot)
    
    logger.info(f"Slot {slot_id} booked by team {data.team_id}")
    
    return {
        "success": True,
        "slot": slot.to_dict(),
        "message": f"Slot booked successfully for {slot.start_time.strftime('%Y-%m-%d %H:%M')}"
    }


@router.post("/{slot_id}/cancel", status_code=200)
async def cancel_booking(
    slot_id: int,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Cancel a slot booking.
    """
    result = await db.execute(
        select(SubmissionSlot).where(SubmissionSlot.id == slot_id)
    )
    slot = result.scalar_one_or_none()
    
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    
    if slot.status != SlotStatus.BOOKED:
        raise HTTPException(status_code=400, detail="Slot is not booked")
    
    # Check permissions
    if current_user.role == UserRole.STUDENT:
        # Must be booked by their team
        team_result = await db.execute(
            select(Team).where(Team.id == slot.booked_by_team_id)
        )
        team = team_result.scalar_one_or_none()
        if not team or current_user.id not in [m.id for m in team.members]:
            raise HTTPException(status_code=403, detail="You can only cancel your own team's booking")
    elif current_user.role in [UserRole.ADMIN, UserRole.FACULTY]:
        if current_user.institution_id != slot.institution_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    old_team_id = slot.booked_by_team_id
    
    # Cancel
    slot.status = SlotStatus.AVAILABLE
    slot.booked_by_team_id = None
    slot.booked_at = None
    slot.petitioner_team_id = None
    slot.respondent_team_id = None
    
    # Create log
    log = SlotBookingLog(
        slot_id=slot_id,
        action="cancel",
        performed_by=current_user.id,
        old_value=f"team_id: {old_team_id}",
        reason=reason
    )
    db.add(log)
    
    await db.commit()
    
    return {
        "success": True,
        "message": "Booking cancelled successfully"
    }


@router.get("", status_code=200)
async def list_slots(
    competition_id: int = Query(...),
    status: Optional[SlotStatus] = Query(None),
    team_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all slots for a competition.
    """
    # Verify competition access
    comp_result = await db.execute(
        select(Competition).where(Competition.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != competition.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build query
    query = select(SubmissionSlot).where(SubmissionSlot.competition_id == competition_id)
    
    if status:
        query = query.where(SubmissionSlot.status == status)
    
    if team_id:
        query = query.where(SubmissionSlot.booked_by_team_id == team_id)
    
    query = query.order_by(asc(SubmissionSlot.start_time))
    
    result = await db.execute(query)
    slots = result.scalars().all()
    
    return {
        "success": True,
        "competition_id": competition_id,
        "slots": [s.to_dict() for s in slots],
        "count": len(slots)
    }
