"""
WebSocket Event Protocol

Defines message types and validation for Human vs Human modes.
Server-authoritative: All messages validated before processing.
"""
from enum import Enum
from typing import Dict, List, Optional, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, validator


class EventType(str, Enum):
    """WebSocket event types."""
    
    # Connection Events
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    CONNECTION_ESTABLISHED = "connection_established"
    
    # Timer Events (SERVER-AUTHORITATIVE)
    TIMER_START = "timer_start"
    TIMER_UPDATE = "timer_update"
    TIMER_PAUSE = "timer_pause"
    TIMER_RESUME = "timer_resume"
    TIMER_EXPIRED = "timer_expired"
    
    # Session Events
    SESSION_STATE_CHANGE = "session_state_change"
    PREP_TIME_STARTED = "prep_time_started"
    PREP_TIME_UPDATE = "prep_time_update"
    PREP_TIME_EXPIRED = "prep_time_expired"
    
    # Argument Events
    ARGUMENT_SUBMITTED = "argument_submitted"
    ARGUMENT_ACCEPTED = "argument_accepted"
    ARGUMENT_REJECTED = "argument_rejected"
    
    # Judge Events
    JUDGE_INTERRUPT = "judge_interrupt"
    OBJECTION_RAISED = "objection_raised"
    OBJECTION_RULING = "objection_ruling"
    
    # Scoring Events
    SCORE_SUBMITTED = "score_submitted"
    SCORE_UPDATED = "score_updated"
    LEADERBOARD_UPDATE = "leaderboard_update"
    
    # Match Events (Online 1v1 only)
    MATCH_FOUND = "match_found"
    MATCH_STARTED = "match_started"
    MATCH_COMPLETED = "match_completed"
    
    # Error Events
    ERROR = "error"
    VALIDATION_FAILED = "validation_failed"


class BaseEvent(BaseModel):
    """Base event model."""
    type: EventType
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    room_id: Optional[str] = None
    
    class Config:
        use_enum_values = True


# Connection Events
class UserJoinedEvent(BaseEvent):
    """User joined room."""
    type: Literal[EventType.USER_JOINED] = EventType.USER_JOINED
    user_id: str
    role: str
    name: str


class UserLeftEvent(BaseEvent):
    """User left room."""
    type: Literal[EventType.USER_LEFT] = EventType.USER_LEFT
    user_id: str


class ConnectionEstablishedEvent(BaseEvent):
    """Connection established successfully."""
    type: Literal[EventType.CONNECTION_ESTABLISHED] = EventType.CONNECTION_ESTABLISHED
    room_id: str
    participants: List[Dict[str, Any]]


# Timer Events
class TimerStartEvent(BaseEvent):
    """Timer started (server-authoritative)."""
    type: Literal[EventType.TIMER_START] = EventType.TIMER_START
    duration_seconds: int
    current_speaker: Optional[str] = None
    
    @validator('duration_seconds')
    def validate_duration(cls, v):
        if v < 0 or v > 7200:  # Max 2 hours
            raise ValueError('Duration must be between 0 and 7200 seconds')
        return v


class TimerUpdateEvent(BaseEvent):
    """Timer update (broadcast periodically)."""
    type: Literal[EventType.TIMER_UPDATE] = EventType.TIMER_UPDATE
    time_remaining: int
    is_paused: bool = False


class TimerPauseEvent(BaseEvent):
    """Timer paused."""
    type: Literal[EventType.TIMER_PAUSE] = EventType.TIMER_PAUSE
    paused_by: str


class TimerResumeEvent(BaseEvent):
    """Timer resumed."""
    type: Literal[EventType.TIMER_RESUME] = EventType.TIMER_RESUME
    resumed_by: str


class TimerExpiredEvent(BaseEvent):
    """Timer expired."""
    type: Literal[EventType.TIMER_EXPIRED] = EventType.TIMER_EXPIRED
    current_speaker: Optional[str] = None


# Session Events
class SessionStateChangeEvent(BaseEvent):
    """Session state changed."""
    type: Literal[EventType.SESSION_STATE_CHANGE] = EventType.SESSION_STATE_CHANGE
    from_state: str
    to_state: str
    triggered_by: Optional[str] = None


class PrepTimeStartedEvent(BaseEvent):
    """Preparation time started."""
    type: Literal[EventType.PREP_TIME_STARTED] = EventType.PREP_TIME_STARTED
    duration_seconds: int


