"""
Classroom Sessions API Routes

REST API endpoints for Classroom Mode (B2B).
"""
from fastapi import APIRouter, HTTPException, Depends, status, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from backend.database import get_db
from backend.orm.classroom_session import (
    ClassroomSession, ClassroomParticipant, ClassroomScore, ClassroomArgument,
    SessionState, SessionCategory
)
from backend.state_machines.classroom_session import SessionStateMachine


router = APIRouter(
    prefix="/api/classroom",
    tags=["classroom"]
)

# In-memory state machines (replace with Redis in production)
active_sessions: dict = {}


def get_current_user():
    """Get current user from auth token."""
    # TODO: Implement JWT auth
    return {"id": 1, "role": "teacher", "name": "Test Teacher"}


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    topic: str,
    category: SessionCategory = SessionCategory.CONSTITUTIONAL,
    prep_time_minutes: int = 30,
    oral_time_minutes: int = 45,
    ai_judge_enabled: bool = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create new classroom session.
    Only teachers/faculty can create sessions.
    """
    user_role = current_user.get("role")
    if user_role not in ["teacher", "faculty"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers or faculty can create sessions"
        )
    
    # Create session
    session = ClassroomSession(
        teacher_id=current_user["id"],
        topic=topic,
        category=category.value,
        prep_time_minutes=prep_time_minutes,
        oral_time_minutes=oral_time_minutes,
        ai_judge_enabled=ai_judge_enabled,
        current_state=SessionState.CREATED.value
    )
    
    db.add(session)
    db.commit()
    db.refresh(session)
    
    # Initialize state machine
    state_machine = SessionStateMachine(str(session.id))
    active_sessions[str(session.id)] = state_machine
    
    return {
        "success": True,
        "session": session.to_dict(),
        "join_url": f"/html/classroom-mode.html?session_id={session.id}"
    }


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get session details."""
    session = db.query(ClassroomSession).filter(ClassroomSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session": session.to_dict(),
        "participants": [p.to_dict() for p in session.participants],
        "scores": [s.to_dict() for s in session.scores]
    }


@router.post("/sessions/{session_id}/join")
async def join_session(
    session_id: int,
    session_code: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Join classroom session with code."""
    session = db.query(ClassroomSession).filter(
        ClassroomSession.id == session_id,
        ClassroomSession.session_code == session_code
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Invalid session code")
    
    # Check if already joined
    existing = db.query(ClassroomParticipant).filter(
        ClassroomParticipant.session_id == session_id,
        ClassroomParticipant.user_id == current_user["id"]
    ).first()
    
    if existing:
        return {"success": True, "message": "Already joined", "participant": existing.to_dict()}
    
    # Add participant
    participant = ClassroomParticipant(
        session_id=session_id,
        user_id=current_user["id"],
        role="observer"
    )
    
    db.add(participant)
    db.commit()
    db.refresh(participant)
    
    # Update state machine
    state_machine = active_sessions.get(str(session_id))
    if state_machine:
        state_machine.add_participant(str(current_user["id"]))
    
    return {
        "success": True,
        "participant": participant.to_dict()
    }


@router.post("/sessions/{session_id}/start")
async def start_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Start session (teacher only)."""
    session = db.query(ClassroomSession).filter(ClassroomSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.teacher_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Only session creator can start")
    
    state_machine = active_sessions.get(str(session_id))
    if not state_machine:
        raise HTTPException(status_code=400, detail="Session not initialized")
    
    # Transition to PREPARING
    result = await state_machine.transition_to(
        SessionStateMachine.TRANSITIONS[SessionState.CREATED][0],
        str(current_user["id"])
    )
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    
    # Update DB
    session.current_state = SessionState.PREPARING.value
    db.commit()
    
    return {
        "success": True,
        "state": session.current_state
    }


@router.post("/sessions/{session_id}/state")
async def update_session_state(
    session_id: int,
    new_state: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update session state (teacher only)."""
    session = db.query(ClassroomSession).filter(ClassroomSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.teacher_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Only session creator can change state")
    
    state_machine = active_sessions.get(str(session_id))
    if not state_machine:
        raise HTTPException(status_code=400, detail="Session not initialized")
    
    # Map state string to enum
    try:
        target_state = SessionState(new_state)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state")
    
    # Transition state
    result = await state_machine.transition_to(target_state, str(current_user["id"]))
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    
    # Update DB
    session.current_state = new_state
    db.commit()
    
    return {
        "success": True,
        "state": session.current_state,
        "transition": result
    }


@router.get("/sessions/{session_id}/participants")
async def get_participants(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get session participants."""
    session = db.query(ClassroomSession).filter(ClassroomSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "participants": [p.to_dict() for p in session.participants]
    }


@router.post("/sessions/{session_id}/scores")
async def submit_score(
    session_id: int,
    user_id: int,
    legal_reasoning: int,
    citation_format: int,
    courtroom_etiquette: int,
    responsiveness: int,
    time_management: int,
    feedback_text: Optional[str] = None,
    is_draft: bool = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Submit score for participant."""
    session = db.query(ClassroomSession).filter(ClassroomSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Validate scores (1-5)
    for score_name, score in [
        ("legal_reasoning", legal_reasoning),
        ("citation_format", citation_format),
        ("courtroom_etiquette", courtroom_etiquette),
        ("responsiveness", responsiveness),
        ("time_management", time_management)
    ]:
        if score < 1 or score > 5:
            raise HTTPException(status_code=400, detail=f"{score_name} must be 1-5")
    
    # Check if score exists
    existing = db.query(ClassroomScore).filter(
        ClassroomScore.session_id == session_id,
        ClassroomScore.user_id == user_id
    ).first()
    
    if existing:
        # Update existing
        existing.legal_reasoning = legal_reasoning
        existing.citation_format = citation_format
        existing.courtroom_etiquette = courtroom_etiquette
        existing.responsiveness = responsiveness
        existing.time_management = time_management
        existing.feedback_text = feedback_text
        existing.is_draft = is_draft
        existing.calculate_total()
    else:
        # Create new
        score = ClassroomScore(
            session_id=session_id,
            user_id=user_id,
            legal_reasoning=legal_reasoning,
            citation_format=citation_format,
            courtroom_etiquette=courtroom_etiquette,
            responsiveness=responsiveness,
            time_management=time_management,
            feedback_text=feedback_text,
            submitted_by=current_user["id"],
            is_draft=is_draft
        )
        score.calculate_total()
        db.add(score)
    
    db.commit()
    
    return {"success": True, "message": "Score submitted"}


@router.get("/sessions/{session_id}/leaderboard")
async def get_leaderboard(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get session leaderboard."""
    session = db.query(ClassroomSession).filter(ClassroomSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get scores sorted by total
    scores = db.query(ClassroomScore).filter(
        ClassroomScore.session_id == session_id
    ).order_by(ClassroomScore.total_score.desc()).all()
    
    leaderboard = []
    for rank, score in enumerate(scores, 1):
        user = db.query(ClassroomParticipant).filter(
            ClassroomParticipant.user_id == score.user_id
        ).first()
        
        leaderboard.append({
            "rank": rank,
            "user_id": score.user_id,
            "role": user.role if user else "unknown",
            "total_score": score.total_score,
            "legal_reasoning": score.legal_reasoning,
            "citation_format": score.citation_format,
            "courtroom_etiquette": score.courtroom_etiquette,
            "responsiveness": score.responsiveness,
            "time_management": score.time_management
        })
    
    return {"leaderboard": leaderboard}
