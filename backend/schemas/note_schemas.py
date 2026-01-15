"""
backend/schemas/note_schemas.py
Phase 7: Request/Response schemas for smart notes
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Literal
from datetime import datetime


class SmartNoteCreate(BaseModel):
    """Request to create a note"""
    title: str = Field(..., min_length=1, max_length=300)
    content: str = Field(..., min_length=1)
    linked_entity_type: Optional[Literal["subject", "case", "learn", "practice"]] = None
    linked_entity_id: Optional[int] = Field(None, gt=0)
    tags: Optional[List[str]] = Field(default_factory=list, max_items=10)
    importance: Literal["low", "medium", "high"] = "medium"
    is_pinned: bool = False
    
    @validator('tags')
    def validate_tags(cls, v):
        if v:
            # Normalize tags: lowercase, strip whitespace, max length
            return [tag.lower().strip()[:30] for tag in v if tag.strip()]
        return []
    
    @validator('linked_entity_id')
    def validate_entity_link(cls, v, values):
        entity_type = values.get('linked_entity_type')
        if entity_type and not v:
            raise ValueError("linked_entity_id required when linked_entity_type is set")
        if v and not entity_type:
            raise ValueError("linked_entity_type required when linked_entity_id is set")
        return v


class SmartNoteUpdate(BaseModel):
    """Request to update a note"""
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    content: Optional[str] = Field(None, min_length=1)
    tags: Optional[List[str]] = Field(None, max_items=10)
    importance: Optional[Literal["low", "medium", "high"]] = None
    is_pinned: Optional[bool] = None
    
    @validator('tags')
    def validate_tags(cls, v):
        if v is not None:
            return [tag.lower().strip()[:30] for tag in v if tag.strip()]
        return v


class SmartNoteResponse(BaseModel):
    """Note response with metadata"""
    id: int
    user_id: int
    title: str
    content: str
    linked_entity_type: Optional[str]
    linked_entity_id: Optional[int]
    tags: List[str]
    importance: str
    is_pinned: bool
    created_at: str
    updated_at: str
    
    # Enriched metadata (optional)
    entity_title: Optional[str] = None
    entity_subtitle: Optional[str] = None
    
    class Config:
        from_attributes = True


class SmartNoteListResponse(BaseModel):
    """Paginated notes list"""
    notes: List[SmartNoteResponse]
    total_count: int
    page: int
    page_size: int
    has_more: bool


class AIAssistRequest(BaseModel):
    """Request for AI note assistance"""
    note_id: int
    action: Literal["summarize", "exam_format", "revision_bullets"]


class AIAssistResponse(BaseModel):
    """AI assistance response"""
    note_id: int
    action: str
    result: str
    original_preserved: bool = True  # Always true - we never modify original
