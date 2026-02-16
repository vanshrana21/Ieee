"""
Phase 19 — Moot Courtroom Operations & Live Session Management Service.

Deterministic live session tracking with hash-chained audit logs for replay.

Phase 20 Integration: Lifecycle guards prevent sessions on closed tournaments.
"""
import hashlib
import json
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from sqlalchemy.orm import selectinload

from backend.orm.phase19_moot_operations import (
    CourtroomSession, SessionParticipation, SessionObservation, SessionLogEntry,
    SessionStatus, ParticipantRole, ParticipantStatus
)
from backend.config.feature_flags import feature_flags


async def _check_lifecycle_guard(tournament_id: UUID) -> bool:
    """Phase 20: Check if session operations are allowed."""
    try:
        from backend.config.feature_flags import feature_flags as ff
        if not ff.FEATURE_TOURNAMENT_LIFECYCLE:
            return True
        
        from backend.services.phase20_lifecycle_service import LifecycleService
        from backend.database import async_session_maker
        
        async with async_session_maker() as db:
            allowed, _ = await LifecycleService.check_operation_allowed(
                db, tournament_id, "session"
            )
            return allowed
    except Exception:
        return True  # Fail open


class SessionError(Exception):
    """Base exception for session errors."""
    pass


class SessionNotFoundError(SessionError):
    """Raised when session is not found."""
    pass


class InvalidSessionStatusError(SessionError):
    """Raised when invalid status transition is attempted."""
    pass


class SessionCompletedError(SessionError):
    """Raised when trying to modify completed session."""
    pass


