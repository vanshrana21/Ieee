"""
Phase 0: Virtual Courtroom Infrastructure - WebSocket Message Schemas

Type-safe Pydantic models for all WebSocket message types.
All timestamps use ISO 8601 format.
"""
from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


# ============================================================================
# ENUM DEFINITIONS
# ============================================================================

class SpeakerRole(str, Enum):
    """Current speaker in the courtroom."""
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    JUDGE = "judge"
    NONE = "none"


class ObjectionType(str, Enum):
    """Types of legal objections."""
    HEARSAY = "hearsay"
    LEADING = "leading"
    RELEVANCE = "relevance"
    SPECULATION = "speculation"
    ARGUMENTATIVE = "argumentative"
    OTHER = "other"


class ObjectionRuling(str, Enum):
    """Possible rulings on an objection."""
    SUSTAINED = "sustained"
    OVERRULED = "overruled"
    RESERVED = "reserved"


class TimerAction(str, Enum):
    """Timer control actions."""
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    RESET = "reset"


class MessageType(str, Enum):
    """All supported WebSocket message types."""
    # Connection
    CONNECTION_ESTABLISHED = "connection_established"
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    PING = "ping"
    PONG = "pong"
    
    # Timer
    TIMER_UPDATE = "timer_update"
    TIMER_START = "timer_start"
    TIMER_PAUSE = "timer_pause"
    TIMER_RESUME = "timer_resume"
    TIMER_RESET = "timer_reset"
    
    # Objections
    OBJECTION_RAISED = "objection_raised"
    OBJECTION_RULING = "objection_ruling"
    
    # Transcript
    TRANSCRIPT_UPDATE = "transcript_update"
    
    # Scoring
    SCORE_UPDATE = "score_update"
    
    # Round lifecycle
    SPEAKER_CHANGE = "speaker_change"
    ROUND_COMPLETE = "round_complete"
    
    # Errors
    ERROR = "error"


# ============================================================================
# BASE MESSAGE
# ============================================================================

class BaseMessage(BaseModel):
    """Base class for all WebSocket messages."""
    type: MessageType = Field(..., description="Message type discriminator")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="ISO 8601 timestamp")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ============================================================================
# CONNECTION MESSAGES
# ============================================================================

class ConnectionEstablishedMessage(BaseMessage):
    """Sent to client when WebSocket connection is established."""
    type: Literal[MessageType.CONNECTION_ESTABLISHED] = MessageType.CONNECTION_ESTABLISHED
    data: Dict[str, Any] = Field(..., description="Room state and participants")


class UserJoinedMessage(BaseMessage):
    """Broadcast when a user joins the room."""
    type: Literal[MessageType.USER_JOINED] = MessageType.USER_JOINED
    data: Dict[str, Any] = Field(..., description="{user_id, role, timestamp}")


class UserLeftMessage(BaseMessage):
    """Broadcast when a user leaves the room."""
    type: Literal[MessageType.USER_LEFT] = MessageType.USER_LEFT
    data: Dict[str, Any] = Field(..., description="{user_id, role, timestamp}")


class PingMessage(BaseMessage):
    """Client keep-alive ping."""
    type: Literal[MessageType.PING] = MessageType.PING


class PongMessage(BaseMessage):
    """Server response to ping."""
    type: Literal[MessageType.PONG] = MessageType.PONG


# ============================================================================
# TIMER MESSAGES
# ============================================================================

class TimerUpdateMessage(BaseMessage):
    """Broadcast timer state changes."""
    type: Literal[MessageType.TIMER_UPDATE] = MessageType.TIMER_UPDATE
    time_remaining: int = Field(..., ge=0, description="Seconds remaining")
    is_paused: bool = Field(..., description="Whether timer is paused")
    current_speaker: SpeakerRole = Field(..., description="Current speaker")
    action: Optional[TimerAction] = Field(None, description="Triggering action")


class TimerStartMessage(BaseMessage):
    """Request to start the timer."""
    type: Literal[MessageType.TIMER_START] = MessageType.TIMER_START
    speaker_role: SpeakerRole = Field(..., description="Speaker to start timer for")
    time_remaining: int = Field(..., ge=0, description="Initial time in seconds")


class TimerPauseMessage(BaseMessage):
    """Request to pause the timer."""
    type: Literal[MessageType.TIMER_PAUSE] = MessageType.TIMER_PAUSE
    time_remaining: int = Field(..., ge=0, description="Current time when paused")


class TimerResumeMessage(BaseMessage):
    """Request to resume the timer."""
    type: Literal[MessageType.TIMER_RESUME] = MessageType.TIMER_RESUME


class TimerResetMessage(BaseMessage):
    """Request to reset the timer."""
    type: Literal[MessageType.TIMER_RESET] = MessageType.TIMER_RESET
    time_remaining: int = Field(..., ge=0, description="Time to reset to")


# ============================================================================
# OBJECTION MESSAGES
# ============================================================================

class ObjectionRaisedMessage(BaseMessage):
    """Broadcast when an objection is raised."""
    type: Literal[MessageType.OBJECTION_RAISED] = MessageType.OBJECTION_RAISED
    objection_id: int = Field(..., description="Database ID of objection")
    raised_by_team_id: int = Field(..., description="Team that raised objection")
    raised_by_user_id: int = Field(..., description="User that raised objection")
    objection_type: ObjectionType = Field(..., description="Type of objection")
    objection_text: Optional[str] = Field(None, description="Custom reason if type is 'other'")
    interrupted_speaker: SpeakerRole = Field(..., description="Speaker who was interrupted")
    time_remaining_before: int = Field(..., description="Timer value before interruption")


