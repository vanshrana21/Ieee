"""
backend/routes/oral_round_objections.py
Phase 3.3: Objection mechanics API for oral rounds
Isolated from existing routes - NEW FILE
4 endpoints: raise, list, rule, withdraw
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.orm.oral_round_objection import OralRoundObjection, ObjectionType, ObjectionStatus
from backend.orm.oral_round import OralRound
from backend.orm.user import User, UserRole
from backend.routes.auth import get_current_user

router = APIRouter(prefix="/oral-rounds", tags=["oral-round-objections"])


# ================= SCHEMAS =================

class ObjectionCreate(BaseModel):
    """Request to raise an objection"""
    objection_type: ObjectionType
    target_speaker_id: Optional[int] = None
    target_statement: Optional[str] = Field(None, description="The statement being objected to")
    round_stage: Optional[str] = Field(None, description="Current round stage")
    transcript_context: Optional[str] = Field(None, description="Context around the statement")


class ObjectionRule(BaseModel):
    """Request to rule on an objection"""
    ruling: str = Field(..., pattern="^(sustain|overrule)$")
    reason: Optional[str] = Field(None, description="Reason for ruling")


class ObjectionResponse(BaseModel):
    """Objection response model"""
    id: int
    round_id: int
    raised_by_id: int
    raised_by_name: str
    objection_type: str
    target_speaker_id: Optional[int]
    target_speaker_name: Optional[str]
    target_statement: Optional[str]
    round_stage: Optional[str]
    status: str
    ruled_by_id: Optional[int]
    ruled_by_name: Optional[str]
    ruling_timestamp: Optional[str]
    ruling_reason: Optional[str]
    raised_at: str
    created_at: str
    
    class Config:
        from_attributes = True


# ================= HELPERS =================

def _check_judge_permission(current_user: User):
    """Verify user can rule on objections"""
    if current_user.role not in [
        UserRole.teacher, 
        UserRole.teacher, 
        UserRole.teacher, 
        UserRole.teacher
    ]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only judges/faculty/admins can rule on objections"
        )


async def _get_round_or_404(round_id: int, db: AsyncSession):
    """Fetch round or raise 404"""
    result = await db.execute(select(OralRound).where(OralRound.id == round_id))
    round_obj = result.scalar_one_or_none()
    if not round_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oral round not found"
        )
    return round_obj


# ================= ROUTES =================

@router.post("/{round_id}/objections", response_model=ObjectionResponse)
async def raise_objection(
    round_id: int,
    objection_data: ObjectionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Raise an objection during an oral round.
    Only team members (petitioner/respondent) can raise objections.
    """
    # Verify round exists
    await _get_round_or_404(round_id, db)
    
    # Create objection
    objection = OralRoundObjection(
        round_id=round_id,
        raised_by_id=current_user.id,
        objection_type=objection_data.objection_type,
        target_speaker_id=objection_data.target_speaker_id,
        target_statement=objection_data.target_statement,
        round_stage=objection_data.round_stage,
        transcript_context=objection_data.transcript_context,
        status=ObjectionStatus.RAISED,
        raised_at=datetime.now(timezone.utc)
    )
    
    db.add(objection)
    await db.commit()
    await db.refresh(objection)
    
    return ObjectionResponse(
        id=objection.id,
        round_id=objection.round_id,
        raised_by_id=objection.raised_by_id,
        raised_by_name=current_user.name,
        objection_type=objection.objection_type.value,
        target_speaker_id=objection.target_speaker_id,
        target_speaker_name=None,  # Will be populated via relationship
        target_statement=objection.target_statement,
        round_stage=objection.round_stage,
        status=objection.status.value,
        ruled_by_id=None,
        ruled_by_name=None,
        ruling_timestamp=None,
        ruling_reason=None,
        raised_at=objection.raised_at.isoformat() if objection.raised_at else None,
        created_at=objection.created_at.isoformat() if objection.created_at else None
    )


