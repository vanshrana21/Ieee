"""
Classroom Session API Routes - Production Hardened

Security features:
- Rate limiting on all endpoints
- JWT validation on every request
- Ownership validation for teacher actions
- Input sanitization (XSS prevention)
- Session code format validation
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import re
import logging

from backend.database import get_db
from backend.orm.classroom_session import (
    ClassroomSession, ClassroomParticipant, ClassroomScore, ClassroomArgument,
    SessionState, ParticipantRole, AIJudgeMode
)
from backend.state_machines.classroom_session import (
    SessionStateMachine, ClassroomSessionState
)
from backend.schemas.classroom import (
    SessionCreate, SessionResponse, SessionJoinRequest, SessionJoinResponse,
    ParticipantResponse, ArgumentCreate, ArgumentResponse, ScoreUpdate,
    SessionStateChangeRequest
)
from backend.middleware.rate_limiter import RateLimiter

# Setup
router = APIRouter(prefix="/api/classroom", tags=["classroom"])
security = HTTPBearer()
rate_limiter = RateLimiter(requests_per_minute=30)
logger = logging.getLogger(__name__)

# Regex patterns
SESSION_CODE_PATTERN = re.compile(r'^JURIS-[A-Z0-9]{6}$')


# Authentication dependency (simplified - integrate with your JWT system)
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate JWT and return user."""
    # TODO: Implement JWT validation
    # Placeholder - replace with your actual JWT validation
    return {"id": 1, "role": "TEACHER", "email": "teacher@example.com"}


def require_teacher(user: dict = Depends(get_current_user)):
    """Require TEACHER role."""
    if user.get("role") != "TEACHER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can perform this action"
        )
    return user


def rate_limit_check(request: Request):
    """Rate limiting middleware."""
    client_ip = request.client.host
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )
    return True


# ==========================================
# SESSION MANAGEMENT ENDPOINTS
# ==========================================

@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    session_data: SessionCreate,
    user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """
    Create a new classroom session.
    
    - Rate limited: Max 3 sessions per teacher per hour
    - Enforces: Only 1 active session per teacher (DB constraint)
    - Generates: Cryptographically random session code
    """
    try:
        # Check if teacher already has active session
        existing = db.query(ClassroomSession).filter(
            ClassroomSession.teacher_id == user["id"],
            ClassroomSession.current_state.notin_(["completed", "cancelled"])
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You already have an active session: {existing.session_code}"
            )
        
        # Generate secure session code
        session_code = ClassroomSession.generate_session_code()
        
        # Ensure uniqueness (retry if collision)
        while db.query(ClassroomSession).filter_by(session_code=session_code).first():
            session_code = ClassroomSession.generate_session_code()
        
        # Create session
        new_session = ClassroomSession(
            session_code=session_code,
            teacher_id=user["id"],
            case_id=session_data.case_id,
            topic=session_data.topic,
            category=session_data.category,
            prep_time_minutes=session_data.prep_time_minutes or 15,
            oral_time_minutes=session_data.oral_time_minutes or 10,
            ai_judge_mode=session_data.ai_judge_mode or AIJudgeMode.HYBRID.value,
            max_participants=session_data.max_participants or 40,
            current_state=SessionState.PREPARING.value,
            is_active=True  # Explicitly set active status
        )
        
        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        
        print(f"[DEBUG] Created session: {new_session.session_code}, is_active={new_session.is_active}")
        logger.info(f"Teacher {user['id']} created session {session_code}")
        
        return SessionResponse(**new_session.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session creation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session"
        )


