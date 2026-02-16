"""
Classroom Session API Schemas (Pydantic)
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class SessionCreate(BaseModel):
    """Request schema for creating a session."""
    case_id: Optional[int] = None
    topic: str = Field(..., min_length=5, max_length=255)
    category: Optional[str] = "constitutional"
    prep_time_minutes: Optional[int] = Field(default=15, ge=5, le=60)
    oral_time_minutes: Optional[int] = Field(default=10, ge=5, le=60)
    ai_judge_mode: Optional[str] = "hybrid"  # on/off/hybrid
    max_participants: Optional[int] = Field(default=40, ge=2, le=100)
    
    @validator('topic')
    def sanitize_topic(cls, v):
        """Basic XSS prevention."""
        return v.strip().replace('<script>', '').replace('</script>', '')


class SessionResponse(BaseModel):
    """Response schema for session data."""
    id: int
    session_code: str
    teacher_id: int
    case_id: Optional[int] = None
    topic: str
    category: str
    prep_time_minutes: int
    oral_time_minutes: int
    ai_judge_mode: str
    max_participants: int
    current_state: str
    teacher_online: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    participants_count: int
    remaining_seconds: Optional[int] = None
    is_phase_expired: bool = False
    
    class Config:
        from_attributes = True


class SessionJoinRequest(BaseModel):
    """Request schema for joining a session."""
    session_code: str = Field(..., pattern=r'^JURIS-[A-Z0-9]{6}$')


class SessionJoinResponse(BaseModel):
    """Response schema for joining a session with deterministic assignment."""
    session_id: int
    session_code: str
    side: Optional[str] = None  # PETITIONER / RESPONDENT
    speaker_number: Optional[int] = None  # 1 or 2
    total_participants: Optional[int] = None
    role: Optional[str] = None  # Legacy field for backward compatibility
    current_state: str
    remaining_seconds: Optional[int]
    message: str


class ParticipantResponse(BaseModel):
    """Response schema for participant data."""
    id: int
    session_id: int
    user_id: int
    role: str
    joined_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    is_connected: bool
    score_id: Optional[int] = None
    
    class Config:
        from_attributes = True


class ArgumentCreate(BaseModel):
    """Request schema for submitting an argument."""
    text: str = Field(..., min_length=10, max_length=5000)
    
    @validator('text')
    def sanitize_text(cls, v):
        """Basic XSS prevention."""
        # Remove dangerous HTML tags
        v = v.replace('<script>', '').replace('</script>', '')
        v = v.replace('<iframe>', '').replace('</iframe>', '')
        v = v.replace('javascript:', '')
        return v.strip()


class ArgumentResponse(BaseModel):
    """Response schema for arguments."""
    id: int
    session_id: int
    user_id: int
    role: str
    text: str
    timestamp: Optional[str] = None
    ai_score: Optional[float] = None
    judge_notes: Optional[str] = None
    
    class Config:
        from_attributes = True


class ScoreUpdate(BaseModel):
    """Request schema for updating scores."""
    legal_reasoning: Optional[int] = Field(None, ge=1, le=5)
    citation_format: Optional[int] = Field(None, ge=1, le=5)
    courtroom_etiquette: Optional[int] = Field(None, ge=1, le=5)
    responsiveness: Optional[int] = Field(None, ge=1, le=5)
    time_management: Optional[int] = Field(None, ge=1, le=5)
    feedback_text: Optional[str] = None
    is_draft: bool = True


class SessionStateChangeRequest(BaseModel):
    """Request schema for state transitions (legacy)."""
    target_state: str = Field(..., pattern=r'^(preparing|study|moot|scoring|completed|cancelled)$')
    validation_data: Optional[Dict[str, Any]] = None


class StrictStateTransitionRequest(BaseModel):
    """Request schema for strict state machine transitions."""
    target_state: str = Field(..., min_length=1, max_length=50, description="Target state (e.g., PREPARING, ARGUING_PETITIONER)")
    reason: Optional[str] = Field(None, max_length=500, description="Optional reason for the transition")


class StrictStateTransitionResponse(BaseModel):
    """Response schema for strict state machine transitions."""
    success: bool
    session_id: int
    new_state: str
    previous_state: str
    state_updated_at: Optional[str] = None
    triggered_by: Optional[int] = None
    reason: Optional[str] = None


class AllowedTransitionResponse(BaseModel):
    """Response schema for allowed transitions."""
    from_state: str
    allowed_states: List[str]
    transitions: List[Dict[str, Any]]


class StateLogResponse(BaseModel):
    """Response schema for state transition log entries."""
    id: int
    session_id: int
    from_state: str
    to_state: str
    triggered_by_user_id: Optional[int] = None
    trigger_type: Optional[str] = None
    reason: Optional[str] = None
    is_successful: bool
    error_message: Optional[str] = None
    created_at: str
    
    class Config:
        from_attributes = True
