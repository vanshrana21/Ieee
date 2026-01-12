"""
backend/schemas/content.py
Pydantic schemas for content module API responses

These schemas define the exact structure of API responses.
They provide type safety and auto-generated documentation.
"""
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


# ================= MODULE SCHEMAS =================

class ContentModuleResponse(BaseModel):
    """Response schema for content module metadata"""
    id: int
    subject_id: int
    module_type: str = Field(..., description="learn | cases | practice | notes")
    status: str = Field(..., description="active | locked | coming_soon")
    is_free: bool
    title: str
    description: Optional[str] = None
    order_index: int
    item_count: int = Field(0, description="Number of content items in module")
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


# ================= LEARN SCHEMAS =================

class LearnContentSummary(BaseModel):
    """Lightweight schema for learn content list"""
    id: int
    title: str
    summary: Optional[str] = None
    order_index: int
    estimated_time_minutes: Optional[int] = None


class LearnContentFull(BaseModel):
    """Full schema for learn content detail"""
    id: int
    module_id: int
    title: str
    body: str
    summary: Optional[str] = None
    order_index: int
    estimated_time_minutes: Optional[int] = None
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


# ================= CASE SCHEMAS =================

class CaseContentSummary(BaseModel):
    """Lightweight schema for case list"""
    id: int
    case_name: str
    citation: Optional[str] = None
    year: int
    exam_importance: str = Field(..., description="high | medium | low")
    tags: List[str] = Field(default_factory=list)


class CaseContentFull(BaseModel):
    """Full schema for case detail"""
    id: int
    module_id: int
    case_name: str
    citation: Optional[str] = None
    year: int
    court: Optional[str] = None
    facts: str
    issue: str
    judgment: str
    ratio: str
    exam_importance: str
    tags: List[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


# ================= PRACTICE SCHEMAS =================

class PracticeQuestionSummary(BaseModel):
    """Schema for practice question without answer"""
    id: int
    question_type: str = Field(..., description="mcq | short_answer | essay | case_analysis")
    question: str
    marks: int
    difficulty: str = Field(..., description="easy | medium | hard")
    order_index: int
    tags: List[str] = Field(default_factory=list)
    
    # MCQ options (only present for MCQs)
    option_a: Optional[str] = None
    option_b: Optional[str] = None
    option_c: Optional[str] = None
    option_d: Optional[str] = None


class PracticeQuestionWithAnswer(PracticeQuestionSummary):
    """Schema for practice question with answer (after submission)"""
    correct_answer: str
    explanation: Optional[str] = None


# ================= NOTES SCHEMAS =================

class UserNoteResponse(BaseModel):
    """Response schema for user notes"""
    id: int
    user_id: int
    subject_id: int
    title: Optional[str] = None
    content: str
    is_pinned: bool
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


class UserNoteCreate(BaseModel):
    """Request schema for creating/updating notes"""
    title: Optional[str] = Field(None, max_length=300)
    content: str = Field(..., min_length=1)
    is_pinned: bool = False


# ================= COMBINED RESPONSES =================

class ModuleContentResponse(BaseModel):
    """
    Combined response for module content.
    Used when fetching all content items for a module.
    """
    module: ContentModuleResponse
    items: List[LearnContentSummary | CaseContentSummary | PracticeQuestionSummary]
    
    class Config:
        from_attributes = True


class SubjectModulesResponse(BaseModel):
    """
    Response for all modules of a subject.
    Used for subject detail page.
    """
    subject_id: int
    subject_title: str
    modules: List[ContentModuleResponse]