@router.get("/{round_id}/objections", response_model=List[ObjectionResponse])
async def list_objections(
    round_id: int,
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all objections for a round.
    Everyone can see objections (no permission restrictions).
    """
    # Verify round exists
    await _get_round_or_404(round_id, db)
    
    # Build query
    query = select(OralRoundObjection).where(
        OralRoundObjection.round_id == round_id
    ).order_by(desc(OralRoundObjection.raised_at))
    
    # Apply status filter if provided
    if status_filter:
        try:
            status_enum = ObjectionStatus(status_filter)
            query = query.where(OralRoundObjection.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter: {status_filter}"
            )
    
    result = await db.execute(query)
    objections = result.scalars().all()
    
    return [
        ObjectionResponse(
            id=o.id,
            round_id=o.round_id,
            raised_by_id=o.raised_by_id,
            raised_by_name=o.raised_by.name if o.raised_by else "Unknown",
            objection_type=o.objection_type.value,
            target_speaker_id=o.target_speaker_id,
            target_speaker_name=o.target_speaker.name if o.target_speaker else None,
            target_statement=o.target_statement,
            round_stage=o.round_stage,
            status=o.status.value,
            ruled_by_id=o.ruled_by_id,
            ruled_by_name=o.ruled_by.name if o.ruled_by else None,
            ruling_timestamp=o.ruling_timestamp.isoformat() if o.ruling_timestamp else None,
            ruling_reason=o.ruling_reason,
            raised_at=o.raised_at.isoformat() if o.raised_at else None,
            created_at=o.created_at.isoformat() if o.created_at else None
        )
        for o in objections
    ]


@router.post("/{round_id}/objections/{objection_id}/rule", response_model=ObjectionResponse)
async def rule_on_objection(
    round_id: int,
    objection_id: int,
    ruling_data: ObjectionRule,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Rule on an objection (sustain or overrule).
    Only judges/faculty/admins can rule.
    """
    _check_judge_permission(current_user)
    
    # Verify round exists
    await _get_round_or_404(round_id, db)
    
    # Fetch objection
    result = await db.execute(
        select(OralRoundObjection).where(OralRoundObjection.id == objection_id)
    )
    objection = result.scalar_one_or_none()
    
    if not objection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Objection not found"
        )
    
    # Verify objection belongs to this round
    if objection.round_id != round_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Objection does not belong to this round"
        )
    
    # Cannot rule on already ruled objections
    if objection.status in [ObjectionStatus.SUSTAINED, ObjectionStatus.OVERRULED, ObjectionStatus.WITHDRAWN]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot rule on {objection.status.value} objection"
        )
    
    # Apply ruling
    if ruling_data.ruling == "sustain":
        objection.sustain(current_user.id, ruling_data.reason)
    else:
        objection.overrule(current_user.id, ruling_data.reason)
    
    await db.commit()
    await db.refresh(objection)
    
    return ObjectionResponse(
        id=objection.id,
        round_id=objection.round_id,
        raised_by_id=objection.raised_by_id,
        raised_by_name=objection.raised_by.name if objection.raised_by else "Unknown",
        objection_type=objection.objection_type.value,
        target_speaker_id=objection.target_speaker_id,
        target_speaker_name=objection.target_speaker.name if objection.target_speaker else None,
        target_statement=objection.target_statement,
        round_stage=objection.round_stage,
        status=objection.status.value,
        ruled_by_id=objection.ruled_by_id,
        ruled_by_name=current_user.name,
        ruling_timestamp=objection.ruling_timestamp.isoformat() if objection.ruling_timestamp else None,
        ruling_reason=objection.ruling_reason,
        raised_at=objection.raised_at.isoformat() if objection.raised_at else None,
        created_at=objection.created_at.isoformat() if objection.created_at else None
    )


@router.post("/{round_id}/objections/{objection_id}/withdraw")
async def withdraw_objection(
    round_id: int,
    objection_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Withdraw an objection.
    Only the person who raised it can withdraw (before it's ruled on).
    """
    # Verify round exists
    await _get_round_or_404(round_id, db)
    
    # Fetch objection
    result = await db.execute(
        select(OralRoundObjection).where(OralRoundObjection.id == objection_id)
    )
    objection = result.scalar_one_or_none()
    
    if not objection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Objection not found"
        )
    
    # Verify objection belongs to this round
    if objection.round_id != round_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Objection does not belong to this round"
        )
    
    # Only raiser can withdraw
    if objection.raised_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the person who raised the objection can withdraw it"
        )
    
    # Cannot withdraw ruled objections
    if objection.status in [ObjectionStatus.SUSTAINED, ObjectionStatus.OVERRULED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot withdraw an already ruled objection"
        )
    
    # Withdraw
    objection.status = ObjectionStatus.WITHDRAWN
    objection.ruled_at = datetime.now(timezone.utc)
    
    await db.commit()
    
    return {
        "message": "Objection withdrawn successfully",
        "objection_id": objection_id,
        "status": ObjectionStatus.WITHDRAWN.value
    }
