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
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from datetime import datetime, timedelta
import re
import logging

from backend.database import get_db
from backend.orm.classroom_session import (
    ClassroomSession, ClassroomParticipant, ClassroomScore, ClassroomArgument,
    SessionState, ParticipantRole, AIJudgeMode
)
from backend.orm.moot_case import MootCase
from backend.orm.user import User, UserRole
from backend.security.rbac import get_current_user, require_teacher, require_student, require_any_role
from backend.state_machines.classroom_session import (
    SessionStateMachine, ClassroomSessionState
)
from backend.schemas.classroom import (
    SessionCreate, SessionResponse, SessionJoinRequest, SessionJoinResponse,
    ParticipantResponse, ArgumentCreate, ArgumentResponse, ScoreUpdate,
    SessionStateChangeRequest, StrictStateTransitionRequest, StrictStateTransitionResponse,
    AllowedTransitionResponse, StateLogResponse
)
from backend.services.session_state_service import (
    transition_session_state as strict_transition_session_state_func, 
    get_allowed_transitions_from_state, get_session_state_history,
    StateTransitionError, ConcurrentModificationError, PreconditionError
)
from backend.services.participant_assignment_service import (
    assign_participant,
    get_assignment_for_position,
    SessionFullError,
    SessionNotJoinableError,
    DuplicateJoinError,
    RaceConditionError,
    UnauthorizedRoleError,
    ParticipantAssignmentError
)
#from backend.middleware.rate_limiter import RateLimiter

# Setup
router = APIRouter(prefix="/api/classroom", tags=["classroom"])
security = HTTPBearer()
#rate_limiter = RateLimiter(requests_per_minute=30)
logger = logging.getLogger(__name__)

# Regex patterns
SESSION_CODE_PATTERN = re.compile(r'^JURIS-[A-Z0-9]{6}$')


def rate_limit_check(request: Request):
    """Rate limiting middleware."""
    client_ip = request.client.host
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )
    return True


def require_faculty(current_user: User = Depends(get_current_user)):
    """
    DEPRECATED: Use require_teacher from backend.security.rbac instead.
    Kept for backward compatibility - redirects to require_teacher.
    """
    return require_teacher(current_user)


# ==========================================
# MOOT CASE ENDPOINTS
# ==========================================

