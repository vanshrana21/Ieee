"""
backend/routes/ai_moot.py
Phase 3: AI Moot Court Practice Mode - API Routes

Solo practice endpoints with AI judge.
Sits ON TOP of existing competition backend (Phases 0-9).
"""
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func

from backend.database import get_db
from backend.rbac import get_current_user
from backend.orm.user import User, UserRole
from backend.orm.moot_project import MootProject
from backend.orm.ai_oral_session import AIOralSession, AIOralTurn
from backend.orm.team_activity import TeamActivityLog, ActionType, TargetType
from backend.schemas.ai_moot import (
    AISessionCreate, AISessionResponse, AITurnSubmit, 
    AITurnResponse, SessionDetailResponse, TurnDetail, ProblemListItem
)
from backend.services.ai_judge_service import AIJudgeEngine
from backend.services.validation_metrics import validation_metrics
from backend.knowledge_base import problems as kb_problems

logger = logging.getLogger(__name__)
ai_moot_router = APIRouter(prefix="/ai-moot", tags=["AI Moot"])

# Initialize AI Judge Engine
ai_judge = AIJudgeEngine()


@ai_moot_router.get("/problems", response_model=List[ProblemListItem])
async def list_validation_problems(
    current_user: User = Depends(get_current_user)
):
    """
    List 3 pre-loaded Indian moot problems for Phase 3 validation testing.
    
    Students select Problem 1, 2, or 3 during AI practice sessions.
    """
    problems = kb_problems.get_validation_problems()
    
    return [
        ProblemListItem(
            id=p["id"],
            title=p["title"],
            legal_issue=p["legal_issues"][0] if p["legal_issues"] else "Constitutional matter"
        )
        for p in problems
    ]


