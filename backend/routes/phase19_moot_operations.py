"""
Phase 19 — Moot Courtroom Operations & Live Session Management API Routes.

Deterministic live session management with hash-chained audit logs.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.rbac import require_role, get_current_user
from backend.orm.user import UserRole
from backend.config.feature_flags import feature_flags

from backend.services.phase19_session_service import (
    SessionService, SessionError, SessionNotFoundError,
    InvalidSessionStatusError, SessionCompletedError
)
from backend.orm.phase19_moot_operations import (
    CourtroomSession, SessionParticipation, SessionObservation, SessionLogEntry,
    SessionStatus, ParticipantRole, ParticipantStatus
)


router = APIRouter(prefix="/api/session", tags=["moot-operations"])


# =============================================================================
# Pydantic Request/Response Models
# =============================================================================

class CreateSessionRequest(BaseModel):
    assignment_id: UUID
    metadata: Optional[Dict[str, Any]] = None


class ParticipantJoinRequest(BaseModel):
    role: ParticipantRole
    client_info: Optional[Dict[str, Any]] = None


class ObserverJoinRequest(BaseModel):
    client_info: Optional[Dict[str, Any]] = None


class LogEventRequest(BaseModel):
    event_type: str = Field(..., max_length=50)
    details: Dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    id: UUID
    assignment_id: UUID
    status: str
    started_at: Optional[str]
    ended_at: Optional[str]
    recording_url: Optional[str]
    metadata: Optional[Dict[str, Any]]
    integrity_hash: Optional[str]
    created_at: str


class ParticipationResponse(BaseModel):
    id: UUID
    session_id: UUID
    user_id: UUID
    role: str
    status: str
    joined_at: str
    left_at: Optional[str]
    connection_count: int
    client_info: Optional[Dict[str, Any]]
    created_at: str


class ObservationResponse(BaseModel):
    id: UUID
    session_id: UUID
    user_id: Optional[UUID]
    observed_at: str
    left_at: Optional[str]
    client_info: Optional[Dict[str, Any]]
    created_at: str


class LogEntryResponse(BaseModel):
    id: UUID
    session_id: UUID
    timestamp: str
    event_type: str
    actor_id: Optional[UUID]
    details: Dict[str, Any]
    hash_chain: str
    sequence_number: int
    created_at: str


class ReplayDeltaResponse(BaseModel):
    session_id: UUID
    start_sequence: int
    end_sequence: int
    logs: List[LogEntryResponse]
    is_complete: bool


class VerifyIntegrityResponse(BaseModel):
    session_id: UUID
    is_valid: bool
    invalid_sequences: List[int]
    message: str


# =============================================================================
# Feature Flag Check
# =============================================================================

def check_moot_operations_enabled():
    """Check if moot operations engine is enabled."""
    if not feature_flags.FEATURE_MOOT_OPERATIONS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Moot operations engine is disabled"
        )


# =============================================================================
# Session Management Routes
# =============================================================================

@router.post("/create", response_model=SessionResponse)
async def create_session(
    request: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.JUDGE]))
):
    """
    Create a new courtroom session.
    
    **Roles:** Admin, SuperAdmin, Judge
    """
    check_moot_operations_enabled()
    
    try:
        session = await SessionService.create_session(
            db=db,
            assignment_id=request.assignment_id,
            metadata=request.metadata
        )
        
        return SessionResponse(
            id=session.id,
            assignment_id=session.assignment_id,
            status=session.status,
            started_at=session.started_at.isoformat() if session.started_at else None,
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            recording_url=session.recording_url,
            metadata=session.metadata,
            integrity_hash=session.integrity_hash,
            created_at=session.created_at.isoformat() if session.created_at else ""
        )
    except SessionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get session details.
    
    **Roles:** Any authenticated user
    """
    check_moot_operations_enabled()
    
    session = await SessionService.get_session(db, session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    return SessionResponse(
        id=session.id,
        assignment_id=session.assignment_id,
        status=session.status,
        started_at=session.started_at.isoformat() if session.started_at else None,
        ended_at=session.ended_at.isoformat() if session.ended_at else None,
        recording_url=session.recording_url,
        metadata=session.metadata,
        integrity_hash=session.integrity_hash,
        created_at=session.created_at.isoformat() if session.created_at else ""
    )


@router.post("/{session_id}/start", response_model=SessionResponse)
async def start_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.JUDGE]))
):
    """
    Start a session (PENDING → ACTIVE).
    
    **Roles:** Admin, SuperAdmin, Judge
    """
    check_moot_operations_enabled()
    
    try:
        session, _ = await SessionService.start_session(
            db=db,
            session_id=session_id,
            started_by_user_id=current_user["id"]
        )
        
        return SessionResponse(
            id=session.id,
            assignment_id=session.assignment_id,
            status=session.status,
            started_at=session.started_at.isoformat() if session.started_at else None,
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            recording_url=session.recording_url,
            metadata=session.metadata,
            integrity_hash=session.integrity_hash,
            created_at=session.created_at.isoformat() if session.created_at else ""
        )
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    except (InvalidSessionStatusError, SessionCompletedError) as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.post("/{session_id}/pause", response_model=SessionResponse)
async def pause_session(
    session_id: UUID,
    reason: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.JUDGE]))
):
    """
    Pause a session (ACTIVE → PAUSED).
    
    **Roles:** Admin, SuperAdmin, Judge
    """
    check_moot_operations_enabled()
    
    try:
        session, _ = await SessionService.pause_session(
            db=db,
            session_id=session_id,
            paused_by_user_id=current_user["id"],
            reason=reason
        )
        
        return SessionResponse(
            id=session.id,
            assignment_id=session.assignment_id,
            status=session.status,
            started_at=session.started_at.isoformat() if session.started_at else None,
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            recording_url=session.recording_url,
            metadata=session.metadata,
            integrity_hash=session.integrity_hash,
            created_at=session.created_at.isoformat() if session.created_at else ""
        )
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    except (InvalidSessionStatusError, SessionCompletedError) as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.post("/{session_id}/resume", response_model=SessionResponse)
async def resume_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.JUDGE]))
):
    """
    Resume a paused session (PAUSED → ACTIVE).
    
    **Roles:** Admin, SuperAdmin, Judge
    """
    check_moot_operations_enabled()
    
    try:
        session, _ = await SessionService.resume_session(
            db=db,
            session_id=session_id,
            resumed_by_user_id=current_user["id"]
        )
        
        return SessionResponse(
            id=session.id,
            assignment_id=session.assignment_id,
            status=session.status,
            started_at=session.started_at.isoformat() if session.started_at else None,
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            recording_url=session.recording_url,
            metadata=session.metadata,
            integrity_hash=session.integrity_hash,
            created_at=session.created_at.isoformat() if session.created_at else ""
        )
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    except InvalidSessionStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.post("/{session_id}/complete", response_model=SessionResponse)
async def complete_session(
    session_id: UUID,
    recording_url: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.JUDGE]))
):
    """
    Complete a session and create integrity hash.
    
    **Roles:** Admin, SuperAdmin, Judge
    
    Once completed, session is immutable with hash verification.
    """
    check_moot_operations_enabled()
    
    try:
        session, integrity_hash = await SessionService.complete_session(
            db=db,
            session_id=session_id,
            completed_by_user_id=current_user["id"],
            recording_url=recording_url
        )
        
        return SessionResponse(
            id=session.id,
            assignment_id=session.assignment_id,
            status=session.status,
            started_at=session.started_at.isoformat() if session.started_at else None,
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            recording_url=session.recording_url,
            metadata=session.metadata,
            integrity_hash=session.integrity_hash,
            created_at=session.created_at.isoformat() if session.created_at else ""
        )
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    except (InvalidSessionStatusError, SessionCompletedError) as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