class ObjectionRulingMessage(BaseMessage):
    """Broadcast when judge rules on an objection."""
    type: Literal[MessageType.OBJECTION_RULING] = MessageType.OBJECTION_RULING
    objection_id: int = Field(..., description="Database ID of objection")
    ruling: ObjectionRuling = Field(..., description="Judge's ruling")
    ruling_notes: Optional[str] = Field(None, description="Judge's explanation")
    judge_id: int = Field(..., description="ID of judging user")
    time_remaining_after: Optional[int] = Field(None, description="Timer value after ruling")


# ============================================================================
# TRANSCRIPT MESSAGES
# ============================================================================

class TranscriptUpdateMessage(BaseMessage):
    """Broadcast transcript segment updates."""
    type: Literal[MessageType.TRANSCRIPT_UPDATE] = MessageType.TRANSCRIPT_UPDATE
    segment_id: str = Field(..., description="Unique segment identifier")
    speaker_role: SpeakerRole = Field(..., description="Speaker of this segment")
    text: str = Field(..., description="Transcribed text")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Whisper confidence (0.0-1.0)")
    audio_chunk_id: Optional[str] = Field(None, description="Source audio chunk UUID")


# ============================================================================
# SCORING MESSAGES
# ============================================================================

class ScoreCriteria(BaseModel):
    """Individual scoring criteria (1-5 scale)."""
    legal_reasoning: int = Field(..., ge=1, le=5)
    citation_format: int = Field(..., ge=1, le=5)
    courtroom_etiquette: int = Field(..., ge=1, le=5)
    responsiveness: int = Field(..., ge=1, le=5)
    time_management: int = Field(..., ge=1, le=5)


class ScoreUpdateMessage(BaseMessage):
    """Broadcast score updates from judges."""
    type: Literal[MessageType.SCORE_UPDATE] = MessageType.SCORE_UPDATE
    score_id: int = Field(..., description="Database ID of score")
    team_id: int = Field(..., description="Team being scored")
    team_side: SpeakerRole = Field(..., description="petitioner or respondent")
    judge_id: int = Field(..., description="ID of judging user")
    criteria: ScoreCriteria = Field(..., description="Individual criterion scores")
    total_score: float = Field(..., ge=1.0, le=5.0, description="Average of criteria")
    is_draft: bool = Field(..., description="Whether score is draft or final")


# ============================================================================
# ROUND LIFECYCLE MESSAGES
# ============================================================================

class SpeakerChangeMessage(BaseMessage):
    """Broadcast speaker transitions."""
    type: Literal[MessageType.SPEAKER_CHANGE] = MessageType.SPEAKER_CHANGE
    previous_speaker: SpeakerRole = Field(..., description="Previous speaker")
    new_speaker: SpeakerRole = Field(..., description="New current speaker")
    new_time_remaining: int = Field(..., ge=0, description="Time for new speaker")


class RoundCompleteMessage(BaseMessage):
    """Broadcast when round ends."""
    type: Literal[MessageType.ROUND_COMPLETE] = MessageType.ROUND_COMPLETE
    final_scores: Optional[Dict[str, Any]] = Field(None, description="Final score summary")
    winner_team_id: Optional[int] = Field(None, description="Winning team if determined")


# ============================================================================
# ERROR MESSAGES
# ============================================================================

class ErrorMessage(BaseMessage):
    """Error notification."""
    type: Literal[MessageType.ERROR] = MessageType.ERROR
    error_code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional context")


# ============================================================================
# UNION TYPE FOR MESSAGE ROUTING
# ============================================================================

CourtroomMessage = (
    ConnectionEstablishedMessage |
    UserJoinedMessage |
    UserLeftMessage |
    PingMessage |
    PongMessage |
    TimerUpdateMessage |
    TimerStartMessage |
    TimerPauseMessage |
    TimerResumeMessage |
    TimerResetMessage |
    ObjectionRaisedMessage |
    ObjectionRulingMessage |
    TranscriptUpdateMessage |
    ScoreUpdateMessage |
    SpeakerChangeMessage |
    RoundCompleteMessage |
    ErrorMessage
)


# ============================================================================
# MESSAGE PARSING
# ============================================================================

def parse_message(data: dict) -> CourtroomMessage:
    """
    Parse a raw dictionary into the appropriate message type.
    
    Args:
        data: Raw message dictionary with 'type' field
    
    Returns:
        Parsed Pydantic model instance
    
    Raises:
        ValueError: If message type is unknown or data is invalid
    """
    msg_type = data.get("type")
    
    type_map = {
        MessageType.CONNECTION_ESTABLISHED: ConnectionEstablishedMessage,
        MessageType.USER_JOINED: UserJoinedMessage,
        MessageType.USER_LEFT: UserLeftMessage,
        MessageType.PING: PingMessage,
        MessageType.PONG: PongMessage,
        MessageType.TIMER_UPDATE: TimerUpdateMessage,
        MessageType.TIMER_START: TimerStartMessage,
        MessageType.TIMER_PAUSE: TimerPauseMessage,
        MessageType.TIMER_RESUME: TimerResumeMessage,
        MessageType.TIMER_RESET: TimerResetMessage,
        MessageType.OBJECTION_RAISED: ObjectionRaisedMessage,
        MessageType.OBJECTION_RULING: ObjectionRulingMessage,
        MessageType.TRANSCRIPT_UPDATE: TranscriptUpdateMessage,
        MessageType.SCORE_UPDATE: ScoreUpdateMessage,
        MessageType.SPEAKER_CHANGE: SpeakerChangeMessage,
        MessageType.ROUND_COMPLETE: RoundCompleteMessage,
        MessageType.ERROR: ErrorMessage,
    }
    
    if msg_type not in type_map:
        raise ValueError(f"Unknown message type: {msg_type}")
    
    return type_map[msg_type](**data)
