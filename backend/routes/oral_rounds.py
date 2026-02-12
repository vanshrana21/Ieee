"""
backend/routes/oral_rounds.py
Phase 5C: Oral round persistence API routes
Replaces client-side oral round storage
"""
import logging
import json
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from backend.database import get_db
from backend.orm.oral_round import OralRound, BenchQuestion, RoundTranscript, RoundStage, RoundStatus
from backend.orm.moot_project import MootProject
from backend.orm.user import User, UserRole
from backend.rbac import get_current_user

# Phase 6B: Permission guards
from backend.services.permission_guards import require_oral_response_permission

# Phase 6C: Activity logging
from backend.services.activity_logger import log_oral_response_submitted

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/oral-rounds", tags=["Oral Rounds"])


# ================= SCHEMAS =================

class OralRoundCreate(BaseModel):
    """Schema for creating an oral round"""
    project_id: int
    stage: str = Field(..., pattern="^(petitioner|respondent|rebuttal|surrebuttal)$")
    notes: Optional[str] = None


class OralResponseSubmit(BaseModel):
    """Schema for submitting an oral response"""
    round_id: int
    issue_id: Optional[int] = None
    speaker_role: str  # 'petitioner_counsel', 'respondent_counsel', etc.
    text: str
    elapsed_seconds: Optional[int] = None


class BenchQuestionSubmit(BaseModel):
    """Schema for submitting a bench question"""
    round_id: int
    judge_name: Optional[str] = None
    question_text: str
    issue_id: Optional[int] = None
    elapsed_seconds: Optional[int] = None


class RoundComplete(BaseModel):
    """Schema for completing a round"""
    round_id: int


# ================= ORAL ROUND CRUD =================

@router.post("", status_code=201)
async def create_round(
    data: OralRoundCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Start a new oral round session.
    """
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(
            and_(
                MootProject.id == data.project_id,
                MootProject.is_active == True
            )
        )
    )
    project = project_result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role == UserRole.STUDENT and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Create round
    round_session = OralRound(
        institution_id=project.institution_id,
        project_id=data.project_id,
        stage=RoundStage(data.stage),
        status=RoundStatus.IN_PROGRESS,
        started_at=datetime.utcnow(),
        notes=data.notes,
        created_by=current_user.id
    )
    
    db.add(round_session)
    await db.commit()
    await db.refresh(round_session)
    
    logger.info(f"Oral round started: {round_session.id} for project {data.project_id}")
    
    return {
        "success": True,
        "oral_round": round_session.to_dict()
    }


@router.get("", status_code=200)
async def list_rounds(
    project_id: int = Query(...),
    include_content: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: List oral rounds for a project.
    """
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(MootProject.id == project_id)
    )
    project = project_result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role == UserRole.STUDENT and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    result = await db.execute(
        select(OralRound).where(OralRound.project_id == project_id).order_by(desc(OralRound.created_at))
    )
    rounds = result.scalars().all()
    
    return {
        "success": True,
        "oral_rounds": [r.to_dict(include_content=include_content) for r in rounds],
        "count": len(rounds)
    }


@router.get("/{round_id}", status_code=200)
async def get_round(
    round_id: int,
    include_content: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Get oral round details with all content.
    """
    result = await db.execute(
        select(OralRound).where(OralRound.id == round_id)
    )
    round_session = result.scalar_one_or_none()
    
    if not round_session:
        raise HTTPException(status_code=404, detail="Oral round not found")
    
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(MootProject.id == round_session.project_id)
    )
    project = project_result.scalar_one_or_none()
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role == UserRole.STUDENT and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {
        "success": True,
        "oral_round": round_session.to_dict(include_content=include_content)
    }


@router.post("/{round_id}/complete", status_code=200)
async def complete_round(
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Complete an oral round and lock it.
    Immutable after completion.
    """
    result = await db.execute(
        select(OralRound).where(OralRound.id == round_id)
    )
    round_session = result.scalar_one_or_none()
    
    if not round_session:
        raise HTTPException(status_code=404, detail="Oral round not found")
    
    if round_session.is_locked:
        raise HTTPException(status_code=400, detail="Round is already locked")
    
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(MootProject.id == round_session.project_id)
    )
    project = project_result.scalar_one_or_none()
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Complete and lock
    round_session.status = RoundStatus.COMPLETED
    round_session.ended_at = datetime.utcnow()
    
    # Calculate duration
    if round_session.started_at:
        duration = (round_session.ended_at - round_session.started_at).total_seconds()
        round_session.duration_seconds = int(duration)
    
    # Lock
    round_session.is_locked = True
    round_session.locked_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(round_session)
    
    logger.info(f"Oral round completed and locked: {round_id}")
    
    return {
        "success": True,
        "oral_round": round_session.to_dict(),
        "message": "Round completed and locked. No further edits allowed."
    }