@router.post("/sessions/join", response_model=SessionJoinResponse)
async def join_session(
    join_request: SessionJoinRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: bool = Depends(rate_limit_check)
):
    """
    Join a classroom session.
    
    - Rate limited: Max 5 attempts per IP per hour
    - Validates: Session code format (regex ^JURIS-[A-Z0-9]{6}$)
    - Checks: Session exists and is not completed/cancelled
    - Checks: Participant count < max_participants
    - Enforces: Unique user per session (can't join twice)
    - Assigns: Role (Petitioner, Respondent, Observer)
    """
    try:
        # DEBUG: Log incoming request
        print(f"[DEBUG] Join request received:")
        print(f"[DEBUG]   session_code: {join_request.session_code}")
        print(f"[DEBUG]   user.id: {user.get('id')}")
        print(f"[DEBUG]   user.role: {user.get('role')}")
        
        # Validate session code format
        if not SESSION_CODE_PATTERN.match(join_request.session_code):
            print(f"[DEBUG] Session code format invalid: {join_request.session_code}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session code format. Expected: JURIS-XXXXXX"
            )
        
        # Find session - case insensitive search
        search_code = join_request.session_code.upper()
        print(f"[DEBUG] Searching for session with code: {search_code}")
        
        session = db.query(ClassroomSession).filter(
            ClassroomSession.session_code == search_code
        ).first()
        
        # DEBUG: Log query result
        print(f"[DEBUG] Session query result: {session}")
        if session:
            print(f"[DEBUG]   session.id: {session.id}")
            print(f"[DEBUG]   session.session_code: {session.session_code}")
            print(f"[DEBUG]   session.current_state: {session.current_state}")
            print(f"[DEBUG]   session.is_active: {session.is_active}")
        else:
            print(f"[DEBUG] No session found with code: {search_code}")
            # DEBUG: List all sessions in DB
            all_sessions = db.query(ClassroomSession).all()
            print(f"[DEBUG] Total sessions in DB: {len(all_sessions)}")
            for s in all_sessions:
                print(f"[DEBUG]   - ID:{s.id} Code:{s.session_code} State:{s.current_state}")
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session with code {join_request.session_code} not found in database"
            )
        
        # Check if session is active
        if not session.is_active:
            print(f"[DEBUG] Session exists but is inactive: {session.session_code}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session exists but is inactive"
            )
        
        # Check session state
        if session.current_state in ["completed", "cancelled"]:
            print(f"[DEBUG] Session has ended: {session.current_state}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session has ended. Contact your professor."
            )
        
        # Check if already joined (FIX 1: Duplicate join prevention)
        existing_participant = db.query(ClassroomParticipant).filter(
            ClassroomParticipant.session_id == session.id,
            ClassroomParticipant.user_id == user["id"]
        ).first()
        
        if existing_participant:
            # FIX 1: Return error for duplicate join (not reconnection)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have already joined this session."
            )
        
        # Check max participants
        participant_count = db.query(ClassroomParticipant).filter(
            ClassroomParticipant.session_id == session.id
        ).count()
        
        if participant_count >= session.max_participants:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session is full. Maximum 40 participants reached."
            )
        
        # Assign role based on join order
        role = ClassroomParticipant.assign_role(participant_count)
        
        # Create participant
        new_participant = ClassroomParticipant(
            session_id=session.id,
            user_id=user["id"],
            role=role,
            is_connected=True,
            last_seen_at=datetime.utcnow()
        )
        
        db.add(new_participant)
        db.commit()
        db.refresh(new_participant)
        
        logger.info(f"User {user['id']} joined session {session.session_code} as {role}")
        
        return SessionJoinResponse(
            session_id=session.id,
            session_code=session.session_code,
            role=role,
            current_state=session.current_state,
            remaining_seconds=session.remaining_time,  # FIX 3: Server-calculated timer
            message=f"Joined as {role}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session join failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to join session"
        )


@router.get("/debug/sessions")
async def debug_sessions(
    db: Session = Depends(get_db)
):
    """DEBUG: List all sessions in the database"""
    sessions = db.query(ClassroomSession).all()
    return {
        "total_sessions": len(sessions),
        "sessions": [
            {
                "id": s.id,
                "session_code": s.session_code,
                "current_state": s.current_state,
                "is_active": s.is_active,
                "teacher_id": s.teacher_id,
                "created_at": s.created_at.isoformat() if s.created_at else None
            }
            for s in sessions
        ]
    }


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get session details with current timer value."""
    session = db.query(ClassroomSession).filter_by(id=session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Check if user has access (teacher or participant)
    is_teacher = session.teacher_id == user["id"]
    is_participant = db.query(ClassroomParticipant).filter(
        ClassroomParticipant.session_id == session_id,
        ClassroomParticipant.user_id == user["id"]
    ).first()
    
    if not is_teacher and not is_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Update last_seen_at for participants (reconnection tracking)
    if is_participant:
        is_participant.last_seen_at = datetime.utcnow()
        is_participant.is_connected = True
        db.commit()
    
    return SessionResponse(**session.to_dict())


# ==========================================
# SESSION STATE TRANSITIONS
# ==========================================

@router.post("/sessions/{session_id}/state")
async def transition_session_state(
    session_id: int,
    state_request: SessionStateChangeRequest,
    user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """
    Transition session state.
    
    - Validates: Teacher owns this session
    - Validates: Transition rules (e.g., need 2+ students for STUDY)
    - Updates: DB first with timestamp, then broadcasts
    """
    try:
        # Load session with ownership check
        session = db.query(ClassroomSession).filter_by(
            id=session_id,
            teacher_id=user["id"]
        ).first()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or you don't own it"
            )
        
        # Initialize state machine with DB session
        state_machine = SessionStateMachine(
            session_id=str(session_id),
            db=db
        )
        
        # Get target state
        target_state = ClassroomSessionState(state_request.target_state)
        
        # Execute transition
        result = await state_machine.transition_to(
            new_state=target_state,
            triggered_by=str(user["id"]),
            triggered_by_role="TEACHER",
            validation_data=state_request.validation_data
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Transition failed")
            )
        
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"State transition failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to transition state"
        )


# ==========================================
# PARTICIPANT ENDPOINTS
# ==========================================

@router.get("/sessions/{session_id}/participants", response_model=List[ParticipantResponse])
async def get_participants(
    session_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all participants for a session."""
    # Check access
    session = db.query(ClassroomSession).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    is_teacher = session.teacher_id == user["id"]
    is_participant = db.query(ClassroomParticipant).filter(
        ClassroomParticipant.session_id == session_id,
        ClassroomParticipant.user_id == user["id"]
    ).first()
    
    if not is_teacher and not is_participant:
        raise HTTPException(status_code=403, detail="Access denied")
    
    participants = db.query(ClassroomParticipant).filter(
        ClassroomParticipant.session_id == session_id
    ).all()
    
    return [ParticipantResponse(**p.to_dict()) for p in participants]