class PrepTimeUpdateEvent(BaseEvent):
    """Preparation time update."""
    type: Literal[EventType.PREP_TIME_UPDATE] = EventType.PREP_TIME_UPDATE
    time_remaining: int


class PrepTimeExpiredEvent(BaseEvent):
    """Preparation time expired."""
    type: Literal[EventType.PREP_TIME_EXPIRED] = EventType.PREP_TIME_EXPIRED


# Argument Events
class ArgumentSubmittedEvent(BaseEvent):
    """Argument submitted by participant."""
    type: Literal[EventType.ARGUMENT_SUBMITTED] = EventType.ARGUMENT_SUBMITTED
    user_id: str
    role: str
    text: str
    timestamp: str
    
    @validator('text')
    def validate_text(cls, v):
        if len(v) < 10:
            raise ValueError('Argument too short (min 10 characters)')
        if len(v) > 5000:
            raise ValueError('Argument too long (max 5000 characters)')
        return v


class ArgumentAcceptedEvent(BaseEvent):
    """Argument accepted."""
    type: Literal[EventType.ARGUMENT_ACCEPTED] = EventType.ARGUMENT_ACCEPTED
    argument_id: str
    score: Optional[float] = None


class ArgumentRejectedEvent(BaseEvent):
    """Argument rejected."""
    type: Literal[EventType.ARGUMENT_REJECTED] = EventType.ARGUMENT_REJECTED
    argument_id: str
    reason: str


# Judge Events
class JudgeInterruptEvent(BaseEvent):
    """Judge interrupt event."""
    type: Literal[EventType.JUDGE_INTERRUPT] = EventType.JUDGE_INTERRUPT
    interrupt_type: str  # question, objection, clarification
    message: str


class ObjectionRaisedEvent(BaseEvent):
    """Objection raised."""
    type: Literal[EventType.OBJECTION_RAISED] = EventType.OBJECTION_RAISED
    by_user_id: str
    objection_type: str  # relevance, hearsay, leading, etc.
    text: Optional[str] = None


class ObjectionRulingEvent(BaseEvent):
    """Objection ruling."""
    type: Literal[EventType.OBJECTION_RULING] = EventType.OBJECTION_RULING
    objection_id: str
    ruling: str  # sustained, overruled
    notes: Optional[str] = None


# Scoring Events
class ScoreSubmittedEvent(BaseEvent):
    """Score submitted."""
    type: Literal[EventType.SCORE_SUBMITTED] = EventType.SCORE_SUBMITTED
    user_id: str
    criteria_scores: Dict[str, int]  # legal_reasoning, citation_format, etc.
    total_score: float
    
    @validator('criteria_scores')
    def validate_scores(cls, v):
        for key, score in v.items():
            if score < 1 or score > 5:
                raise ValueError(f'Score for {key} must be between 1 and 5')
        return v
    
    @validator('total_score')
    def validate_total(cls, v):
        if v < 0 or v > 25:  # 5 criteria * 5 max = 25
            raise ValueError('Total score must be between 0 and 25')
        return v


class ScoreUpdatedEvent(BaseEvent):
    """Score updated."""
    type: Literal[EventType.SCORE_UPDATED] = EventType.SCORE_UPDATED
    score_id: str
    new_total: float


class LeaderboardUpdateEvent(BaseEvent):
    """Leaderboard updated."""
    type: Literal[EventType.LEADERBOARD_UPDATE] = EventType.LEADERBOARD_UPDATE
    rankings: List[Dict[str, Any]]


# Match Events (Online 1v1 only)
class MatchFoundEvent(BaseEvent):
    """Match found for online 1v1."""
    type: Literal[EventType.MATCH_FOUND] = EventType.MATCH_FOUND
    opponent_id: str
    opponent_name: str
    opponent_rating: int
    match_id: str


class MatchStartedEvent(BaseEvent):
    """Match started."""
    type: Literal[EventType.MATCH_STARTED] = EventType.MATCH_STARTED
    topic: str
    problem_statement: str
    your_role: str
    opponent_role: str


class MatchCompletedEvent(BaseEvent):
    """Match completed."""
    type: Literal[EventType.MATCH_COMPLETED] = EventType.MATCH_COMPLETED
    winner_id: Optional[str]
    your_score: Dict[str, Any]
    opponent_score: Dict[str, Any]
    rating_change: int
    new_rating: int


