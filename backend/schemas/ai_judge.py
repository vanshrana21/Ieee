"""
Pydantic Schemas for AI Judge Engine — Phase 4

Request/response models for rubrics, evaluations, and faculty overrides.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, Field, validator


# ============================================================================
# Rubric Schemas
# ============================================================================

class RubricCriterion(BaseModel):
    """Single criterion in a rubric."""
    id: str = Field(..., description="Unique identifier for criterion")
    label: str = Field(..., description="Human-readable label")
    weight: float = Field(..., ge=0, le=1, description="Weight (0-1)")
    type: str = Field("numeric", description="Type: numeric, boolean, etc.")
    scale: List[int] = Field([0, 100], description="Min/max scale values")


class RubricDefinition(BaseModel):
    """Complete rubric definition JSON."""
    name: str
    version: int
    criteria: List[RubricCriterion]
    instructions_for_llm: str


class RubricCreateRequest(BaseModel):
    """Create a new rubric."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    rubric_type: str = Field("oral_argument", description="Type of rubric")
    definition: RubricDefinition


class RubricResponse(BaseModel):
    """Rubric response."""
    id: int
    name: str
    description: Optional[str]
    rubric_type: str
    current_version: int
    definition: Dict[str, Any]
    created_at: str
    is_active: bool
    
    class Config:
        from_attributes = True


class RubricVersionResponse(BaseModel):
    """Frozen rubric version response."""
    id: int
    rubric_id: int
    version_number: int
    name: str
    frozen_json: Dict[str, Any]
    criteria_summary: Optional[str]
    created_at: str
    
    class Config:
        from_attributes = True


class RubricListResponse(BaseModel):
    """List of rubrics."""
    rubrics: List[RubricResponse]
    total: int


# ============================================================================
# Evaluation Request/Response Schemas
# ============================================================================

class EvaluationTriggerRequest(BaseModel):
    """Trigger AI evaluation for a participant/round."""
    participant_id: int = Field(..., description="Participant to evaluate")
    turn_id: Optional[int] = Field(None, description="Specific turn (optional)")
    rubric_version_id: int = Field(..., description="Rubric version to use")
    transcript_text: Optional[str] = Field(None, description="Override transcript (optional)")
    
    @validator('rubric_version_id')
    def validate_rubric_version(cls, v):
        if v <= 0:
            raise ValueError("rubric_version_id must be positive")
        return v


class EvaluationResponse(BaseModel):
    """Evaluation response."""
    id: int
    session_id: int
    round_id: int
    participant_id: int
    turn_id: Optional[int]
    rubric_version_id: int
    status: str
    final_score: Optional[float]
    score_breakdown: Optional[Dict[str, float]]
    weights_used: Optional[Dict[str, float]]
    ai_model: str
    ai_model_version: Optional[str]
    evaluation_timestamp: str
    finalized_by_faculty_id: Optional[int]
    finalized_at: Optional[str]
    created_at: str
    
    class Config:
        from_attributes = True


class EvaluationDetailResponse(EvaluationResponse):
    """Detailed evaluation with attempts and audit."""
    attempts: List["EvaluationAttemptResponse"]
    overrides: List["FacultyOverrideResponse"]
    audit_entries: List["EvaluationAuditResponse"]


class EvaluationListResponse(BaseModel):
    """List of evaluations for a session/round."""
    evaluations: List[EvaluationResponse]
    total: int


# ============================================================================
# Evaluation Attempt Schemas
# ============================================================================

class EvaluationAttemptResponse(BaseModel):
    """Raw LLM attempt response."""
    id: int
    evaluation_id: Optional[int]
    attempt_number: int
    prompt_hash: str
    llm_raw_response: Optional[str]
    parsed_json: Optional[Dict[str, Any]]
    parse_status: str
    parse_errors: Optional[List[str]]
    ai_model: str
    ai_model_version: Optional[str]
    llm_latency_ms: Optional[int]
    llm_token_usage_input: Optional[int]
    llm_token_usage_output: Optional[int]
    is_canonical: bool
    created_at: str
    completed_at: Optional[str]
    
    class Config:
        from_attributes = True


# ============================================================================
# Faculty Override Schemas
# ============================================================================

class FacultyOverrideRequest(BaseModel):
    """Faculty override of AI evaluation."""
    new_score: float = Field(..., ge=0, le=100, description="New final score")
    new_breakdown: Dict[str, float] = Field(..., description="New per-criterion scores")
    reason: str = Field(..., min_length=10, description="Required justification")


class FacultyOverrideResponse(BaseModel):
    """Faculty override record."""
    id: int
    ai_evaluation_id: int
    previous_score: float
    new_score: float
    previous_breakdown: Optional[Dict[str, float]]
    new_breakdown: Optional[Dict[str, float]]
    faculty_id: int
    reason: str
    created_at: str
    
    class Config:
        from_attributes = True


# ============================================================================
# Audit Schemas
# ============================================================================

class EvaluationAuditResponse(BaseModel):
    """Audit log entry."""
    id: int
    evaluation_id: int
    attempt_id: Optional[int]
    action: str
    actor_user_id: Optional[int]
    payload_json: Optional[Dict[str, Any]]
    created_at: str
    
    class Config:
        from_attributes = True


# ============================================================================
# Leaderboard Schemas
# ============================================================================

class LeaderboardEntry(BaseModel):
    """Single leaderboard entry."""
    participant_id: int
    user_id: int
    user_name: Optional[str]
    side: Optional[str]
    speaker_number: Optional[int]
    final_score: float
    rank: int
    evaluations_count: int
    has_override: bool


class LeaderboardResponse(BaseModel):
    """Session leaderboard."""
    session_id: int
    entries: List[LeaderboardEntry]
    generated_at: str


# ============================================================================
# Error Response Schemas
# ============================================================================

class EvaluationErrorResponse(BaseModel):
    """Error response for evaluation failures."""
    success: bool = False
    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable message")
    details: Optional[Dict[str, Any]] = None
    requires_review: bool = False
    evaluation_id: Optional[int] = None


# ============================================================================
# LLM Response Schema (expected from AI)
# ============================================================================

class LLMScoreBreakdown(BaseModel):
    """Expected scores from LLM."""
    substance: int = Field(..., ge=0, le=100)
    structure: int = Field(..., ge=0, le=100)
    citations: int = Field(..., ge=0, le=100)
    delivery: int = Field(..., ge=0, le=100)


class LLMComments(BaseModel):
    """Expected comments from LLM."""
    substance: str
    structure: str
    citations: str
    delivery: str


class LLMMeta(BaseModel):
    """Metadata from LLM."""
    confidence: float = Field(..., ge=0, le=1)


class LLMExpectedResponse(BaseModel):
    """Strict schema for LLM JSON output validation."""
    scores: LLMScoreBreakdown
    weights: Dict[str, float]
    comments: LLMComments
    pass_fail: bool
    meta: LLMMeta


# Forward references for nested models
EvaluationDetailResponse.model_rebuild()
