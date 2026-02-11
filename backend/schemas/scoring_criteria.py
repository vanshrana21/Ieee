"""
Phase 3: Judge Scoring Interface - Scoring Criteria Definitions

5-criteria rubric for judge evaluation of oral round performance.
Each criterion scored on 1-5 scale.
"""
from typing import List, Optional
from pydantic import BaseModel, Field, validator
from enum import Enum


class ScoreCriterion(str, Enum):
    """Individual scoring criteria."""
    LEGAL_REASONING = "legal_reasoning"
    CITATION_FORMAT = "citation_format"
    COURTROOM_ETIQUETTE = "courtroom_etiquette"
    RESPONSIVENESS = "responsiveness"
    TIME_MANAGEMENT = "time_management"


class ScoreScale(int, Enum):
    """Valid score values (1-5 scale)."""
    POOR = 1
    WEAK = 2
    ADEQUATE = 3
    STRONG = 4
    EXCEPTIONAL = 5


class CriterionDefinition(BaseModel):
    """Definition of a single scoring criterion."""
    name: str = Field(..., description="Criterion name")
    key: ScoreCriterion = Field(..., description="Criterion identifier")
    description: str = Field(..., description="Brief description")
    scale_definitions: dict = Field(
        default_factory=dict,
        description="Score value (1-5) to description mapping"
    )


class ScoringRubric(BaseModel):
    """
    Complete 5-criteria scoring rubric.
    
    Total score = average of all 5 criteria (0.0-5.0 scale)
    Max possible = 25 (5 criteria × 5 max)
    """
    
    # 5 individual criteria (1-5 scale each)
    legal_reasoning: int = Field(
        ...,
        ge=1,
        le=5,
        description="Quality of legal arguments and precedent application"
    )
    citation_format: int = Field(
        ...,
        ge=1,
        le=5,
        description="Proper SCC citation format (AIR, SCR, SCC formats)"
    )
    courtroom_etiquette: int = Field(
        ...,
        ge=1,
        le=5,
        description="Professional conduct ('My Lord'/'Your Lordship' usage)"
    )
    responsiveness: int = Field(
        ...,
        ge=1,
        le=5,
        description="Answers to judge questions and rebuttals"
    )
    time_management: int = Field(
        ...,
        ge=1,
        le=5,
        description="Effective use of allocated time"
    )
    
    @validator('legal_reasoning', 'citation_format', 'courtroom_etiquette', 
               'responsiveness', 'time_management')
    def validate_score_range(cls, v):
        """Ensure score is within valid 1-5 range."""
        if v < 1 or v > 5:
            raise ValueError('Score must be between 1 and 5')
        return v
    
    def calculate_total(self) -> float:
        """Calculate total score (average of 5 criteria)."""
        scores = [
            self.legal_reasoning,
            self.citation_format,
            self.courtroom_etiquette,
            self.responsiveness,
            self.time_management
        ]
        return sum(scores) / 5.0
    
    def calculate_percentage(self) -> float:
        """Calculate percentage (0-100 scale)."""
        return (self.calculate_total() / 5.0) * 100
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "criteria": {
                "legal_reasoning": self.legal_reasoning,
                "citation_format": self.citation_format,
                "courtroom_etiquette": self.courtroom_etiquette,
                "responsiveness": self.responsiveness,
                "time_management": self.time_management
            },
            "total_score": self.calculate_total(),
            "percentage": self.calculate_percentage(),
            "max_possible": 25  # 5 criteria × 5 max
        }


class ScoreCreateRequest(BaseModel):
    """Request body for creating/updating a score."""
    team_id: int = Field(..., description="ID of team being scored")
    team_side: str = Field(..., pattern="^(petitioner|respondent)$")
    legal_reasoning: int = Field(..., ge=1, le=5)
    citation_format: int = Field(..., ge=1, le=5)
    courtroom_etiquette: int = Field(..., ge=1, le=5)
    responsiveness: int = Field(..., ge=1, le=5)
    time_management: int = Field(..., ge=1, le=5)
    written_feedback: Optional[str] = Field(
        None,
        max_length=1000,
        description="Written feedback (max 1000 characters)"
    )
    strengths: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="List of strengths (max 5 items)"
    )
    areas_for_improvement: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Areas for improvement (max 5 items)"
    )
    is_draft: bool = Field(
        default=True,
        description="Save as draft (true) or submit (false)"
    )
    
    @validator('strengths')
    def validate_strengths_count(cls, v):
        """Limit strengths to 5 items maximum."""
        if len(v) > 5:
            raise ValueError('Maximum 5 strengths allowed')
        return v
    
    @validator('areas_for_improvement')
    def validate_improvements_count(cls, v):
        """Limit improvements to 5 items maximum."""
        if len(v) > 5:
            raise ValueError('Maximum 5 areas for improvement allowed')
        return v
    
    @validator('written_feedback')
    def validate_feedback_length(cls, v):
        """Limit feedback to 1000 characters."""
        if v and len(v) > 1000:
            raise ValueError('Written feedback must not exceed 1000 characters')
        return v


