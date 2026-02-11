"""
backend/routes/oral_round_transcripts.py
Phase 3.3: Transcript management API for oral rounds
Isolated from existing routes - NEW FILE
3 endpoints: create, list, export
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, asc
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.orm.oral_round_transcript import OralRoundTranscript, TranscriptEntryType, TranscriptSource, TranscriptSegment
from backend.orm.oral_round import OralRound
from backend.orm.user import User, UserRole
from backend.routes.auth import get_current_user

router = APIRouter(prefix="/oral-rounds", tags=["oral-round-transcripts"])


# ================= SCHEMAS =================

class TranscriptCreate(BaseModel):
    """Request to create transcript entry"""
    content: str = Field(..., min_length=1, description="The spoken text")
    entry_type: TranscriptEntryType = Field(default=TranscriptEntryType.STATEMENT)
    round_stage: Optional[str] = Field(None, description="Current round stage")
    team_side: Optional[str] = Field(None, pattern="^(petitioner|respondent)$")
    speaker_role: Optional[str] = Field(None, description="Speaker's role")
    source: TranscriptSource = Field(default=TranscriptSource.MANUAL_ENTRY)


class TranscriptResponse(BaseModel):
    """Transcript entry response"""
    id: int
    round_id: int
    speaker_id: int
    speaker_name: str
    entry_type: str
    content: str
    round_stage: Optional[str]
    team_side: Optional[str]
    speaker_role: Optional[str]
    source: str
    confidence_score: Optional[float]
    objection_id: Optional[int]
    sequence_number: int
    timestamp: str
    created_at: str
    
    class Config:
        from_attributes = True


class TranscriptExport(BaseModel):
    """Full transcript export"""
    round_id: int
    entries: List[TranscriptResponse]
    total_entries: int
    generated_at: str


# ================= HELPERS =================

async def _get_next_sequence(round_id: int, db: AsyncSession) -> int:
    """Get next sequence number for transcript entries"""
    result = await db.execute(
        select(OralRoundTranscript).where(
            OralRoundTranscript.round_id == round_id
        ).order_by(desc(OralRoundTranscript.sequence_number))
    )
    last_entry = result.scalar_one_or_none()
    return (last_entry.sequence_number + 1) if last_entry else 1


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

@router.post("/{round_id}/transcripts", response_model=TranscriptResponse)
async def create_transcript_entry(
    round_id: int,
    entry_data: TranscriptCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a transcript entry.
    Judges can create entries for anyone; speakers can create for themselves.
    """
    # Verify round exists
    await _get_round_or_404(round_id, db)
    
    # Determine speaker_id (judge can specify, otherwise uses current user)
    speaker_id = current_user.id
    
    # Get next sequence number
    sequence = await _get_next_sequence(round_id, db)
    
    # Create entry
    entry = OralRoundTranscript(
        round_id=round_id,
        speaker_id=speaker_id,
        entry_type=entry_data.entry_type,
        content=entry_data.content,
        round_stage=entry_data.round_stage,
        team_side=entry_data.team_side,
        speaker_role=entry_data.speaker_role,
        source=entry_data.source,
        sequence_number=sequence,
        timestamp=datetime.now(timezone.utc)
    )
    
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    
    return TranscriptResponse(
        id=entry.id,
        round_id=entry.round_id,
        speaker_id=entry.speaker_id,
        speaker_name=current_user.name,
        entry_type=entry.entry_type.value,
        content=entry.content,
        round_stage=entry.round_stage,
        team_side=entry.team_side.value if entry.team_side else None,
        speaker_role=entry.speaker_role,
        source=entry.source.value,
        confidence_score=entry.confidence_score,
        objection_id=entry.objection_id,
        sequence_number=entry.sequence_number,
        timestamp=entry.timestamp.isoformat() if entry.timestamp else None,
        created_at=entry.created_at.isoformat() if entry.created_at else None
    )


@router.get("/{round_id}/transcripts", response_model=List[TranscriptResponse])
async def list_transcripts(
    round_id: int,
    entry_type: Optional[str] = None,
    team_side: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List transcript entries for a round.
    Everyone can view transcripts.
    """
    # Verify round exists
    await _get_round_or_404(round_id, db)
    
    # Build query
    query = select(OralRoundTranscript).where(
        OralRoundTranscript.round_id == round_id
    ).order_by(asc(OralRoundTranscript.sequence_number))
    
    # Apply filters
    if entry_type:
        try:
            type_enum = TranscriptEntryType(entry_type)
            query = query.where(OralRoundTranscript.entry_type == type_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid entry type: {entry_type}"
            )
    
    if team_side:
        query = query.where(OralRoundTranscript.team_side == team_side)
    
    # Apply pagination
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    entries = result.scalars().all()
    
    return [
        TranscriptResponse(
            id=e.id,
            round_id=e.round_id,
            speaker_id=e.speaker_id,
            speaker_name=e.speaker.name if e.speaker else "Unknown",
            entry_type=e.entry_type.value,
            content=e.content,
            round_stage=e.round_stage,
            team_side=e.team_side.value if e.team_side else None,
            speaker_role=e.speaker_role,
            source=e.source.value,
            confidence_score=e.confidence_score,
            objection_id=e.objection_id,
            sequence_number=e.sequence_number,
            timestamp=e.timestamp.isoformat() if e.timestamp else None,
            created_at=e.created_at.isoformat() if e.created_at else None
        )
        for e in entries
    ]


@router.get("/{round_id}/transcripts/export", response_model=TranscriptExport)
async def export_transcript(
    round_id: int,
    format_type: str = "json",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Export full transcript for a round.
    Everyone can export transcripts.
    """
    # Verify round exists
    await _get_round_or_404(round_id, db)
    
    # Get all entries
    result = await db.execute(
        select(OralRoundTranscript).where(
            OralRoundTranscript.round_id == round_id
        ).order_by(asc(OralRoundTranscript.sequence_number))
    )
    entries = result.scalars().all()
    
    transcript_responses = [
        TranscriptResponse(
            id=e.id,
            round_id=e.round_id,
            speaker_id=e.speaker_id,
            speaker_name=e.speaker.name if e.speaker else "Unknown",
            entry_type=e.entry_type.value,
            content=e.content,
            round_stage=e.round_stage,
            team_side=e.team_side.value if e.team_side else None,
            speaker_role=e.speaker_role,
            source=e.source.value,
            confidence_score=e.confidence_score,
            objection_id=e.objection_id,
            sequence_number=e.sequence_number,
            timestamp=e.timestamp.isoformat() if e.timestamp else None,
            created_at=e.created_at.isoformat() if e.created_at else None
        )
        for e in entries
    ]
    
    return TranscriptExport(
        round_id=round_id,
        entries=transcript_responses,
        total_entries=len(entries),
        generated_at=datetime.now(timezone.utc).isoformat()
    )
