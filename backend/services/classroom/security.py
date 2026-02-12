"""
Classroom Security Middleware - Phase 7
Rate limiting, audit logging, and security enforcement.
"""
import time
import logging
from typing import Optional, Dict, Callable
from functools import wraps
from datetime import datetime, timedelta

from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.database import get_async_db
from backend.orm.classroom_round_action import ClassroomRoundAction, ActionType
from backend.orm.user import User

logger = logging.getLogger(__name__)
security = HTTPBearer()


# =============================================================================
# Rate Limiting
# =============================================================================

class RateLimiter:
    """
    In-memory rate limiter for classroom endpoints.
    
    For production, consider using Redis-based rate limiting.
    """
    
    def __init__(self):
        # user_id -> {endpoint: [(timestamp, count), ...]}
        self.requests: Dict[int, Dict[str, list]] = {}
        self.window_size = 60  # 60 seconds
    
    def is_allowed(self, user_id: int, endpoint: str, max_requests: int = 30) -> bool:
        """
        Check if request is within rate limit.
        
        Args:
            user_id: User making the request
            endpoint: API endpoint being accessed
            max_requests: Maximum requests allowed in window
            
        Returns:
            True if request is allowed, False if rate limited
        """
        now = time.time()
        
        if user_id not in self.requests:
            self.requests[user_id] = {}
        
        if endpoint not in self.requests[user_id]:
            self.requests[user_id][endpoint] = []
        
        # Clean old entries
        self.requests[user_id][endpoint] = [
            ts for ts in self.requests[user_id][endpoint]
            if now - ts < self.window_size
        ]
        
        # Check limit
        if len(self.requests[user_id][endpoint]) >= max_requests:
            return False
        
        # Record request
        self.requests[user_id][endpoint].append(now)
        return True
    
    def get_remaining(self, user_id: int, endpoint: str, max_requests: int = 30) -> int:
        """Get remaining requests in current window."""
        if user_id not in self.requests or endpoint not in self.requests[user_id]:
            return max_requests
        
        now = time.time()
        valid_requests = [
            ts for ts in self.requests[user_id][endpoint]
            if now - ts < self.window_size
        ]
        
        return max(0, max_requests - len(valid_requests))


# Global rate limiter instance
rate_limiter = RateLimiter()