class ScoreResponse(BaseModel):
    """Response model for score operations."""
    id: int
    round_id: int
    judge_id: int
    team_id: int
    team_side: str
    legal_reasoning: int
    citation_format: int
    courtroom_etiquette: int
    responsiveness: int
    time_management: int
    total_score: float
    written_feedback: Optional[str] = None
    strengths: List[str] = Field(default_factory=list)
    areas_for_improvement: List[str] = Field(default_factory=list)
    is_draft: bool
    is_submitted: bool
    submitted_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    class Config:
        from_attributes = True


class ScoreSubmitRequest(BaseModel):
    """Request body for submitting a draft score."""
    pass  # No fields needed - just the action


# ============================================================================
# RUBRIC DEFINITIONS FOR UI DISPLAY
# ============================================================================

RUBRIC_DEFINITIONS = {
    ScoreCriterion.LEGAL_REASONING: CriterionDefinition(
        name="Legal Reasoning",
        key=ScoreCriterion.LEGAL_REASONING,
        description="Quality of legal arguments and precedent application",
        scale_definitions={
            1: "Poor legal analysis, fundamental errors",
            2: "Weak legal analysis, significant gaps",
            3: "Adequate legal analysis, some logical flaws",
            4: "Strong legal analysis with minor gaps",
            5: "Exceptional legal analysis, clear application of precedent"
        }
    ),
    ScoreCriterion.CITATION_FORMAT: CriterionDefinition(
        name="Citation Format",
        key=ScoreCriterion.CITATION_FORMAT,
        description="Proper SCC citation format (AIR, SCR, SCC formats)",
        scale_definitions={
            1: "Consistent citation errors (>10 instances)",
            2: "Frequent citation errors (6-10 instances)",
            3: "Several citation errors (3-5 instances)",
            4: "Minor citation errors (1-2 instances)",
            5: "Perfect SCC citation format throughout"
        }
    ),
    ScoreCriterion.COURTROOM_ETIQUETTE: CriterionDefinition(
        name="Courtroom Etiquette",
        key=ScoreCriterion.COURTROOM_ETIQUETTE,
        description="Professional conduct ('My Lord'/'Your Lordship' usage)",
        scale_definitions={
            1: "Consistent etiquette violations (>10 instances)",
            2: "Frequent etiquette lapses (6-10 instances)",
            3: "Several etiquette lapses (3-5 instances)",
            4: "Minor etiquette lapses (1-2 instances)",
            5: "Perfect etiquette ('My Lord'/'Your Lordship' consistently)"
        }
    ),
    ScoreCriterion.RESPONSIVENESS: CriterionDefinition(
        name="Responsiveness",
        key=ScoreCriterion.RESPONSIVENESS,
        description="Answers to judge questions and rebuttals",
        scale_definitions={
            1: "Very poor responsiveness, refuses to answer",
            2: "Poor responsiveness, frequent evasion",
            3: "Adequate responsiveness, some evasiveness",
            4: "Good responsiveness with minor delays",
            5: "Excellent responsiveness to judge questions"
        }
    ),
    ScoreCriterion.TIME_MANAGEMENT: CriterionDefinition(
        name="Time Management",
        key=ScoreCriterion.TIME_MANAGEMENT,
        description="Effective use of allocated time",
        scale_definitions={
            1: "Consistent time overruns (>10 instances)",
            2: "Frequent time overruns (6-10 instances)",
            3: "Several time overruns (3-5 instances)",
            4: "Minor time overruns (1-2 instances)",
            5: "Perfect time management, stays within limits"
        }
    )
}


def get_rubric_description(criterion: ScoreCriterion, score: int) -> str:
    """
    Get the rubric description for a specific criterion and score.
    
    Args:
        criterion: The scoring criterion
        score: Score value (1-5)
    
    Returns:
        Human-readable description of what that score means
    """
    if criterion not in RUBRIC_DEFINITIONS:
        return "Unknown criterion"
    
    definition = RUBRIC_DEFINITIONS[criterion]
    return definition.scale_definitions.get(score, "Invalid score")


def get_all_rubric_definitions() -> dict:
    """Get all rubric definitions for UI display."""
    return {
        key.value: {
            "name": defn.name,
            "description": defn.description,
            "scale": defn.scale_definitions
        }
        for key, defn in RUBRIC_DEFINITIONS.items()
    }
