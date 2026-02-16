"""
Pydantic Schemas for Classroom Round Engine — Phase 3

Request and response models for rounds, turns, and audit operations.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ============================================================================
# Turn Schemas
# ============================================================================

class TurnCreate(BaseModel):
    """Schema for creating a turn."""
    participant_id: int = Field(..., description="ID of the participant who will speak")
    allowed_seconds: Optional[int] = Field(300, description="Allowed speaking time in seconds")


class TurnResponse(BaseModel):
    """Schema for turn response."""
    id: int
    round_id: int
    participant_id: int
    turn_order: int
    allowed_seconds: int
    started_at: Optional[str] = None
    submitted_at: Optional[str] = None
    transcript: Optional[str] = None
    word_count: Optional[int] = None
    is_submitted: bool
    
    class Config:
        from_attributes = True


class TurnStartRequest(BaseModel):
    """Schema for starting a turn."""
    turn_id: int = Field(..., description="ID of the turn to start")


class TurnStartResponse(BaseModel):
    """Schema for turn start response."""
    turn_id: int
    started_at: str
    allowed_seconds: int
    remaining_seconds: int


class TurnSubmitRequest(BaseModel):
    """Schema for submitting a turn transcript."""
    turn_id: int = Field(..., description="ID of the turn to submit")
    transcript: str = Field(..., description="Transcript content")
    word_count: int = Field(..., description="Word count of transcript")
    timestamp: Optional[str] = Field(None, description="Client timestamp (server validates)")


class TurnSubmitResponse(BaseModel):
    """Schema for turn submission response."""
    success: bool = True
    turn_id: int
    submitted_at: str
    next_current_speaker_participant_id: Optional[int] = None
    round_status: Optional[str] = None


class TurnAuditEntry(BaseModel):
    """Schema for turn audit log entry."""
    id: int
    turn_id: int
    action: str
    actor_user_id: int
    payload_json: Optional[str] = None
    created_at: str
    
    class Config:
        from_attributes = True


# ============================================================================
# Round Schemas
# ============================================================================

class RoundType(str):
    """Round type enum values."""
    PETITIONER_MAIN = "PETITIONER_MAIN"
    RESPONDENT_MAIN = "RESPONDENT_MAIN"
    REBUTTAL = "REBUTTAL"
    OTHER = "OTHER"


class RoundStatus(str):
    """Round status enum values."""
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class RoundCreateRequest(BaseModel):
    """Schema for creating a round with optional explicit turns."""
    session_id: int = Field(..., description="ID of the session")
    round_index: int = Field(..., description="Round index within session (1-based)")
    round_type: str = Field(..., description="Type: PETITIONER_MAIN, RESPONDENT_MAIN, REBUTTAL, OTHER")
    default_turn_seconds: int = Field(300, description="Default speaking time per turn")
    turns: Optional[List[TurnCreate]] = Field(None, description="Explicit turn definitions (auto-generated if None)")


class RoundResponse(BaseModel):
    """Schema for round response."""
    id: int
    session_id: int
    round_index: int
    round_type: str
    status: str
    current_speaker_participant_id: Optional[int] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    turns: List[TurnResponse] = []
    
    class Config:
        from_attributes = True


class RoundStartRequest(BaseModel):
    """Schema for starting a round."""
    round_id: int = Field(..., description="ID of the round to start")


class RoundStartResponse(BaseModel):
    """Schema for round start response."""
    success: bool = True
    round_id: int
    status: str
    current_speaker_participant_id: Optional[int] = None


class RoundAbortRequest(BaseModel):
    """Schema for aborting a round."""
    round_id: int = Field(..., description="ID of the round to abort")
    reason: Optional[str] = Field(None, description="Reason for abort")


class RoundAbortResponse(BaseModel):
    """Schema for round abort response."""
    success: bool = True
    round_id: int
    status: str = "ABORTED"
    ended_at: str


class RoundListResponse(BaseModel):
    """Schema for listing rounds."""
    rounds: List[RoundResponse]
    total: int


# ============================================================================
# Force Submit Schemas
# ============================================================================

class TurnForceSubmitRequest(BaseModel):
    """Schema for faculty force submit."""
    turn_id: int = Field(..., description="ID of the turn to force submit")
    transcript: Optional[str] = Field("", description="Optional transcript content")
    word_count: Optional[int] = Field(0, description="Optional word count")
    reason: Optional[str] = Field(None, description="Reason for force submit")


class TurnForceSubmitResponse(BaseModel):
    """Schema for force submit response."""
    success: bool = True
    turn_id: int
    round_id: int
    status: str
    force_submitted_at: str


# ============================================================================
# Error Response Schemas
# ============================================================================

class APIError(BaseModel):
    """Standard API error response."""
    success: bool = False
    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")


# ============================================================================
# Notification/Event Schemas
# ============================================================================

class RoundEvent(BaseModel):
    """Schema for round events (for notifications)."""
    event_type: str = Field(..., description="ROUND_STARTED, TURN_STARTED, TURN_SUBMITTED, TURN_TIMEOUT, ROUND_COMPLETED")
    round_id: int
    turn_id: Optional[int] = None
    session_id: int
    participant_id: Optional[int] = None
    timestamp: str
    payload: Optional[Dict[str, Any]] = None


# ============================================================================
# Metrics Schemas
# ============================================================================

class RoundMetrics(BaseModel):
    """Schema for round engine metrics."""
    rounds_started_total: int
    rounds_completed_total: int
    turns_submitted_total: int
    turns_timed_out_total: int
    avg_turn_duration_seconds: float
    percent_turns_late: float