def rate_limit(max_requests: int = 30, window_seconds: int = 60):
    """
    Decorator for rate limiting endpoints.
    
    Usage:
        @router.post("/some-endpoint")
        @rate_limit(max_requests=10)
        async def my_endpoint(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request and current user from kwargs or args
            request = kwargs.get('request')
            current_user = kwargs.get('current_user')
            
            if not request or not current_user:
                # Try to find in args
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                    elif hasattr(arg, 'id'):  # Assume it's a user
                        current_user = arg
            
            if current_user and request:
                endpoint = request.url.path
                
                if not rate_limiter.is_allowed(current_user.id, endpoint, max_requests):
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Rate limit exceeded. Try again in {window_seconds} seconds.",
                        headers={"Retry-After": str(window_seconds)}
                    )
                
                # Add rate limit headers
                remaining = rate_limiter.get_remaining(current_user.id, endpoint, max_requests)
                # Note: Headers would need to be added to response
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# =============================================================================
# Audit Logging
# =============================================================================

class AuditLogger:
    """
    Audit logger for privileged classroom actions.
    
    Logs all important actions for compliance and debugging.
    """
    
    PRIVILEGED_ACTIONS = {
        "session_create": ActionType.ROUND_CREATED,
        "session_start": ActionType.ROUND_STARTED,
        "session_end": ActionType.ROUND_COMPLETED,
        "round_transition": ActionType.STATE_TRANSITION,
        "round_score": ActionType.SCORE_SUBMITTED,
        "round_override": ActionType.SCORE_OVERRIDDEN,
        "participant_remove": ActionType.PARTICIPANT_REMOVED,
        "pairing_update": ActionType.PAIRING_UPDATED,
        "force_state_change": ActionType.FORCE_STATE_CHANGE,
    }
    
    async def log(
        self,
        db: AsyncSession,
        action_type: str,
        actor_id: int,
        session_id: Optional[int] = None,
        round_id: Optional[int] = None,
        payload: Optional[Dict] = None,
        request: Optional[Request] = None
    ):
        """
        Log an audit event.
        
        Args:
            db: Database session
            action_type: Type of action (see PRIVILEGED_ACTIONS)
            actor_id: User performing the action
            session_id: Related session ID
            round_id: Related round ID
            payload: Additional data
            request: HTTP request for IP/user agent
        """
        if action_type not in self.PRIVILEGED_ACTIONS:
            return  # Not a privileged action, don't log
        
        # Extract request info
        ip_address = None
        user_agent = None
        
        if request:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")
        
        # Create audit log entry
        action = ClassroomRoundAction(
            round_id=round_id,
            session_id=session_id,
            actor_user_id=actor_id,
            action_type=self.PRIVILEGED_ACTIONS[action_type],
            payload=payload or {},
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        db.add(action)
        await db.flush()
        
        # Also log to application logger
        logger.info(
            f"AUDIT: {action_type} by user {actor_id} "
            f"(session={session_id}, round={round_id})"
        )
    
    async def get_audit_log(
        self,
        db: AsyncSession,
        session_id: Optional[int] = None,
        round_id: Optional[int] = None,
        actor_id: Optional[int] = None,
        action_type: Optional[ActionType] = None,
        limit: int = 100
    ):
        """Query audit log entries."""
        query = select(ClassroomRoundAction)
        
        if session_id:
            query = query.where(ClassroomRoundAction.session_id == session_id)
        if round_id:
            query = query.where(ClassroomRoundAction.round_id == round_id)
        if actor_id:
            query = query.where(ClassroomRoundAction.actor_user_id == actor_id)
        if action_type:
            query = query.where(ClassroomRoundAction.action_type == action_type)
        
        query = query.order_by(ClassroomRoundAction.created_at.desc()).limit(limit)
        
        result = await db.execute(query)
        return result.scalars().all()


# Global audit logger
audit_logger = AuditLogger()


# =============================================================================
# Security Dependencies
# =============================================================================

async def require_classroom_access(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
) -> User:
    """
    Dependency to verify user has access to a classroom session.
    
    Raises HTTPException if user is not a participant or teacher.
    """
    from backend.orm.classroom_session import ClassroomSession, ClassroomParticipant
    
    # Check if teacher
    session = await db.scalar(
        select(ClassroomSession).where(
            ClassroomSession.id == session_id,
            ClassroomSession.teacher_id == current_user.id
        )
    )
    
    if session:
        return current_user
    
    # Check if participant
    participant = await db.scalar(
        select(ClassroomParticipant).where(
            ClassroomParticipant.session_id == session_id,
            ClassroomParticipant.user_id == current_user.id,
            ClassroomParticipant.approved == True
        )
    )
    
    if participant:
        return current_user
    
    # Check if admin
    if current_user.role in ["admin", "institution_admin"]:
        return current_user
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this classroom session"
    )


async def require_round_participant(
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
) -> User:
    """
    Dependency to verify user is a participant in a round.
    
    Raises HTTPException if user is not petitioner, respondent, or judge.
    """
    from backend.orm.classroom_round import ClassroomRound
    
    round_obj = await db.scalar(
        select(ClassroomRound).where(ClassroomRound.id == round_id)
    )
    
    if not round_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Round not found"
        )
    
    # Check if participant
    is_participant = current_user.id in [
        round_obj.petitioner_id,
        round_obj.respondent_id,
        round_obj.judge_id
    ]
    
    if is_participant:
        return current_user
    
    # Check if teacher of the session
    from backend.orm.classroom_session import ClassroomSession
    session = await db.scalar(
        select(ClassroomSession).where(
            ClassroomSession.id == round_obj.session_id,
            ClassroomSession.teacher_id == current_user.id
        )
    )
    
    if session:
        return current_user
    
    # Check if admin
    if current_user.role in ["admin", "institution_admin"]:
        return current_user
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You are not a participant in this round"
    )


# =============================================================================
# Input Validation & Sanitization
# =============================================================================

def sanitize_input(text: str, max_length: int = 10000) -> str:
    """
    Sanitize user input to prevent XSS and injection attacks.
    
    Args:
        text: Input text to sanitize
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length]
    
    # Remove dangerous HTML tags
    dangerous_tags = [
        "script", "iframe", "object", "embed", "form", "input",
        "textarea", "button", "link", "style", "meta"
    ]
    
    import re
    for tag in dangerous_tags:
        # Remove opening tags
        text = re.sub(f'<{tag}[^>]*>', '', text, flags=re.IGNORECASE)
        # Remove closing tags
        text = re.sub(f'</{tag}>', '', text, flags=re.IGNORECASE)
    
    # Remove event handlers
    text = re.sub(r'\s*on\w+\s*=\s*"[^"]*"', '', text, flags=re.IGNORECASE)
    text = re.sub(r"\s*on\w+\s*=\s*'[^']*'", '', text, flags=re.IGNORECASE)
    
    return text.strip()


def validate_join_code(code: str) -> bool:
    """
    Validate join code format.
    
    Join codes should be 6-20 alphanumeric characters.
    """
    import re
    pattern = r'^[A-Z0-9]{6,20}$'
    return bool(re.match(pattern, code.upper()))


# =============================================================================
# Security Headers
# =============================================================================

async def add_security_headers(request: Request, call_next):
    """
    Middleware to add security headers to responses.
    """
    response = await call_next(request)
    
    # Prevent content type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"
    
    # XSS protection
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    # Strict transport security (HTTPS only)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    # Content security policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self' wss: https:;"
    )
    
    return response


# =============================================================================
# Multi-tenant Validation
# =============================================================================

async def validate_institution_scope(
    session_id: int,
    current_user: User,
    db: AsyncSession
) -> bool:
    """
    Validate that user and session belong to the same institution.
    
    Returns True if valid, raises HTTPException if invalid.
    """
    from backend.orm.classroom_session import ClassroomSession
    
    session = await db.scalar(
        select(ClassroomSession).where(ClassroomSession.id == session_id)
    )
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Admins can access any institution
    if current_user.role in ["admin", "super_admin"]:
        return True
    
    # Check institution match
    if session.institution_id != current_user.institution_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: institution mismatch"
        )
    
    return True