# =============================================================================
# Participant Routes
# =============================================================================

@router.post("/{session_id}/join", response_model=ParticipationResponse)
async def participant_join(
    session_id: UUID,
    request: ParticipantJoinRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Join a session as participant.
    
    **Roles:** Any authenticated user
    
    Roles: petitioner, respondent, judge, moderator
    """
    check_moot_operations_enabled()
    
    try:
        participation, _ = await SessionService.participant_join(
            db=db,
            session_id=session_id,
            user_id=current_user["id"],
            role=request.role,
            client_info=request.client_info
        )
        
        return ParticipationResponse(
            id=participation.id,
            session_id=participation.session_id,
            user_id=participation.user_id,
            role=participation.role,
            status=participation.status,
            joined_at=participation.joined_at.isoformat() if participation.joined_at else "",
            left_at=participation.left_at.isoformat() if participation.left_at else None,
            connection_count=participation.connection_count,
            client_info=participation.client_info,
            created_at=participation.created_at.isoformat() if participation.created_at else ""
        )
    except SessionCompletedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except SessionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{session_id}/leave", response_model=ParticipationResponse)
async def participant_leave(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Leave a session.
    
    **Roles:** Any authenticated user
    """
    check_moot_operations_enabled()
    
    try:
        participation, _ = await SessionService.participant_leave(
            db=db,
            session_id=session_id,
            user_id=current_user["id"]
        )
        
        return ParticipationResponse(
            id=participation.id,
            session_id=participation.session_id,
            user_id=participation.user_id,
            role=participation.role,
            status=participation.status,
            joined_at=participation.joined_at.isoformat() if participation.joined_at else "",
            left_at=participation.left_at.isoformat() if participation.left_at else None,
            connection_count=participation.connection_count,
            client_info=participation.client_info,
            created_at=participation.created_at.isoformat() if participation.created_at else ""
        )
    except SessionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{session_id}/participants", response_model=List[ParticipationResponse])
async def get_session_participants(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all participants in a session.
    
    **Roles:** Any authenticated user
    """
    check_moot_operations_enabled()
    
    participants = await SessionService.get_session_participants(db, session_id)
    
    return [
        ParticipationResponse(
            id=p.id,
            session_id=p.session_id,
            user_id=p.user_id,
            role=p.role,
            status=p.status,
            joined_at=p.joined_at.isoformat() if p.joined_at else "",
            left_at=p.left_at.isoformat() if p.left_at else None,
            connection_count=p.connection_count,
            client_info=p.client_info,
            created_at=p.created_at.isoformat() if p.created_at else ""
        )
        for p in participants
    ]


# =============================================================================
# Observer Routes
# =============================================================================

@router.post("/{session_id}/observe", response_model=ObservationResponse)
async def observer_join(
    session_id: UUID,
    request: ObserverJoinRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user)
):
    """
    Join a session as observer (audience).
    
    **Roles:** Any authenticated user (optional - allows anonymous)
    """
    check_moot_operations_enabled()
    
    user_id = current_user.get("id") if current_user else None
    
    observation = await SessionService.observer_join(
        db=db,
        session_id=session_id,
        user_id=user_id,
        client_info=request.client_info
    )
    
    return ObservationResponse(
        id=observation.id,
        session_id=observation.session_id,
        user_id=observation.user_id,
        observed_at=observation.observed_at.isoformat() if observation.observed_at else "",
        left_at=observation.left_at.isoformat() if observation.left_at else None,
        client_info=observation.client_info,
        created_at=observation.created_at.isoformat() if observation.created_at else ""
    )


# =============================================================================
# Log & Replay Routes
# =============================================================================

@router.post("/{session_id}/log", response_model=LogEntryResponse)
async def log_event(
    session_id: UUID,
    request: LogEventRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.JUDGE]))
):
    """
    Log a custom event in the session.
    
    **Roles:** Admin, SuperAdmin, Judge
    """
    check_moot_operations_enabled()
    
    log_entry = await SessionService.log_event(
        db=db,
        session_id=session_id,
        event_type=request.event_type,
        actor_id=current_user["id"],
        details=request.details
    )
    
    return LogEntryResponse(
        id=log_entry.id,
        session_id=log_entry.session_id,
        timestamp=log_entry.timestamp.isoformat() if log_entry.timestamp else "",
        event_type=log_entry.event_type,
        actor_id=log_entry.actor_id,
        details=log_entry.details,
        hash_chain=log_entry.hash_chain,
        sequence_number=log_entry.sequence_number,
        created_at=log_entry.created_at.isoformat() if log_entry.created_at else ""
    )


@router.get("/{session_id}/logs", response_model=List[LogEntryResponse])
async def get_session_logs(
    session_id: UUID,
    start_sequence: Optional[int] = Query(None, description="Start sequence for delta replay"),
    end_sequence: Optional[int] = Query(None, description="End sequence for delta replay"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get session logs with optional sequence range.
    
    **Roles:** Any authenticated user
    
    For replay: provide start_sequence to get delta.
    """
    check_moot_operations_enabled()
    
    logs = await SessionService.get_session_logs(
        db=db,
        session_id=session_id,
        start_sequence=start_sequence,
        end_sequence=end_sequence
    )
    
    return [
        LogEntryResponse(
            id=log.id,
            session_id=log.session_id,
            timestamp=log.timestamp.isoformat() if log.timestamp else "",
            event_type=log.event_type,
            actor_id=log.actor_id,
            details=log.details,
            hash_chain=log.hash_chain,
            sequence_number=log.sequence_number,
            created_at=log.created_at.isoformat() if log.created_at else ""
        )
        for log in logs
    ]


@router.get("/{session_id}/replay", response_model=ReplayDeltaResponse)
async def get_replay_delta(
    session_id: UUID,
    from_sequence: int = Query(..., description="Start sequence for replay delta"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get replay delta from a specific sequence number.
    
    **Roles:** Any authenticated user
    
    Used for live replay synchronization.
    """
    check_moot_operations_enabled()
    
    logs = await SessionService.get_session_logs(
        db=db,
        session_id=session_id,
        start_sequence=from_sequence
    )
    
    log_responses = [
        LogEntryResponse(
            id=log.id,
            session_id=log.session_id,
            timestamp=log.timestamp.isoformat() if log.timestamp else "",
            event_type=log.event_type,
            actor_id=log.actor_id,
            details=log.details,
            hash_chain=log.hash_chain,
            sequence_number=log.sequence_number,
            created_at=log.created_at.isoformat() if log.created_at else ""
        )
        for log in logs
    ]
    
    # Check if session is complete
    session = await SessionService.get_session(db, session_id)
    is_complete = session.status == SessionStatus.COMPLETED if session else False
    
    start_seq = logs[0].sequence_number if logs else from_sequence
    end_seq = logs[-1].sequence_number if logs else from_sequence
    
    return ReplayDeltaResponse(
        session_id=session_id,
        start_sequence=start_seq,
        end_sequence=end_seq,
        logs=log_responses,
        is_complete=is_complete
    )


# =============================================================================
# Integrity Verification Routes
# =============================================================================

@router.get("/{session_id}/verify", response_model=VerifyIntegrityResponse)
async def verify_session_integrity(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Verify integrity of session log chain.
    
    **Roles:** Any authenticated user
    
    Recomputes hashes and checks chain linking for tamper detection.
    """
    check_moot_operations_enabled()
    
    try:
        is_valid, invalid_sequences = await SessionService.verify_log_integrity(
            db=db,
            session_id=session_id
        )
        
        if is_valid:
            message = "Session log integrity verified - chain is valid"
        else:
            message = f"Session log integrity failed - invalid sequences: {invalid_sequences}"
        
        return VerifyIntegrityResponse(
            session_id=session_id,
            is_valid=is_valid,
            invalid_sequences=invalid_sequences,
            message=message
        )
    except SessionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# =============================================================================
# Active Sessions Route
# =============================================================================

@router.get("/active/list", response_model=List[SessionResponse])
async def get_active_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all currently active sessions.
    
    **Roles:** Any authenticated user
    """
    check_moot_operations_enabled()
    
    sessions = await SessionService.get_active_sessions(db)
    
    return [
        SessionResponse(
            id=session.id,
            assignment_id=session.assignment_id,
            status=session.status,
            started_at=session.started_at.isoformat() if session.started_at else None,
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            recording_url=session.recording_url,
            metadata=session.metadata,
            integrity_hash=session.integrity_hash,
            created_at=session.created_at.isoformat() if session.created_at else ""
        )
        for session in sessions
    ]