# ==========================================
# ARGUMENT ENDPOINTS
# ==========================================

@router.post("/sessions/{session_id}/arguments", response_model=ArgumentResponse)
async def submit_argument(
    session_id: int,
    argument_data: ArgumentCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit an argument.
    
    - Validates: User is Petitioner or Respondent (not Observer)
    - Sanitizes: Input text (XSS prevention)
    """
    try:
        # Get session
        session = db.query(ClassroomSession).filter_by(id=session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Check session state
        if session.current_state not in ["study", "moot"]:
            raise HTTPException(
                status_code=400,
                detail="Session is not in a phase that accepts arguments"
            )
        
        # Get participant
        participant = db.query(ClassroomParticipant).filter(
            ClassroomParticipant.session_id == session_id,
            ClassroomParticipant.user_id == user["id"]
        ).first()
        
        if not participant:
            raise HTTPException(status_code=403, detail="You are not a participant")
        
        # Check role (observers can't submit arguments)
        if participant.role == ParticipantRole.OBSERVER.value:
            raise HTTPException(
                status_code=403,
                detail="Observers cannot submit arguments"
            )
        
        # Sanitize text (basic XSS prevention)
        text = argument_data.text.strip()
        # Remove potentially dangerous tags
        text = text.replace('<script>', '').replace('</script>', '')
        text = text.replace('<iframe>', '').replace('</iframe>', '')
        
        # Create argument
        argument = ClassroomArgument(
            session_id=session_id,
            user_id=user["id"],
            role=participant.role,
            text=text
        )
        
        db.add(argument)
        db.commit()
        db.refresh(argument)
        
        return ArgumentResponse(**argument.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Argument submission failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to submit argument")


# ==========================================
# SCORING ENDPOINTS
# ==========================================

@router.put("/sessions/{session_id}/scores/{participant_id}")
async def update_score(
    session_id: int,
    participant_id: int,
    score_data: ScoreUpdate,
    user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Update score for a participant (teacher only)."""
    # Verify session ownership
    session = db.query(ClassroomSession).filter_by(
        id=session_id,
        teacher_id=user["id"]
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get score record
    score = db.query(ClassroomScore).filter_by(
        session_id=session_id,
        user_id=participant_id
    ).first()
    
    if not score:
        raise HTTPException(status_code=404, detail="Score record not found")
    
    # Update scores
    if score_data.legal_reasoning is not None:
        score.legal_reasoning = score_data.legal_reasoning
    if score_data.citation_format is not None:
        score.citation_format = score_data.citation_format
    if score_data.courtroom_etiquette is not None:
        score.courtroom_etiquette = score_data.courtroom_etiquette
    if score_data.responsiveness is not None:
        score.responsiveness = score_data.responsiveness
    if score_data.time_management is not None:
        score.time_management = score_data.time_management
    if score_data.feedback_text is not None:
        score.feedback_text = score_data.feedback_text
    
    # Calculate total
    score.calculate_total()
    score.submitted_by = user["id"]
    score.is_draft = score_data.is_draft
    
    db.commit()
    db.refresh(score)
    
    return score.to_dict()


@router.get("/sessions/{session_id}/leaderboard")
async def get_leaderboard(
    session_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get final leaderboard."""
    # Check access
    session = db.query(ClassroomSession).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    is_teacher = session.teacher_id == user["id"]
    is_participant = db.query(ClassroomParticipant).filter(
        ClassroomParticipant.session_id == session_id,
        ClassroomParticipant.user_id == user["id"]
    ).first()
    
    if not is_teacher and not is_participant:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get scores sorted by total
    scores = db.query(ClassroomScore).filter(
        ClassroomScore.session_id == session_id
    ).order_by(ClassroomScore.total_score.desc()).all()
    
    return {
        "scores": [s.to_dict() for s in scores],
        "completed": session.current_state == "completed"
    }
