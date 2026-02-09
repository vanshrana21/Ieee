"""
backend/schemas/ai_moot.py
Phase 3: AI Moot Court Practice Mode - Pydantic Schemas

Request/response models for solo AI moot court practice.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ProblemListItem(BaseModel):
    """Pre-loaded validation problem for Phase 3 testing."""
    id: int
    title: str
    legal_issue: str


class AISessionCreate(BaseModel):
    """Request to create a new AI moot court session.
    
    Supports BOTH:
    - problem_id: Database MootProject ID for custom problems
    - problem_type: Pre-loaded validation problem (validation_1, validation_2, validation_3)
    """
    problem_id: Optional[int] = None
    problem_type: Optional[Literal["validation_1", "validation_2", "validation_3", "custom"]] = None
    side: Literal["petitioner", "respondent"]
    
    @model_validator(mode='after')
    def require_either_problem(self):
        """Ensure either problem_id or problem_type is provided."""
        if not self.problem_id and not self.problem_type:
            raise ValueError("Either problem_id or problem_type must be provided")
        return self


class AISessionResponse(BaseModel):
    """Response with created session details."""
    id: int
    problem_title: str
    side: str
    current_turn: int


class AITurnSubmit(BaseModel):
    """Request to submit a turn argument."""
    argument: str = Field(
        ...,
        min_length=20,
        max_length=250,
        description="Argument must be between 20 and 250 characters"
    )


class ScoreBreakdown(BaseModel):
    """Score breakdown for a turn."""
    legal_accuracy: int = Field(..., ge=0, le=5)
    citation: int = Field(..., ge=0, le=5)
    etiquette: int = Field(..., ge=0, le=5)


class AITurnResponse(BaseModel):
    """Response with AI judge feedback for a turn."""
    feedback: str
    score_breakdown: ScoreBreakdown
    next_question: str
    session_complete: bool


class TurnDetail(BaseModel):
    """Detail of a completed turn."""
    turn_number: int
    user_argument: str
    ai_feedback: str
    legal_accuracy_score: int
    citation_score: int
    etiquette_score: int
    created_at: str


class SessionDetailResponse(BaseModel):
    """Response with full session details including all turns."""
    id: int
    problem_title: str
    side: str
    created_at: str
    completed_at: str | None
    turns: list[TurnDetail]
    total_score: int | None