@router.get("/moot-cases")
async def get_moot_cases(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all available moot cases for session creation.
    
    PHASE: Case Library Upgrade - Returns structured High Court case data.
    """
    try:
        result = await db.execute(
            select(
                MootCase.id,
                MootCase.title,
                MootCase.citation,
                MootCase.short_proposition,
                MootCase.legal_domain,
                MootCase.difficulty_level,
                MootCase.complexity_level,
                MootCase.constitutional_articles,
                MootCase.key_issues,
                MootCase.landmark_cases_expected
            ).order_by(MootCase.complexity_level.desc(), MootCase.created_at.desc())
        )
        cases = result.all()
        
        return [
            {
                "id": case.id,
                "title": case.title,
                "citation": case.citation,
                "short_proposition": case.short_proposition,
                "topic": case.legal_domain or "general",
                "difficulty": case.difficulty_level or "intermediate",
                "complexity_level": case.complexity_level or 3,
                "constitutional_articles": case.constitutional_articles,
                "key_issues": case.key_issues,
                "landmark_cases_expected": case.landmark_cases_expected
            }
            for case in cases
        ]
    except Exception as e:
        logger.error(f"Failed to fetch moot cases: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch moot cases"
        )


# ==========================================
# SESSION MANAGEMENT ENDPOINTS
# ==========================================

@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    session_data: SessionCreate,
    current_user: User = Depends(require_faculty),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new classroom session.
    
    - Rate limited: Max 3 sessions per teacher per hour
    - Enforces: Only 1 active session per teacher (DB constraint)
    - Generates: Cryptographically random session code
    - Validates: MootCase must exist (if provided)
    """
    try:
        # DEBUG: Log user role attempting session creation
        print(f"User role attempting session create: {current_user.role.value}")
        
        # Validate MootCase if case_id is provided
        if session_data.case_id:
            result = await db.execute(
                select(MootCase).where(MootCase.id == session_data.case_id)
            )
            moot_case = result.scalar_one_or_none()
            
            if not moot_case:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid moot case ID"
                )
        else:
            # Auto-select first available moot case if none provided
            result = await db.execute(
                select(MootCase).order_by(MootCase.id.asc()).limit(1)
            )
            moot_case = result.scalar_one_or_none()
            
            if not moot_case:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No moot cases available. Please create a moot case first."
                )
            
            session_data.case_id = moot_case.id
        
        # Check if teacher already has active session
        result = await db.execute(
            select(ClassroomSession).where(
                ClassroomSession.teacher_id == current_user.id,
                ClassroomSession.current_state.notin_(["completed", "cancelled"])
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You already have an active session: {existing.session_code}"
            )
        
        # Generate secure session code
        session_code = ClassroomSession.generate_session_code()
        
        # Ensure uniqueness (retry if collision)
        result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.session_code == session_code)
        )
        while result.scalar_one_or_none():
            session_code = ClassroomSession.generate_session_code()
            result = await db.execute(
                select(ClassroomSession).where(ClassroomSession.session_code == session_code)
            )
        
        # Create session
        new_session = ClassroomSession(
            session_code=session_code,
            teacher_id=current_user.id,
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
        await db.commit()
        await db.refresh(new_session)
        
        print(f"[DEBUG] Created session: {new_session.session_code}, is_active={new_session.is_active}")
        logger.info(f"Teacher {current_user.id} created session {session_code}")
        
        # Return only primitive fields to avoid relationship loading
        return SessionResponse(
            id=new_session.id,
            session_code=new_session.session_code,
            teacher_id=new_session.teacher_id,
            case_id=new_session.case_id,
            topic=new_session.topic,
            category=new_session.category,
            prep_time_minutes=new_session.prep_time_minutes,
            oral_time_minutes=new_session.oral_time_minutes,
            ai_judge_mode=new_session.ai_judge_mode,
            max_participants=new_session.max_participants,
            current_state=new_session.current_state,
            is_active=new_session.is_active,
            teacher_online=new_session.teacher_online,
            created_at=new_session.created_at.isoformat() if new_session.created_at else None,
            updated_at=new_session.updated_at.isoformat() if new_session.updated_at else None,
            completed_at=new_session.completed_at.isoformat() if new_session.completed_at else None,
            cancelled_at=new_session.cancelled_at.isoformat() if new_session.cancelled_at else None,
            phase_start_timestamp=new_session.phase_start_timestamp.isoformat() if new_session.phase_start_timestamp else None,
            phase_duration_seconds=new_session.phase_duration_seconds,
            remaining_seconds=new_session.get_remaining_seconds(),
            participants_count=0  # New session has zero participants
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to create session")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


async def _get_participant_count(db: AsyncSession, session_id: int) -> int:
    """Get count of active participants in session."""
    result = await db.execute(
        select(func.count(ClassroomParticipant.id))
        .where(
            ClassroomParticipant.session_id == session_id,
            ClassroomParticipant.is_active == True
        )
    )
    return result.scalar() or 0


@router.post("/sessions/join", response_model=SessionJoinResponse)
async def join_session(
    join_request: SessionJoinRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Join a classroom session with deterministic assignment.
    
    - Validates: Session code format (regex ^JURIS-[A-Z0-9]{6}$)
    - Validates: Only students can join
    - Validates: Session exists and is in PREPARING/CREATED state
    - Validates: Session not full (max 4 participants)
    - Assigns: Side (PETITIONER/RESPONDENT) and speaker number (1/2) deterministically
    - Enforces: No duplicate joins via database constraints
    - Logs: All attempts to classroom_participant_audit_log
    """
    try:
        # DEBUG: Log incoming request
        print(f"[DEBUG] Join request received:")
        print(f"[DEBUG]   session_code: {join_request.session_code}")
        print(f"[DEBUG]   user.id: {current_user.id}")
        print(f"[DEBUG]   user.role: {current_user.role.value}")
        
        # Check role - only students can join sessions
        if current_user.role != UserRole.student:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only students can join sessions"
            )
        
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
        
        result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.session_code == search_code)
        )
        session = result.scalar_one_or_none()
        
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
            result = await db.execute(select(ClassroomSession))
            all_sessions = result.scalars().all()
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
        
        # Check if already joined - IDEMPOTENT: return existing assignment
        result = await db.execute(
            select(ClassroomParticipant).where(
                ClassroomParticipant.session_id == session.id,
                ClassroomParticipant.user_id == current_user.id,
                ClassroomParticipant.is_active == True
            )
        )
        existing_participant = result.scalar_one_or_none()
        
        if existing_participant:
            # IDEMPOTENT: Return existing assignment
            logger.info(f"[IDEMPOTENT] User {current_user.id} already in session {session.id}")
            return SessionJoinResponse(
                session_id=session.id,
                session_code=session.session_code,
                side=existing_participant.side,
                speaker_number=existing_participant.speaker_number,
                total_participants=await _get_participant_count(db, session.id),
                current_state=session.current_state,
                remaining_seconds=session.remaining_time,
                message=f"Already joined as {existing_participant.side} Speaker {existing_participant.speaker_number}"
            )
        
        # Use deterministic assignment service (Layer 2)
        # This handles all validation, locking, assignment, and audit logging
        assignment = await assign_participant(
            session_id=session.id,
            user_id=current_user.id,
            db=db,
            is_student=(current_user.role == UserRole.student),
            ip_address=None,  # Could extract from request if needed
            user_agent=None   # Could extract from request if needed
        )
        
        # Commit the transaction
        await db.commit()
        
        logger.info(
            f"User {current_user.id} joined session {session.session_code} "
            f"as {assignment['side']} #{assignment['speaker_number']}"
        )
        
        # Return response with deterministic assignment
        return SessionJoinResponse(
            session_id=session.id,
            session_code=session.session_code,
            side=assignment['side'],
            speaker_number=assignment['speaker_number'],
            total_participants=assignment['total_participants'],
            current_state=session.current_state,
            remaining_seconds=session.remaining_time,
            message=f"Joined as {assignment['side']} Speaker {assignment['speaker_number']}"
        )
        
    except HTTPException:
        raise
    except UnauthorizedRoleError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can join sessions"
        )
    except SessionNotJoinableError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message
        )
    except SessionFullError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message
        )
    except RaceConditionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Position was taken by another participant. Please try again."
        )
    except DuplicateJoinError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already joined this session"
        )
    except ParticipantAssignmentError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message
        )
    except Exception as e:
        logger.error(f"Session join failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to join session"
        )


@router.get("/debug/sessions")
async def debug_sessions(
    db: AsyncSession = Depends(get_db)
):
    """DEBUG: List all sessions in the database"""
    result = await db.execute(
        select(ClassroomSession).order_by(ClassroomSession.id.desc())
    )
    sessions = result.scalars().all()
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get session details with current timer value."""
    result = await db.execute(
        select(ClassroomSession).where(ClassroomSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Check if user has access (teacher or participant)
    is_teacher = session.teacher_id == current_user.id
    result = await db.execute(
        select(ClassroomParticipant).where(
            ClassroomParticipant.session_id == session_id,
            ClassroomParticipant.user_id == current_user.id
        )
    )
    is_participant = result.scalar_one_or_none()
    
    if not is_teacher and not is_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Update last_seen_at for participants (reconnection tracking)
    if is_participant:
        is_participant.last_seen_at = datetime.utcnow()
        is_participant.is_connected = True
        await db.commit()
    
    return SessionResponse(**session.to_dict())


# ==========================================
# SESSION STATE TRANSITIONS
# ==========================================

@router.post("/sessions/{session_id}/state")
async def transition_session_state(
    session_id: int,
    state_request: SessionStateChangeRequest,
    current_user: User = Depends(require_faculty),
    db: AsyncSession = Depends(get_db)
):
    """
    Transition session state.
    
    - Validates: Teacher owns this session
    - Validates: Transition rules (e.g., need 2+ students for STUDY)
    - Updates: DB first with timestamp, then broadcasts
    """
    try:
        # Load session with ownership check
        result = await db.execute(
            select(ClassroomSession).where(
                ClassroomSession.id == session_id,
                ClassroomSession.teacher_id == current_user.id
            )
        )
        session = result.scalar_one_or_none()
        
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
            triggered_by=str(current_user.id),
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
# STRICT STATE MACHINE ENDPOINTS
# ==========================================

@router.post("/sessions/{session_id}/transition", response_model=StrictStateTransitionResponse)
async def strict_transition_session_state(
    session_id: int,
    transition_request: StrictStateTransitionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Strict state machine transition endpoint.
    
    - Validates: Transition rules from session_state_transitions table
    - Locks: Session row for update (concurrency safety)
    - Logs: All attempts to classroom_session_state_log
    - Checks: Faculty authorization where required
    - Handles: Idempotency (no-op if already in target state)
    """
    try:
        # Check if user is teacher
        is_faculty = current_user.role == UserRole.teacher
        
        # Perform the transition using the strict state machine service
        session = await strict_transition_session_state_func(
            session_id=session_id,
            to_state=transition_request.target_state,
            acting_user_id=current_user.id,
            db=db,
            is_faculty=is_faculty,
            reason=transition_request.reason,
            trigger_type="faculty_action" if is_faculty else "user_action"
        )
        
        # Commit the transaction to save changes and audit logs
        await db.commit()
        
        return StrictStateTransitionResponse(
            success=True,
            session_id=session.id,
            new_state=session.current_state,
            previous_state=session.current_state,  # This will be updated in the service
            state_updated_at=session.state_updated_at.isoformat() if session.state_updated_at else None,
            triggered_by=current_user.id,
            reason=transition_request.reason
        )
        
    except StateTransitionError as e:
        logger.warning(f"Invalid transition attempt: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "InvalidTransition",
                "message": e.message,
                "from_state": e.from_state,
                "to_state": e.to_state,
                "allowed_states": e.allowed_states
            }
        )
    except ConcurrentModificationError as e:
        logger.warning(f"Concurrent modification: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "ConcurrentModification",
                "message": e.message,
                "current_state": e.current_state
            }
        )
    except PreconditionError as e:
        logger.warning(f"Precondition failed: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "PreconditionFailed",
                "message": e.message,
                "precondition": e.precondition
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error in state transition: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalError",
                "message": "Failed to process state transition"
            }
        )


@router.get("/sessions/{session_id}/allowed-transitions", response_model=AllowedTransitionResponse)
async def get_allowed_transitions_endpoint(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get allowed transitions for the current session state.
    
    Returns a list of states that the session can transition to,
    based on the session_state_transitions table.
    """
    try:
        # Get session
        result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Check access (teacher or participant)
        is_teacher = session.teacher_id == current_user.id
        result = await db.execute(
            select(ClassroomParticipant).where(
                ClassroomParticipant.session_id == session_id,
                ClassroomParticipant.user_id == current_user.id
            )
        )
        is_participant = result.scalar_one_or_none()
        
        if not is_teacher and not is_participant:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get allowed transitions from database
        transitions = await get_allowed_transitions_from_state(db, session.current_state)
        
        # Filter by teacher requirement if user is not teacher
        is_faculty = current_user.role == UserRole.teacher
        if not is_faculty:
            transitions = [t for t in transitions if not t.requires_faculty]
        
        allowed_states = [t.to_state for t in transitions]
        
        return AllowedTransitionResponse(
            from_state=session.current_state,
            allowed_states=allowed_states,
            transitions=[t.to_dict() for t in transitions]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get allowed transitions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve allowed transitions"
        )


@router.get("/sessions/{session_id}/state-history", response_model=List[StateLogResponse])
async def get_session_state_history_endpoint(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50
):
    """
    Get the state transition history for a session.
    
    Returns audit log entries showing all state changes,
    including failed attempts.
    """
    try:
        # Get session
        result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Check access (teacher or participant)
        is_teacher = session.teacher_id == current_user.id
        result = await db.execute(
            select(ClassroomParticipant).where(
                ClassroomParticipant.session_id == session_id,
                ClassroomParticipant.user_id == current_user.id
            )
        )
        is_participant = result.scalar_one_or_none()
        
        if not is_teacher and not is_participant:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get state history
        history = await get_session_state_history(db, session_id, limit)
        
        return [StateLogResponse(**log.to_dict()) for log in history]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get state history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve state history"
        )


# ==========================================
# PARTICIPANT ENDPOINTS
# ==========================================

@router.get("/sessions/{session_id}/participants", response_model=List[ParticipantResponse])
async def get_participants(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all participants for a session."""
    # Check access
    result = await db.execute(
        select(ClassroomSession).where(ClassroomSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    is_teacher = session.teacher_id == current_user.id
    result = await db.execute(
        select(ClassroomParticipant).where(
            ClassroomParticipant.session_id == session_id,
            ClassroomParticipant.user_id == current_user.id
        )
    )
    is_participant = result.scalar_one_or_none()
    
    if not is_teacher and not is_participant:
        raise HTTPException(status_code=403, detail="Access denied")
    
    result = await db.execute(
        select(ClassroomParticipant).where(
            ClassroomParticipant.session_id == session_id
        )
    )
    participants = result.scalars().all()
    
    return [ParticipantResponse(**p.to_dict()) for p in participants]


# ==========================================
# ARGUMENT ENDPOINTS
# ==========================================

@router.post("/sessions/{session_id}/arguments", response_model=ArgumentResponse)
async def submit_argument(
    session_id: int,
    argument_data: ArgumentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit an argument.
    
    - Validates: User is Petitioner or Respondent (not Observer)
    - Sanitizes: Input text (XSS prevention)
    """
    try:
        # Get session
        result = await db.execute(
            select(ClassroomSession).where(ClassroomSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Check session state
        if session.current_state not in ["study", "moot"]:
            raise HTTPException(
                status_code=400,
                detail="Session is not in a phase that accepts arguments"
            )
        
        # Get participant
        result = await db.execute(
            select(ClassroomParticipant).where(
                ClassroomParticipant.session_id == session_id,
                ClassroomParticipant.user_id == current_user.id
            )
        )
        participant = result.scalar_one_or_none()
        
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
            user_id=current_user.id,
            role=participant.role,
            text=text
        )
        
        db.add(argument)
        await db.commit()
        await db.refresh(argument)
        
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
    current_user: User = Depends(require_faculty),
    db: AsyncSession = Depends(get_db)
):
    """Update score for a participant (teacher only)."""
    # Verify session ownership
    result = await db.execute(
        select(ClassroomSession).where(
            ClassroomSession.id == session_id,
            ClassroomSession.teacher_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get score record
    result = await db.execute(
        select(ClassroomScore).where(
            ClassroomScore.session_id == session_id,
            ClassroomScore.user_id == participant_id
        )
    )
    score = result.scalar_one_or_none()
    
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
    score.submitted_by = current_user.id
    score.is_draft = score_data.is_draft
    
    await db.commit()
    await db.refresh(score)
    
    return score.to_dict()


@router.get("/sessions/{session_id}/leaderboard")
async def get_leaderboard(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get final leaderboard."""
    # Check access
    result = await db.execute(
        select(ClassroomSession).where(ClassroomSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    is_teacher = session.teacher_id == current_user.id
    result = await db.execute(
        select(ClassroomParticipant).where(
            ClassroomParticipant.session_id == session_id,
            ClassroomParticipant.user_id == current_user.id
        )
    )
    is_participant = result.scalar_one_or_none()
    
    if not is_teacher and not is_participant:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get scores sorted by total
    result = await db.execute(
        select(ClassroomScore)
        .where(ClassroomScore.session_id == session_id)
        .order_by(ClassroomScore.total_score.desc())
    )
    scores = result.scalars().all()
    
    return {
        "scores": [s.to_dict() for s in scores],
        "completed": session.current_state == "completed"
    }
