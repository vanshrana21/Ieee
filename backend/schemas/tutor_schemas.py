"""
backend/schemas/tutor_schemas.py
Phase 9A: Tutor API request/response schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ChatContext(BaseModel):
    """Optional context for chat requests"""
    subject_id: Optional[int] = Field(None, description="Filter to specific subject")
    previous_turns: Optional[int] = Field(3, ge=0, le=10, description="Number of previous messages to include")


class ChatRequest(BaseModel):
    """Request to chat with AI tutor"""
    session_id: Optional[str] = Field(None, max_length=50, description="Existing session ID or null for new")
    input: str = Field(..., min_length=1, max_length=2000, description="User's question")
    context: Optional[ChatContext] = Field(default_factory=ChatContext, description="Optional context filters")
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "input": "Explain Article 21 in simple words",
                "context": {
                    "subject_id": 5,
                    "previous_turns": 3
                }
            }
        }


class ProvenanceItem(BaseModel):
    """Source document used in response"""
    doc_id: int = Field(..., description="Document ID")
    doc_type: str = Field(..., description="Document type: learn, case, or note")
    score: float = Field(..., ge=0.0, le=1.0, description="Similarity score")
    snippet: str = Field(..., description="Relevant snippet from document")
    title: Optional[str] = Field(None, description="Document title")


class ChatResponse(BaseModel):
    """Response from AI tutor"""
    message_id: int = Field(..., description="Database ID of this message")
    session_id: str = Field(..., description="Session ID for continuity")
    content: str = Field(..., description="Tutor's response")
    provenance: List[ProvenanceItem] = Field(default_factory=list, description="Source documents")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Response confidence")
    timestamp: str = Field(..., description="ISO timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message_id": 42,
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "content": "Article 21 guarantees the right to life and personal liberty...",
                "provenance": [
                    {
                        "doc_id": 15,
                        "doc_type": "learn",
                        "score": 0.92,
                        "snippet": "Article 21: Right to life and personal liberty",
                        "title": "Fundamental Rights"
                    }
                ],
                "confidence_score": 0.89,
                "timestamp": "2026-01-13T18:30:00Z"
            }
        }


class SessionHistoryResponse(BaseModel):
    """Chat history for a session"""
    session_id: str
    message_count: int
    messages: List[Dict[str, Any]]
    last_activity: str