@ai_moot_router.post("/sessions", response_model=AISessionResponse, status_code=201)
async def create_session(
    session_create: AISessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new AI moot court practice session.
    
    - Validates problem exists
    - Creates AIOralSession ORM object
    - Logs to TeamActivityLog
    """
    # Validate problem exists
    problem = None
    problem_title = "Unknown Problem"
    problem_id = None
    
    logger.info(f"Creating AI session: problem_type={session_create.problem_type}, problem_id={session_create.problem_id}, side={session_create.side}")
    
    # Check if using pre-loaded validation problem
    if session_create.problem_type and session_create.problem_type.startswith("validation_"):
        logger.info(f"Using validation problem: {session_create.problem_type}")
        try:
            # Map validation_1, validation_2, validation_3 to problem IDs 1, 2, 3
            validation_id = int(session_create.problem_type.split("_")[1])
            kb_problem = kb_problems.get_problem_by_id(validation_id)
            if kb_problem:
                problem_title = kb_problem["title"]
                problem_id = validation_id
                logger.info(f"Validation problem loaded: ID={problem_id}, title={problem_title}")
            else:
                logger.error(f"Validation problem {validation_id} not found in knowledge base")
                raise HTTPException(status_code=404, detail=f"Validation problem {validation_id} not found")
        except Exception as e:
            logger.error(f"Error loading validation problem: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error loading validation problem: {str(e)}")
    elif session_create.problem_id:
        # Use custom MootProject from database
        logger.info(f"Using database MootProject: ID={session_create.problem_id}")
        try:
            result = await db.execute(
                select(MootProject).where(MootProject.id == session_create.problem_id)
            )
            problem = result.scalar_one_or_none()
            if not problem:
                logger.error(f"MootProject with ID={session_create.problem_id} not found")
                raise HTTPException(status_code=404, detail="MootProject not found")
            problem_title = problem.title
            problem_id = session_create.problem_id
            logger.info(f"Database problem loaded: ID={problem_id}, title={problem_title}")
        except Exception as e:
            logger.error(f"Error loading MootProject: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error loading problem: {str(e)}")
    else:
        logger.error("Neither problem_type nor problem_id provided")
        raise HTTPException(status_code=400, detail="Either problem_type or problem_id must be provided")
    
    # Create AI oral session
    session = AIOralSession(
        user_id=current_user.id,
        problem_id=problem_id,
        side=session_create.side,
        created_at=datetime.utcnow(),
        completed_at=None
    )
    
    db.add(session)
    await db.commit()
    await db.refresh(session)
    
    # Log activity using Phase 6C logging
    log_entry = TeamActivityLog(
        institution_id=current_user.institution_id,
        team_id=None,  # Solo practice, no team
        project_id=None,
        actor_id=current_user.id,
        actor_role_at_time=current_user.role.value if current_user.role else "unknown",
        action_type=ActionType.AI_USAGE_ALLOWED,  # Phase 8 action type for AI usage
        target_type=TargetType.ORAL_ROUND,
        target_id=session.id,
        target_name=f"AI Moot Session for {problem_title}",
        context={
            "ai_moot_session_id": str(session.id),
            "problem_id": str(problem_id),
            "side": session_create.side,
            "problem_title": problem_title,
            "problem_type": session_create.problem_type
        },
        timestamp=datetime.utcnow()
    )
    db.add(log_entry)
    await db.commit()
    
    logger.info(f"AI moot session created: {session.id} for user {current_user.id}")
    
    return AISessionResponse(
        id=session.id,
        problem_title=problem_title,
        side=session.side,
        current_turn=1
    )


@ai_moot_router.post("/sessions/{session_id}/turns", response_model=AITurnResponse)
async def submit_turn(
    session_id: int,  # AIOralSession uses Integer primary key
    turn_submit: AITurnSubmit,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit a turn argument and get AI judge feedback.
    
    - Validates session belongs to current user
    - Rejects if session already has 3 turns
    - Calls AIJudgeEngine for feedback
    - Creates AIOralTurn with scores
    - Logs to TeamActivityLog
    """
    # Verify session exists and belongs to user
    result = await db.execute(
        select(AIOralSession).where(
            and_(
                AIOralSession.id == session_id,
                AIOralSession.user_id == current_user.id
            )
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Check if session is already complete
    if session.completed_at:
        raise HTTPException(status_code=400, detail="Session already completed")
    
    # Count existing turns
    turn_count_result = await db.execute(
        select(func.count(AIOralTurn.id)).where(AIOralTurn.session_id == session_id)
    )
    existing_turns = turn_count_result.scalar()
    
    if existing_turns >= 3:
        raise HTTPException(status_code=400, detail="Maximum 3 turns allowed per session")
    
    turn_number = existing_turns + 1
    
    # Get problem for context
    problem = None
    kb_problem = None
    
    # Check if using validation problem (IDs 1-3 are validation problems)
    if session.problem_id in [1, 2, 3]:
        kb_problem = kb_problems.get_problem_by_id(session.problem_id)
        problem_title = kb_problem["title"] if kb_problem else "Unknown Problem"
        legal_issue = kb_problem["legal_issues"][0] if kb_problem and kb_problem["legal_issues"] else "Constitutional matter"
    else:
        # Use custom MootProject
        problem_result = await db.execute(
            select(MootProject).where(MootProject.id == session.problem_id)
        )
        problem = problem_result.scalar_one_or_none()
        problem_title = problem.title if problem else "Unknown Problem"
        legal_issue = "Constitutional matter"
    
    problem_context = {
        "title": problem_title,
        "side": session.side,
        "legal_issue": legal_issue
    }
    
    # Generate AI feedback
    feedback_result = ai_judge.generate_feedback(
        argument=turn_submit.argument,
        problem_context=problem_context,
        turn_number=turn_number
    )
    
    # Create turn record
    turn = AIOralTurn(
        session_id=session_id,
        turn_number=turn_number,
        user_argument=turn_submit.argument,
        ai_feedback=feedback_result["feedback_text"],
        legal_accuracy_score=feedback_result["scores"]["legal_accuracy"],
        citation_score=feedback_result["scores"]["citation"],
        etiquette_score=feedback_result["scores"]["etiquette"],
        created_at=datetime.utcnow()
    )
    
    db.add(turn)
    
    # Mark session complete if this was turn 3
    session_complete = turn_number == 3
    if session_complete:
        session.completed_at = datetime.utcnow()
        db.add(session)
    
    # Log activity
    log_entry = TeamActivityLog(
        institution_id=current_user.institution_id,
        team_id=None,
        project_id=None,
        actor_id=current_user.id,
        actor_role_at_time=current_user.role.value if current_user.role else "unknown",
        action_type=ActionType.AI_USAGE_ALLOWED,
        target_type=TargetType.ORAL_ROUND,
        target_id=turn.id,
        target_name=f"AI Turn {turn_number}",
        context={
            "ai_moot_session_id": str(session_id),
            "turn_number": turn_number,
            "scores": feedback_result["scores"],
            "missing_cases": feedback_result["missing_cases"],
            "citation_valid": feedback_result["citation_valid"],
            "has_etiquette": feedback_result["has_etiquette"]
        },
        timestamp=datetime.utcnow()
    )
    db.add(log_entry)
    
    await db.commit()
    await db.refresh(turn)
    
    # Track validation metrics
    validation_metrics.track_session_completion(
        session_id=str(session_id),
        turns_completed=turn_number,
        max_turns=3
    )
    
    logger.info(f"AI moot turn {turn_number} completed for session {session_id}")
    
    return AITurnResponse(
        feedback=feedback_result["feedback_text"],
        score_breakdown=feedback_result["scores"],
        next_question=feedback_result["next_question"],
        session_complete=session_complete
    )


@ai_moot_router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: int,  # AIOralSession uses Integer primary key
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get full session details including all turns.
    
    Used for debrief screen after practice session.
    """
    # Verify session exists and belongs to user
    result = await db.execute(
        select(AIOralSession).where(
            and_(
                AIOralSession.id == session_id,
                AIOralSession.user_id == current_user.id
            )
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get problem for context (handle validation problems)
    kb_problem = None
    problem_title = "Unknown Problem"
    
    if session.problem_id in [1, 2, 3]:
        kb_problem = kb_problems.get_problem_by_id(session.problem_id)
        problem_title = kb_problem["title"] if kb_problem else "Unknown Problem"
    else:
        problem_result = await db.execute(
            select(MootProject).where(MootProject.id == session.problem_id)
        )
        problem = problem_result.scalar_one_or_none()
        problem_title = problem.title if problem else "Unknown Problem"
    
    # Get all turns
    turns_result = await db.execute(
        select(AIOralTurn)
        .where(AIOralTurn.session_id == session_id)
        .order_by(AIOralTurn.turn_number)
    )
    turns = turns_result.scalars().all()
    
    # Build turn details
    turn_details = []
    total_score = 0
    
    for turn in turns:
        turn_score = (
            turn.legal_accuracy_score + 
            turn.citation_score + 
            turn.etiquette_score
        )
        total_score += turn_score
        
        turn_details.append(TurnDetail(
            turn_number=turn.turn_number,
            user_argument=turn.user_argument,
            ai_feedback=turn.ai_feedback,
            legal_accuracy_score=turn.legal_accuracy_score,
            citation_score=turn.citation_score,
            etiquette_score=turn.etiquette_score,
            created_at=turn.created_at.isoformat() if turn.created_at else ""
        ))
    
    # Calculate average if completed
    avg_score = None
    if session.completed_at and turn_details:
        avg_score = round(total_score / len(turn_details), 2)
    
    return SessionDetailResponse(
        id=session.id,
        problem_title=problem_title,
        side=session.side,
        created_at=session.created_at.isoformat() if session.created_at else "",
        completed_at=session.completed_at.isoformat() if session.completed_at else None,
        turns=turn_details,
        total_score=avg_score
    )