class SessionService:
    """
    Service for deterministic live courtroom session management.
    
    All operations are deterministic and produce hash-chained audit logs.
    Completed sessions are immutable with integrity verification.
    """
    
    # State machine valid transitions
    VALID_TRANSITIONS = {
        SessionStatus.PENDING: [SessionStatus.ACTIVE],
        SessionStatus.ACTIVE: [SessionStatus.PAUSED, SessionStatus.COMPLETED],
        SessionStatus.PAUSED: [SessionStatus.ACTIVE, SessionStatus.COMPLETED],
        SessionStatus.COMPLETED: [],  # Terminal state
    }
    
    @staticmethod
    def _is_valid_transition(current: SessionStatus, new: SessionStatus) -> bool:
        """Check if status transition is valid."""
        return new in SessionService.VALID_TRANSITIONS.get(current, [])
    
    @staticmethod
    def _compute_log_hash(
        session_id: UUID,
        timestamp: datetime,
        event_type: str,
        details: Dict[str, Any],
        previous_hash: Optional[str]
    ) -> str:
        """
        Compute SHA256 hash for log entry with chain linking.
        
        Creates deterministic hash chain for tamper detection.
        """
        # Build deterministic data
        data = {
            "session_id": str(session_id),
            "timestamp": timestamp.isoformat(),
            "event_type": event_type,
            "details": json.dumps(details, sort_keys=True, separators=(',', ':')),
            "previous_hash": previous_hash or "0" * 64,
        }
        
        # Deterministic JSON
        json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        
        # SHA256 hash
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()
    
    @staticmethod
    def _compute_session_integrity_hash(session_data: Dict[str, Any]) -> str:
        """
        Compute SHA256 integrity hash for completed session.
        
        Includes all session data for verification.
        """
        # Sort keys for determinism
        json_str = json.dumps(session_data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()
    
    @staticmethod
    def _constant_time_compare(a: str, b: str) -> bool:
        """Constant-time string comparison to prevent timing attacks."""
        if len(a) != len(b):
            return False
        result = 0
        for x, y in zip(a, b):
            result |= ord(x) ^ ord(y)
        return result == 0
    
    # ==========================================================================
    # Session Operations
    # ==========================================================================
    
    @staticmethod
    async def create_session(
        db: AsyncSession,
        assignment_id: UUID,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CourtroomSession:
        """
        Create a new courtroom session.
        
        Args:
            db: Database session
            assignment_id: Match schedule assignment ID
            metadata: Optional session configuration
            
        Returns:
            Created CourtroomSession
        """
        session = CourtroomSession(
            assignment_id=assignment_id,
            status=SessionStatus.PENDING,
            metadata=metadata,
            integrity_hash=None
        )
        
        db.add(session)
        await db.flush()
        
        return session
    
    @staticmethod
    async def get_session(
        db: AsyncSession,
        session_id: UUID,
        lock: bool = False
    ) -> Optional[CourtroomSession]:
        """
        Get session by ID.
        
        Args:
            db: Database session
            session_id: Session UUID
            lock: Whether to use FOR UPDATE locking
            
        Returns:
            CourtroomSession or None
        """
        query = select(CourtroomSession).where(CourtroomSession.id == session_id)
        
        if lock:
            query = query.with_for_update()
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def start_session(
        db: AsyncSession,
        session_id: UUID,
        started_by_user_id: UUID
    ) -> Tuple[CourtroomSession, SessionLogEntry]:
        """
        Start a session (PENDING → ACTIVE).
        
        Args:
            db: Database session
            session_id: Session UUID
            started_by_user_id: User starting the session
            
        Returns:
            Tuple of (updated session, log entry)
            
        Raises:
            SessionNotFoundError: If session not found
            InvalidSessionStatusError: If invalid transition
        """
        # Lock session
        session = await SessionService.get_session(db, session_id, lock=True)
        
        if not session:
            raise SessionNotFoundError("Session not found")
        
        if session.status == SessionStatus.COMPLETED:
            raise SessionCompletedError("Cannot start completed session")
        
        if not SessionService._is_valid_transition(session.status, SessionStatus.ACTIVE):
            raise InvalidSessionStatusError(
                f"Cannot transition from {session.status} to ACTIVE"
            )
        
        # Update session
        session.status = SessionStatus.ACTIVE
        session.started_at = datetime.utcnow()
        
        # Create log entry
        log_entry = await SessionService._create_log_entry(
            db=db,
            session_id=session_id,
            event_type="SESSION_STARTED",
            actor_id=started_by_user_id,
            details={"previous_status": SessionStatus.PENDING}
        )
        
        await db.flush()
        
        return session, log_entry
    
    @staticmethod
    async def pause_session(
        db: AsyncSession,
        session_id: UUID,
        paused_by_user_id: UUID,
        reason: Optional[str] = None
    ) -> Tuple[CourtroomSession, SessionLogEntry]:
        """
        Pause a session (ACTIVE → PAUSED).
        
        Args:
            db: Database session
            session_id: Session UUID
            paused_by_user_id: User pausing the session
            reason: Optional pause reason
            
        Returns:
            Tuple of (updated session, log entry)
        """
        session = await SessionService.get_session(db, session_id, lock=True)
        
        if not session:
            raise SessionNotFoundError("Session not found")
        
        if session.status == SessionStatus.COMPLETED:
            raise SessionCompletedError("Cannot pause completed session")
        
        if not SessionService._is_valid_transition(session.status, SessionStatus.PAUSED):
            raise InvalidSessionStatusError(
                f"Cannot transition from {session.status} to PAUSED"
            )
        
        session.status = SessionStatus.PAUSED
        
        log_entry = await SessionService._create_log_entry(
            db=db,
            session_id=session_id,
            event_type="SESSION_PAUSED",
            actor_id=paused_by_user_id,
            details={"reason": reason}
        )
        
        await db.flush()
        
        return session, log_entry
    
    @staticmethod
    async def resume_session(
        db: AsyncSession,
        session_id: UUID,
        resumed_by_user_id: UUID
    ) -> Tuple[CourtroomSession, SessionLogEntry]:
        """
        Resume a paused session (PAUSED → ACTIVE).
        
        Args:
            db: Database session
            session_id: Session UUID
            resumed_by_user_id: User resuming the session
            
        Returns:
            Tuple of (updated session, log entry)
        """
        session = await SessionService.get_session(db, session_id, lock=True)
        
        if not session:
            raise SessionNotFoundError("Session not found")
        
        if not SessionService._is_valid_transition(session.status, SessionStatus.ACTIVE):
            raise InvalidSessionStatusError(
                f"Cannot transition from {session.status} to ACTIVE"
            )
        
        session.status = SessionStatus.ACTIVE
        
        log_entry = await SessionService._create_log_entry(
            db=db,
            session_id=session_id,
            event_type="SESSION_RESUMED",
            actor_id=resumed_by_user_id,
            details={}
        )
        
        await db.flush()
        
        return session, log_entry
    
    @staticmethod
    async def complete_session(
        db: AsyncSession,
        session_id: UUID,
        completed_by_user_id: UUID,
        recording_url: Optional[str] = None
    ) -> Tuple[CourtroomSession, str]:
        """
        Complete a session and create integrity hash.
        
        Args:
            db: Database session
            session_id: Session UUID
            completed_by_user_id: User completing the session
            recording_url: Optional recording URL
            
        Returns:
            Tuple of (updated session, integrity_hash)
        """
        session = await SessionService.get_session(db, session_id, lock=True)
        
        if not session:
            raise SessionNotFoundError("Session not found")
        
        if session.status == SessionStatus.COMPLETED:
            raise SessionCompletedError("Session already completed")
        
        if not SessionService._is_valid_transition(session.status, SessionStatus.COMPLETED):
            raise InvalidSessionStatusError(
                f"Cannot transition from {session.status} to COMPLETED"
            )
        
        # Update session
        session.status = SessionStatus.COMPLETED
        session.ended_at = datetime.utcnow()
        if recording_url:
            session.recording_url = recording_url
        
        # Create completion log
        await SessionService._create_log_entry(
            db=db,
            session_id=session_id,
            event_type="SESSION_COMPLETED",
            actor_id=completed_by_user_id,
            details={"recording_url": recording_url}
        )
        
        # Build session data for integrity hash
        session_data = await SessionService._build_session_data(db, session_id)
        
        # Compute integrity hash
        integrity_hash = SessionService._compute_session_integrity_hash(session_data)
        session.integrity_hash = integrity_hash
        
        await db.flush()
        
        return session, integrity_hash
    
    @staticmethod
    async def _build_session_data(
        db: AsyncSession,
        session_id: UUID
    ) -> Dict[str, Any]:
        """Build deterministic session data for integrity hash."""
        # Get session
        session = await SessionService.get_session(db, session_id)
        
        # Get all participations
        participation_query = (
            select(SessionParticipation)
            .where(SessionParticipation.session_id == session_id)
            .order_by(SessionParticipation.joined_at)
        )
        participation_result = await db.execute(participation_query)
        participations = participation_result.scalars().all()
        
        # Get all logs
        logs_query = (
            select(SessionLogEntry)
            .where(SessionLogEntry.session_id == session_id)
            .order_by(SessionLogEntry.sequence_number)
        )
        logs_result = await db.execute(logs_query)
        logs = logs_result.scalars().all()
        
        # Build deterministic data
        data = {
            "session_id": str(session.id),
            "assignment_id": str(session.assignment_id),
            "status": session.status,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "recording_url": session.recording_url,
            "participations": [
                {
                    "user_id": str(p.user_id),
                    "role": p.role,
                    "joined_at": p.joined_at.isoformat(),
                    "left_at": p.left_at.isoformat() if p.left_at else None,
                    "connection_count": p.connection_count,
                }
                for p in participations
            ],
            "logs": [
                {
                    "sequence_number": log.sequence_number,
                    "timestamp": log.timestamp.isoformat(),
                    "event_type": log.event_type,
                    "actor_id": str(log.actor_id) if log.actor_id else None,
                    "details": log.details,
                    "hash_chain": log.hash_chain,
                }
                for log in logs
            ],
        }
        
        return data
    
    # ==========================================================================
    # Participant Operations
    # ==========================================================================
    
    @staticmethod
    async def participant_join(
        db: AsyncSession,
        session_id: UUID,
        user_id: UUID,
        role: ParticipantRole,
        client_info: Optional[Dict[str, Any]] = None
    ) -> Tuple[SessionParticipation, SessionLogEntry]:
        """
        Record participant joining session.
        
        Args:
            db: Database session
            session_id: Session UUID
            user_id: User UUID
            role: Participant role
            client_info: Optional client metadata
            
        Returns:
            Tuple of (participation record, log entry)
        """
        # Lock session
        session = await SessionService.get_session(db, session_id, lock=True)
        
        if not session:
            raise SessionNotFoundError("Session not found")
        
        if session.status == SessionStatus.COMPLETED:
            raise SessionCompletedError("Cannot join completed session")
        
        # Check for existing participation (reconnect)
        existing_query = (
            select(SessionParticipation)
            .where(
                and_(
                    SessionParticipation.session_id == session_id,
                    SessionParticipation.user_id == user_id
                )
            )
        )
        existing_result = await db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()
        
        if existing:
            # Reconnection
            existing.status = ParticipantStatus.CONNECTED
            existing.connection_count += 1
            
            log_entry = await SessionService._create_log_entry(
                db=db,
                session_id=session_id,
                event_type="PARTICIPANT_RECONNECTED",
                actor_id=user_id,
                details={"role": role, "connection_count": existing.connection_count}
            )
            
            await db.flush()
            return existing, log_entry
        
        # New participation
        participation = SessionParticipation(
            session_id=session_id,
            user_id=user_id,
            role=role,
            status=ParticipantStatus.CONNECTED,
            client_info=client_info
        )
        
        db.add(participation)
        
        log_entry = await SessionService._create_log_entry(
            db=db,
            session_id=session_id,
            event_type="PARTICIPANT_JOINED",
            actor_id=user_id,
            details={"role": role, "client_info": client_info}
        )
        
        await db.flush()
        
        return participation, log_entry
    
    @staticmethod
    async def participant_leave(
        db: AsyncSession,
        session_id: UUID,
        user_id: UUID
    ) -> Tuple[SessionParticipation, SessionLogEntry]:
        """
        Record participant leaving session.
        
        Args:
            db: Database session
            session_id: Session UUID
            user_id: User UUID
            
        Returns:
            Tuple of (updated participation, log entry)
        """
        # Lock participation
        participation_query = (
            select(SessionParticipation)
            .where(
                and_(
                    SessionParticipation.session_id == session_id,
                    SessionParticipation.user_id == user_id
                )
            )
            .with_for_update()
        )
        participation_result = await db.execute(participation_query)
        participation = participation_result.scalar_one_or_none()
        
        if not participation:
            raise SessionError("Participant not found in session")
        
        participation.status = ParticipantStatus.DISCONNECTED
        participation.left_at = datetime.utcnow()
        
        log_entry = await SessionService._create_log_entry(
            db=db,
            session_id=session_id,
            event_type="PARTICIPANT_LEFT",
            actor_id=user_id,
            details={"role": participation.role}
        )
        
        await db.flush()
        
        return participation, log_entry
    
    # ==========================================================================
    # Observer Operations
    # ==========================================================================
    
    @staticmethod
    async def observer_join(
        db: AsyncSession,
        session_id: UUID,
        user_id: Optional[UUID],
        client_info: Optional[Dict[str, Any]] = None
    ) -> SessionObservation:
        """
        Record observer joining session.
        
        Args:
            db: Database session
            session_id: Session UUID
            user_id: Optional user UUID (None for anonymous)
            client_info: Optional client metadata
            
        Returns:
            Created observation record
        """
        observation = SessionObservation(
            session_id=session_id,
            user_id=user_id,
            client_info=client_info
        )
        
        db.add(observation)
        await db.flush()
        
        return observation
    
    @staticmethod
    async def observer_leave(
        db: AsyncSession,
        observation_id: UUID
    ) -> SessionObservation:
        """
        Record observer leaving session.
        
        Args:
            db: Database session
            observation_id: Observation UUID
            
        Returns:
            Updated observation record
        """
        query = (
            select(SessionObservation)
            .where(SessionObservation.id == observation_id)
            .with_for_update()
        )
        result = await db.execute(query)
        observation = result.scalar_one_or_none()
        
        if not observation:
            raise SessionError("Observation not found")
        
        observation.left_at = datetime.utcnow()
        await db.flush()
        
        return observation
    
    # ==========================================================================
    # Log Operations
    # ==========================================================================
    
    @staticmethod
    async def _create_log_entry(
        db: AsyncSession,
        session_id: UUID,
        event_type: str,
        actor_id: Optional[UUID],
        details: Dict[str, Any]
    ) -> SessionLogEntry:
        """
        Create hash-chained log entry.
        
        Internal method - not exposed directly.
        """
        # Get next sequence number
        sequence_query = (
            select(SessionLogEntry.sequence_number)
            .where(SessionLogEntry.session_id == session_id)
            .order_by(desc(SessionLogEntry.sequence_number))
            .limit(1)
        )
        sequence_result = await db.execute(sequence_query)
        last_sequence = sequence_result.scalar()
        next_sequence = (last_sequence or 0) + 1
        
        # Get previous hash
        previous_hash = None
        if last_sequence:
            prev_hash_query = (
                select(SessionLogEntry.hash_chain)
                .where(
                    and_(
                        SessionLogEntry.session_id == session_id,
                        SessionLogEntry.sequence_number == last_sequence
                    )
                )
            )
            prev_hash_result = await db.execute(prev_hash_query)
            previous_hash = prev_hash_result.scalar()
        
        # Compute hash
        timestamp = datetime.utcnow()
        hash_chain = SessionService._compute_log_hash(
            session_id=session_id,
            timestamp=timestamp,
            event_type=event_type,
            details=details,
            previous_hash=previous_hash
        )
        
        # Create log entry
        log_entry = SessionLogEntry(
            session_id=session_id,
            timestamp=timestamp,
            event_type=event_type,
            actor_id=actor_id,
            details=details,
            hash_chain=hash_chain,
            sequence_number=next_sequence
        )
        
        db.add(log_entry)
        
        return log_entry
    
    @staticmethod
    async def log_event(
        db: AsyncSession,
        session_id: UUID,
        event_type: str,
        actor_id: Optional[UUID],
        details: Dict[str, Any]
    ) -> SessionLogEntry:
        """
        Log a custom event in the session.
        
        Args:
            db: Database session
            session_id: Session UUID
            event_type: Event type string
            actor_id: Optional actor UUID
            details: Event details dict
            
        Returns:
            Created log entry
        """
        return await SessionService._create_log_entry(
            db=db,
            session_id=session_id,
            event_type=event_type,
            actor_id=actor_id,
            details=details
        )
    
    # ==========================================================================
    # Query Operations
    # ==========================================================================
    
    @staticmethod
    async def get_session_logs(
        db: AsyncSession,
        session_id: UUID,
        start_sequence: Optional[int] = None,
        end_sequence: Optional[int] = None
    ) -> List[SessionLogEntry]:
        """
        Get session logs with optional sequence range.
        
        For replay: provide start_sequence to get delta.
        """
        query = (
            select(SessionLogEntry)
            .where(SessionLogEntry.session_id == session_id)
            .order_by(SessionLogEntry.sequence_number)
        )
        
        if start_sequence is not None:
            query = query.where(SessionLogEntry.sequence_number >= start_sequence)
        
        if end_sequence is not None:
            query = query.where(SessionLogEntry.sequence_number <= end_sequence)
        
        result = await db.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def get_session_participants(
        db: AsyncSession,
        session_id: UUID
    ) -> List[SessionParticipation]:
        """Get all participants in a session."""
        query = (
            select(SessionParticipation)
            .where(SessionParticipation.session_id == session_id)
            .order_by(SessionParticipation.joined_at)
        )
        
        result = await db.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def verify_log_integrity(
        db: AsyncSession,
        session_id: UUID
    ) -> Tuple[bool, List[int]]:
        """
        Verify integrity of session log chain.
        
        Recomputes hashes and checks chain linking.
        
        Returns:
            Tuple of (is_valid, list of invalid sequence numbers)
        """
        logs = await SessionService.get_session_logs(db, session_id)
        
        if not logs:
            return True, []
        
        invalid_sequences = []
        previous_hash = "0" * 64
        
        for log in logs:
            # Recompute hash
            computed_hash = SessionService._compute_log_hash(
                session_id=session_id,
                timestamp=log.timestamp,
                event_type=log.event_type,
                details=log.details,
                previous_hash=previous_hash if log.sequence_number > 1 else None
            )
            
            # Check hash matches
            if not SessionService._constant_time_compare(computed_hash, log.hash_chain):
                invalid_sequences.append(log.sequence_number)
            
            previous_hash = log.hash_chain
        
        return len(invalid_sequences) == 0, invalid_sequences
    
    @staticmethod
    async def get_active_sessions(
        db: AsyncSession
    ) -> List[CourtroomSession]:
        """Get all currently active sessions."""
        query = (
            select(CourtroomSession)
            .where(CourtroomSession.status == SessionStatus.ACTIVE)
            .order_by(CourtroomSession.started_at)
        )
        
        result = await db.execute(query)
        return result.scalars().all()
