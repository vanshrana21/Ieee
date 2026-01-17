from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class TutorChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    session_id: Optional[str] = None
    mode: str = "adaptive"  # "adaptive" | "concise" | "detailed" | "remediation"

class StudyAction(BaseModel):
    type: str  # "practice", "read", "review"
    module_id: Optional[int] = None
    doc_type: Optional[str] = None
    doc_id: Optional[int] = None
    title: Optional[str] = None

class ProvenanceItem(BaseModel):
    doc_type: str
    doc_id: Any
    score: float

class AdaptiveTutorResponse(BaseModel):
    answer: str
    depth: str
    mini_lesson: Optional[List[str]] = None
    worked_examples: Optional[List[Dict[str, Any]]] = None
    study_actions: List[StudyAction]
    why_this_help: str
    provenance: List[ProvenanceItem]
    confidence_score: float
    linked_topics: Optional[List[str]] = None

class TutorChatResponse(BaseModel):
    # Phase 4.2 compatibility
    answer: str
    confidence: Optional[str] = None
    linked_topics: List[str]
    why_this_answer: str
    # Phase 4.3 extensions (optional to maintain compatibility)
    adaptive: Optional[AdaptiveTutorResponse] = None