# Error Events
class ErrorEvent(BaseEvent):
    """Error event."""
    type: Literal[EventType.ERROR] = EventType.ERROR
    error_code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ValidationFailedEvent(BaseEvent):
    """Validation failed event."""
    type: Literal[EventType.VALIDATION_FAILED] = EventType.VALIDATION_FAILED
    field: str
    message: str
    received_value: Optional[Any] = None


# Event validation and routing
EVENT_MAP = {
    EventType.USER_JOINED: UserJoinedEvent,
    EventType.USER_LEFT: UserLeftEvent,
    EventType.CONNECTION_ESTABLISHED: ConnectionEstablishedEvent,
    EventType.TIMER_START: TimerStartEvent,
    EventType.TIMER_UPDATE: TimerUpdateEvent,
    EventType.TIMER_PAUSE: TimerPauseEvent,
    EventType.TIMER_RESUME: TimerResumeEvent,
    EventType.TIMER_EXPIRED: TimerExpiredEvent,
    EventType.SESSION_STATE_CHANGE: SessionStateChangeEvent,
    EventType.PREP_TIME_STARTED: PrepTimeStartedEvent,
    EventType.PREP_TIME_UPDATE: PrepTimeUpdateEvent,
    EventType.PREP_TIME_EXPIRED: PrepTimeExpiredEvent,
    EventType.ARGUMENT_SUBMITTED: ArgumentSubmittedEvent,
    EventType.ARGUMENT_ACCEPTED: ArgumentAcceptedEvent,
    EventType.ARGUMENT_REJECTED: ArgumentRejectedEvent,
    EventType.JUDGE_INTERRUPT: JudgeInterruptEvent,
    EventType.OBJECTION_RAISED: ObjectionRaisedEvent,
    EventType.OBJECTION_RULING: ObjectionRulingEvent,
    EventType.SCORE_SUBMITTED: ScoreSubmittedEvent,
    EventType.SCORE_UPDATED: ScoreUpdatedEvent,
    EventType.LEADERBOARD_UPDATE: LeaderboardUpdateEvent,
    EventType.MATCH_FOUND: MatchFoundEvent,
    EventType.MATCH_STARTED: MatchStartedEvent,
    EventType.MATCH_COMPLETED: MatchCompletedEvent,
    EventType.ERROR: ErrorEvent,
    EventType.VALIDATION_FAILED: ValidationFailedEvent,
}


def parse_event(data: Dict[str, Any]) -> Optional[BaseEvent]:
    """
    Parse event data into appropriate event model.
    
    Args:
        data: Raw event data from WebSocket
        
    Returns:
        Parsed event model or None if invalid
    """
    event_type = data.get('type')
    if not event_type:
        return None
    
    try:
        event_type_enum = EventType(event_type)
        event_class = EVENT_MAP.get(event_type_enum)
        if event_class:
            return event_class(**data)
        return None
    except (ValueError, TypeError):
        return None


def validate_event(event: BaseEvent, user_id: str, user_role: str) -> bool:
    """
    Validate event permissions based on user role.
    
    Args:
        event: Event to validate
        user_id: User ID sending the event
        user_role: User role (teacher, student, player)
        
    Returns:
        True if valid, False otherwise
    """
    # Teachers can send most events
    if user_role == 'teacher':
        return True
    
    # Students/players can only send specific events
    allowed_events = {
        'student': [
            EventType.ARGUMENT_SUBMITTED,
            EventType.OBJECTION_RAISED,
        ],
        'player': [
            EventType.ARGUMENT_SUBMITTED,
            EventType.OBJECTION_RAISED,
        ]
    }
    
    return event.type in allowed_events.get(user_role, [])


# Room ID patterns
ROOM_PREFIXES = {
    'classroom': 'classroom',
    'match': 'match',
}


def generate_room_id(room_type: str, entity_id: str) -> str:
    """
    Generate room ID with proper prefix.
    
    Args:
        room_type: Type of room (classroom, match)
        entity_id: Session ID or Match ID
        
    Returns:
        Formatted room ID
    """
    prefix = ROOM_PREFIXES.get(room_type, room_type)
    return f"{prefix}:{entity_id}"


def parse_room_id(room_id: str) -> tuple:
    """
    Parse room ID into type and entity ID.
    
    Args:
        room_id: Room ID string
        
    Returns:
        Tuple of (room_type, entity_id)
    """
    parts = room_id.split(':', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return room_id, None
