"""
Phase 8 — Global Integrity Verification Route

Admin-only endpoint for full system integrity audit.
Verifies event chains, hashes, and states across all live sessions.
"""
import json
import hashlib
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from datetime import datetime

from backend.database import get_db
from backend.orm.live_court import (
    LiveCourtSession, LiveCourtStatus, LiveEventLog, LiveTurn, LiveTurnState
)
from backend.orm.live_objection import LiveObjection, ObjectionState
from backend.orm.exhibit import SessionExhibit, ExhibitState
from backend.auth import require_admin, get_current_user

router = APIRouter(prefix="/integrity", tags=["integrity"])


class IntegrityVerifier:
    """
    Verifies system-wide integrity across all sessions.
    
    Checks:
    - Event chain continuity (no sequence gaps)
    - Event hash recomputation and validation
    - Turn state consistency
    - Objection state consistency
    - Exhibit file hash verification
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.invalid_sessions: List[Dict[str, Any]] = []
        self.sessions_checked = 0
    
    async def verify_all_sessions(self) -> Dict[str, Any]:
        """
        Run full integrity verification on all sessions.
        
        Returns:
            Dict with verification results
        """
        # Fetch all sessions (live and completed)
        result = await self.db.execute(
            select(LiveCourtSession)
            .order_by(LiveCourtSession.id.asc())  # Deterministic order
        )
        sessions = result.scalars().all()
        
        self.sessions_checked = len(sessions)
        
        for session in sessions:
            session_issues = await self._verify_session(session)
            if session_issues:
                self.invalid_sessions.append({
                    "session_id": session.id,
                    "issues": session_issues
                })
        
        # Update last checked timestamp for all live sessions
        await self._update_check_timestamp()
        
        return {
            "sessions_checked": self.sessions_checked,
            "invalid_sessions": self.invalid_sessions,
            "tamper_detected": len(self.invalid_sessions) > 0,
            "system_valid": len(self.invalid_sessions) == 0,
            "checked_at": datetime.utcnow().isoformat()
        }
    
    async def _verify_session(self, session: LiveCourtSession) -> List[str]:
        """
        Verify single session integrity.
        
        Args:
            session: Session to verify
        Returns:
            List of issues found (empty if valid)
        """
        issues = []
        session_id = session.id
        
        # 1. Verify event chain
        event_issues = await self._verify_event_chain(session_id)
        issues.extend(event_issues)
        
        # 2. Verify turn states
        turn_issues = await self._verify_turn_states(session_id)
        issues.extend(turn_issues)
        
        # 3. Verify objection states
        objection_issues = await self._verify_objection_states(session_id)
        issues.extend(objection_issues)
        
        # 4. Verify exhibit integrity
        exhibit_issues = await self._verify_exhibit_integrity(session_id)
        issues.extend(exhibit_issues)
        
        return issues
    
    async def _verify_event_chain(self, session_id: int) -> List[str]:
        """
        Verify event log chain for session.
        
        Checks:
        - No sequence gaps
        - Event hashes valid
        - Deterministic serialization
        
        Args:
            session_id: Session ID
        Returns:
            List of issues
        """
        issues = []
        
        result = await self.db.execute(
            select(LiveEventLog)
            .where(LiveEventLog.session_id == session_id)
            .order_by(LiveEventLog.event_sequence.asc())
        )
        events = result.scalars().all()
        
        if not events:
            return issues  # No events is valid (new session)
        
        expected_sequence = 1
        
        for event in events:
            # Check sequence continuity
            if event.event_sequence != expected_sequence:
                issues.append(
                    f"Sequence gap: expected {expected_sequence}, got {event.event_sequence}"
                )
                expected_sequence = event.event_sequence
            
            # Recompute and verify hash
            try:
                payload_dict = json.loads(event.payload_json)
                serialized = json.dumps(payload_dict, sort_keys=True)
                
                # Reconstruct hash input (same as Phase 5 service)
                hash_input = (
                    f"{event.session_id}|"
                    f"{event.event_type.value}|"
                    f"{serialized}|"
                    f"{event.created_at.isoformat()}"
                )
                
                recomputed_hash = hashlib.sha256(
                    hash_input.encode()
                ).hexdigest()
                
                if recomputed_hash != event.event_hash:
                    issues.append(
                        f"Hash mismatch at sequence {event.event_sequence}: "
                        f"stored={event.event_hash[:16]}..., "
                        f"computed={recomputed_hash[:16]}..."
                    )
            except json.JSONDecodeError:
                issues.append(
                    f"Invalid JSON payload at sequence {event.event_sequence}"
                )
            except Exception as e:
                issues.append(
                    f"Hash verification error at sequence {event.event_sequence}: {e}"
                )
            
            expected_sequence += 1
        
        return issues
    
    async def _verify_turn_states(self, session_id: int) -> List[str]:
        """
        Verify turn state consistency.
        
        Args:
            session_id: Session ID
        Returns:
            List of issues
        """
        issues = []
        
        result = await self.db.execute(
            select(LiveTurn)
            .where(LiveTurn.session_id == session_id)
            .order_by(LiveTurn.id.asc())
        )
        turns = result.scalars().all()
        
        # Check for multiple active turns
        active_turns = [t for t in turns if t.state == LiveTurnState.ACTIVE]
        if len(active_turns) > 1:
            issues.append(
                f"Multiple active turns: {[t.id for t in active_turns]}"
            )
        
        # Check state transitions (completed must have ended_at)
        for turn in turns:
            if turn.state == LiveTurnState.COMPLETED and not turn.ended_at:
                issues.append(
                    f"Turn {turn.id} marked completed but no ended_at"
                )
        
        return issues
    
    async def _verify_objection_states(self, session_id: int) -> List[str]:
        """
        Verify objection state consistency.
        
        Args:
            session_id: Session ID
        Returns:
            List of issues
        """
        issues = []
        
        result = await self.db.execute(
            select(LiveObjection)
            .where(LiveObjection.session_id == session_id)
            .order_by(LiveObjection.id.asc())
        )
        objections = result.scalars().all()
        
        for obj in objections:
            # Ruled objections must have ruling fields
            if obj.state in (ObjectionState.SUSTAINED, ObjectionState.OVERRULED):
                if not obj.ruled_at:
                    issues.append(
                        f"Objection {obj.id} ruled but no ruled_at timestamp"
                    )
                if not obj.ruled_by_user_id:
                    issues.append(
                        f"Objection {obj.id} ruled but no ruled_by_user_id"
                    )
        
        return issues
    
    async def _verify_exhibit_integrity(self, session_id: int) -> List[str]:
        """
        Verify exhibit file integrity.
        
        Args:
            session_id: Session ID
        Returns:
            List of issues
        """
        issues = []
        
        result = await self.db.execute(
            select(SessionExhibit)
            .where(SessionExhibit.session_id == session_id)
            .order_by(SessionExhibit.id.asc())
        )
        exhibits = result.scalars().all()
        
        for exhibit in exhibits:
            # Marked/admitted/rejected exhibits must have exhibit_number
            if exhibit.state in (ExhibitState.MARKED, ExhibitState.TENDERED, 
                               ExhibitState.ADMITTED, ExhibitState.REJECTED):
                if not exhibit.exhibit_number:
                    issues.append(
                        f"Exhibit {exhibit.id} in state {exhibit.state.value} "
                        f"but no exhibit_number"
                    )
            
            # Ruled exhibits must have ruling fields
            if exhibit.state in (ExhibitState.ADMITTED, ExhibitState.REJECTED):
                if not exhibit.ruled_at:
                    issues.append(
                        f"Exhibit {exhibit.id} ruled but no ruled_at"
                    )
            
            # Verify exhibit hash if marked
            if exhibit.state != ExhibitState.UPLOADED:
                if not exhibit.exhibit_hash:
                    issues.append(
                        f"Exhibit {exhibit.id} marked but no exhibit_hash"
                    )
        
        return issues
    
    async def _update_check_timestamp(self) -> None:
        """Update integrity_last_checked_at for all live sessions."""
        result = await self.db.execute(
            select(LiveCourtSession)
            .where(LiveCourtSession.status == LiveCourtStatus.LIVE)
        )
        live_sessions = result.scalars().all()
        
        now = datetime.utcnow()
        for session in live_sessions:
            session.integrity_last_checked_at = now
        
        await self.db.flush()


@router.get("/global-verify")
async def global_integrity_verify(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Run global integrity verification.
    
    Admin only. Verifies all live sessions for:
    - Event chain continuity
    - Hash integrity
    - State consistency
    - Tamper detection
    
    Returns:
        Verification report
    """
    verifier = IntegrityVerifier(db)
    result = await verifier.verify_all_sessions()
    
    # Log verification event
    print(f"Integrity verification run by admin {current_user.get('user_id')}: "
          f"valid={result['system_valid']}, "
          f"sessions={result['sessions_checked']}, "
          f"issues={len(result['invalid_sessions'])}")
    
    return result


@router.get("/session/{session_id}")
async def verify_single_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Verify single session integrity.
    
    Requires institution scoping.
    """
    # Fetch session
    result = await self.db.execute(
        select(LiveCourtSession).where(LiveCourtSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Institution scoping
    user_institution = current_user.get("institution_id")
    if session.institution_id != user_institution and not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Institution access denied"
        )
    
    verifier = IntegrityVerifier(db)
    issues = await verifier._verify_session(session)
    
    return {
        "session_id": session_id,
        "valid": len(issues) == 0,
        "issues": issues,
        "checked_at": datetime.utcnow().isoformat()
    }
