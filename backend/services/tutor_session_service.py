"""
backend/services/tutor_session_service.py
Phase 4.4: Tutor Memory - Session-level continuity
"""

import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_

from backend.orm.tutor_session import TutorSession, DEFAULT_SESSION_TTL_HOURS
from backend.orm.tutor_message import TutorMessage

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 5000
DEFAULT_MESSAGE_LIMIT = 6

PII_PATTERNS = [
    r'\b\d{12}\b',  # Aadhaar-like
    r'\b\d{10}\b',  # Phone numbers
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
    r'\b[A-Z]{5}\d{4}[A-Z]\b',  # PAN
]

def redact_pii(text: str) -> str:
    """Redact PII from text before storage."""
    for pattern in PII_PATTERNS:
        text = re.sub(pattern, '[REDACTED]', text)
    return text


async def start_session(
    user_id: int,
    db: AsyncSession,
    session_name: Optional[str] = None,
    preferences: Optional[Dict[str, Any]] = None,
    ttl_hours: int = DEFAULT_SESSION_TTL_HOURS
) -> Dict[str, Any]:
    """Start a new tutor session."""
    session_id = str(uuid.uuid4())
    now = datetime.utcnow()
    expires_at = now + timedelta(hours=ttl_hours)
    
    session = TutorSession(
        user_id=user_id,
        session_id=session_id,
        session_name=session_name or f"Session {now.strftime('%Y-%m-%d %H:%M')}",
        message_count=0,
        last_activity_at=now,
        expires_at=expires_at,
        preferences=preferences or {},
        pinned_preferences={},
        is_ephemeral=True
    )
    
    db.add(session)
    await db.commit()
    await db.refresh(session)
    
    logger.info(f"Session started: user_id={user_id}, session_id={session_id}")
    
    return {
        "session_id": session_id,
        "started_at": now.isoformat(),
        "expires_at": expires_at.isoformat()
    }


async def get_session(session_id: str, user_id: int, db: AsyncSession) -> Optional[TutorSession]:
    """Get session by ID, verifying ownership."""
    stmt = select(TutorSession).where(
        and_(
            TutorSession.session_id == session_id,
            TutorSession.user_id == user_id
        )
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if session and session.is_expired():
        logger.info(f"Session expired: {session_id}")
        return None
        
    return session


async def append_message(
    session_id: str,
    user_id: int,
    role: str,
    text: str,
    db: AsyncSession,
    metadata: Optional[Dict[str, Any]] = None,
    provenance: Optional[List[Dict]] = None,
    confidence_score: Optional[float] = None
) -> bool:
    """Append a message to the session."""
    session = await get_session(session_id, user_id, db)
    if not session:
        return False
        
    # Truncate and redact
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[:MAX_MESSAGE_LENGTH] + "... [truncated]"
    text = redact_pii(text)
    
    message = TutorMessage(
        session_id=session_id,
        role=role,
        content=text,
        provenance=provenance,
        confidence_score=confidence_score
    )
    
    db.add(message)
    session.increment_message_count()
    await db.commit()
    
    return True


async def get_history(
    session_id: str,
    user_id: int,
    db: AsyncSession,
    limit: int = DEFAULT_MESSAGE_LIMIT
) -> Dict[str, Any]:
    """Get session history with messages and preferences."""
    session = await get_session(session_id, user_id, db)
    if not session:
        return {"error": "Session not found or expired", "messages": [], "preferences": {}}
        
    stmt = (
        select(TutorMessage)
        .where(TutorMessage.session_id == session_id)
        .order_by(TutorMessage.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()
    
    # Reverse to get chronological order (oldest first)
    messages_list = [m.to_dict() for m in reversed(messages)]
    
    return {
        "session_id": session_id,
        "messages": messages_list,
        "preferences": session.preferences or {},
        "pinned_preferences": session.pinned_preferences or {},
        "message_count": session.message_count,
        "expires_at": session.expires_at.isoformat() if session.expires_at else None
    }


async def clear_session(session_id: str, user_id: int, db: AsyncSession) -> bool:
    """Clear all messages from a session."""
    session = await get_session(session_id, user_id, db)
    if not session:
        return False
        
    # Delete all messages
    stmt = delete(TutorMessage).where(TutorMessage.session_id == session_id)
    await db.execute(stmt)
    
    session.message_count = 0
    session.pinned_preferences = {}
    await db.commit()
    
    logger.info(f"Session cleared: user_id={user_id}, session_id={session_id}")
    return True


async def pin_preference(
    session_id: str,
    user_id: int,
    key: str,
    value: Any,
    db: AsyncSession
) -> bool:
    """Pin a preference for the session."""
    session = await get_session(session_id, user_id, db)
    if not session:
        return False
        
    pinned = session.pinned_preferences or {}
    pinned[key] = value
    session.pinned_preferences = pinned
    await db.commit()
    
    return True


async def extend_session_ttl(
    session_id: str,
    user_id: int,
    db: AsyncSession,
    hours: int = DEFAULT_SESSION_TTL_HOURS
) -> bool:
    """Extend session TTL."""
    session = await get_session(session_id, user_id, db)
    if not session:
        return False
        
    session.extend_ttl(hours)
    await db.commit()
    return True


async def make_session_permanent(session_id: str, user_id: int, db: AsyncSession) -> bool:
    """Mark session as non-ephemeral (permanent)."""
    session = await get_session(session_id, user_id, db)
    if not session:
        return False
        
    session.is_ephemeral = False
    session.expires_at = datetime.utcnow() + timedelta(days=365)  # 1 year
    await db.commit()
    return True


async def build_session_context(
    session_id: str,
    user_id: int,
    db: AsyncSession,
    message_limit: int = DEFAULT_MESSAGE_LIMIT
) -> Dict[str, Any]:
    """Build context from session for AI prompt."""
    history = await get_history(session_id, user_id, db, limit=message_limit)
    
    if "error" in history:
        return {"session_available": False, "warning": history["error"]}
        
    messages_formatted = []
    for msg in history["messages"]:
        role_label = "Student" if msg["role"] in ["user", "student"] else "Assistant"
        messages_formatted.append(f"[{role_label}] {msg['content']}")
        
    return {
        "session_available": True,
        "messages": messages_formatted,
        "pinned_preferences": history.get("pinned_preferences", {}),
        "preferences": history.get("preferences", {})
    }


async def evict_expired_sessions(db: AsyncSession) -> int:
    """Evict all expired ephemeral sessions. Returns count deleted."""
    now = datetime.utcnow()
    
    # Find expired ephemeral sessions
    stmt = select(TutorSession).where(
        and_(
            TutorSession.is_ephemeral == True,
            TutorSession.expires_at < now
        )
    )
    result = await db.execute(stmt)
    expired_sessions = result.scalars().all()
    
    count = 0
    for session in expired_sessions:
        # Delete messages first (cascade should handle, but explicit)
        await db.execute(
            delete(TutorMessage).where(TutorMessage.session_id == session.session_id)
        )
        await db.delete(session)
        count += 1
        
    await db.commit()
    logger.info(f"Evicted {count} expired sessions")
    return count