# ================= ORAL RESPONSES =================

@router.post("/{round_id}/responses", status_code=201)
async def submit_response(
    round_id: int,
    data: OralResponseSubmit,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Submit an oral response during a round.
    """
    result = await db.execute(
        select(OralRound).where(OralRound.id == round_id)
    )
    round_session = result.scalar_one_or_none()
    
    if not round_session:
        raise HTTPException(status_code=404, detail="Oral round not found")
    
    # Check if round is locked
    if round_session.is_locked:
        raise HTTPException(status_code=400, detail="Cannot add responses to a locked round")
    
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(MootProject.id == round_session.project_id)
    )
    project = project_result.scalar_one_or_none()
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Phase 6B: Check team permission for oral response (CAPTAIN, SPEAKER)
    await require_oral_response_permission(current_user, project, db)
    
    response = OralResponse(
        institution_id=round_session.institution_id,
        round_id=round_id,
        project_id=round_session.project_id,
        issue_id=data.issue_id,
        speaker_role=data.speaker_role,
        text=data.text,
        elapsed_seconds=data.elapsed_seconds,
        created_by=current_user.id
    )
    
    db.add(response)
    await db.commit()
    await db.refresh(response)
    
    # Phase 6C: Log oral response submission (high-level only)
    await log_oral_response_submitted(
        db=db,
        project=project,
        actor=current_user,
        round_id=round_id,
        speaker_role=data.speaker_role
    )
    
    return {
        "success": True,
        "response": response.to_dict()
    }


@router.get("/{round_id}/responses", status_code=200)
async def list_responses(
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: List all oral responses for a round.
    """
    result = await db.execute(
        select(OralRound).where(OralRound.id == round_id)
    )
    round_session = result.scalar_one_or_none()
    
    if not round_session:
        raise HTTPException(status_code=404, detail="Oral round not found")
    
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(MootProject.id == round_session.project_id)
    )
    project = project_result.scalar_one_or_none()
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role == UserRole.STUDENT and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    result = await db.execute(
        select(OralResponse).where(OralResponse.round_id == round_id).order_by(OralResponse.timestamp)
    )
    responses = result.scalars().all()
    
    return {
        "success": True,
        "responses": [r.to_dict() for r in responses],
        "count": len(responses)
    }


# ================= BENCH QUESTIONS =================

@router.post("/{round_id}/questions", status_code=201)
async def submit_question(
    round_id: int,
    data: BenchQuestionSubmit,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Submit a bench question during a round.
    """
    result = await db.execute(
        select(OralRound).where(OralRound.id == round_id)
    )
    round_session = result.scalar_one_or_none()
    
    if not round_session:
        raise HTTPException(status_code=404, detail="Oral round not found")
    
    # Check if round is locked
    if round_session.is_locked:
        raise HTTPException(status_code=400, detail="Cannot add questions to a locked round")
    
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(MootProject.id == round_session.project_id)
    )
    project = project_result.scalar_one_or_none()
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    question = BenchQuestion(
        institution_id=round_session.institution_id,
        round_id=round_id,
        project_id=round_session.project_id,
        judge_id=current_user.id if current_user.role in [UserRole.JUDGE, UserRole.FACULTY] else None,
        judge_name=data.judge_name or (current_user.full_name if hasattr(current_user, 'full_name') else None),
        question_text=data.question_text,
        issue_id=data.issue_id,
        elapsed_seconds=data.elapsed_seconds
    )
    
    db.add(question)
    await db.commit()
    await db.refresh(question)
    
    return {
        "success": True,
        "question": question.to_dict()
    }


@router.get("/{round_id}/questions", status_code=200)
async def list_questions(
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: List all bench questions for a round.
    """
    result = await db.execute(
        select(OralRound).where(OralRound.id == round_id)
    )
    round_session = result.scalar_one_or_none()
    
    if not round_session:
        raise HTTPException(status_code=404, detail="Oral round not found")
    
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(MootProject.id == round_session.project_id)
    )
    project = project_result.scalar_one_or_none()
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role == UserRole.STUDENT and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    result = await db.execute(
        select(BenchQuestion).where(BenchQuestion.round_id == round_id).order_by(BenchQuestion.timestamp)
    )
    questions = result.scalars().all()
    
    return {
        "success": True,
        "questions": [q.to_dict() for q in questions],
        "count": len(questions)
    }


# ================= TRANSCRIPT GENERATION =================

@router.post("/{round_id}/transcript", status_code=201)
async def generate_transcript(
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Generate immutable transcript from responses and questions.
    """
    result = await db.execute(
        select(OralRound).where(OralRound.id == round_id)
    )
    round_session = result.scalar_one_or_none()
    
    if not round_session:
        raise HTTPException(status_code=404, detail="Oral round not found")
    
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(MootProject.id == round_session.project_id)
    )
    project = project_result.scalar_one_or_none()
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all responses and questions
    responses_result = await db.execute(
        select(OralResponse).where(OralResponse.round_id == round_id)
    )
    responses = responses_result.scalars().all()
    
    questions_result = await db.execute(
        select(BenchQuestion).where(BenchQuestion.round_id == round_id)
    )
    questions = questions_result.scalars().all()
    
    # Combine and sort chronologically
    items = []
    
    for r in responses:
        items.append({
            "type": "response",
            "speaker": r.speaker_role,
            "text": r.text,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "elapsed_seconds": r.elapsed_seconds
        })
    
    for q in questions:
        items.append({
            "type": "question",
            "speaker": f"Judge ({q.judge_name or 'Unknown'})",
            "text": q.question_text,
            "timestamp": q.timestamp.isoformat() if q.timestamp else None,
            "elapsed_seconds": q.elapsed_seconds
        })
    
    # Sort by timestamp
    items.sort(key=lambda x: x["timestamp"] or "")
    
    # Build full text
    full_text_lines = []
    for item in items:
        if item["type"] == "response":
            full_text_lines.append(f"[{item['speaker']}]: {item['text']}")
        else:
            full_text_lines.append(f"[BENCH - {item['speaker']}]: {item['text']}")
    
    full_text = "\n\n".join(full_text_lines)
    
    # Check for existing transcript
    existing_result = await db.execute(
        select(RoundTranscript).where(RoundTranscript.round_id == round_id)
    )
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        # Update if not final
        if not existing.is_final:
            existing.transcript_items = json.dumps(items)
            existing.full_text = full_text
            existing.generated_at = datetime.utcnow()
            transcript = existing
        else:
            raise HTTPException(status_code=400, detail="Transcript is already finalized")
    else:
        # Create new
        transcript = RoundTranscript(
            institution_id=round_session.institution_id,
            round_id=round_id,
            project_id=round_session.project_id,
            transcript_items=json.dumps(items),
            full_text=full_text,
            generated_by=current_user.id,
            is_final=True
        )
        db.add(transcript)
    
    await db.commit()
    await db.refresh(transcript)
    
    logger.info(f"Transcript generated for round {round_id}")
    
    return {
        "success": True,
        "transcript": transcript.to_dict(),
        "item_count": len(items)
    }


@router.get("/{round_id}/transcript", status_code=200)
async def get_transcript(
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 5C: Get generated transcript for a round.
    """
    result = await db.execute(
        select(OralRound).where(OralRound.id == round_id)
    )
    round_session = result.scalar_one_or_none()
    
    if not round_session:
        raise HTTPException(status_code=404, detail="Oral round not found")
    
    # Verify project access
    project_result = await db.execute(
        select(MootProject).where(MootProject.id == round_session.project_id)
    )
    project = project_result.scalar_one_or_none()
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.institution_id != project.institution_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role == UserRole.STUDENT and project.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    transcript_result = await db.execute(
        select(RoundTranscript).where(RoundTranscript.round_id == round_id)
    )
    transcript = transcript_result.scalar_one_or_none()
    
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found. Generate it first.")
    
    return {
        "success": True,
        "transcript": transcript.to_dict()
    }
