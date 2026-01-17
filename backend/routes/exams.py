"""
backend/routes/exams.py
Phase 7.1: Exam Blueprint API Routes

Provides endpoints for deterministic exam blueprint generation.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.services.exam_blueprint_service import (
    generate_exam_blueprint,
    ExamType,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exams", tags=["exams"])

class BlueprintQuestionResponse(BaseModel):
    question_id: int
    text_preview: str
    marks: int
    type: str
    topic_tag: str
    why_selected: str
    mastery_reference: str
    syllabus_reference: str

class BlueprintSectionResponse(BaseModel):
    section: str
    instructions: str
    questions: List[BlueprintQuestionResponse]

class ExamBlueprintResponse(BaseModel):
    exam_type: str
    total_marks: int
    assigned_marks: int
    duration_minutes: int
    sections: List[BlueprintSectionResponse]
    metadata: Dict[str, Any]

@router.get("/blueprint", response_model=ExamBlueprintResponse)
async def get_exam_blueprint(
    exam_type: ExamType = Query(default=ExamType.MOCK),
    subject_id: Optional[int] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate a deterministic exam blueprint for a student.
    
    The blueprint mirrors real Indian law university exam structures 
    and prioritizes weak/medium topics.
    
    Query Params:
    - exam_type: internal_assessment, end_semester, unit_test, mock_exam
    - subject_id: Optional ID to restrict blueprint to one subject
    """
    try:
        blueprint = await generate_exam_blueprint(
            user_id=current_user.id,
            exam_type=exam_type,
            subject_id=subject_id,
            db=db
        )
        return ExamBlueprintResponse(**blueprint)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"Failed to generate exam blueprint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while generating blueprint"
        )

@router.get("/types")
async def get_exam_types():
    """
    Get all supported exam types with descriptions.
    """
    return {
        "exam_types": [
            {
                "type": ExamType.INTERNAL.value,
                "label": "Internal Assessment",
                "description": "Short mid-term assessment (25 marks, 60 mins)"
            },
            {
                "type": ExamType.END_SEM.value,
                "label": "End-Semester Exam",
                "description": "Full comprehensive exam (80 marks, 180 mins)"
            },
            {
                "type": ExamType.UNIT_TEST.value,
                "label": "Unit Test",
                "description": "Focus on specific units (15 marks, 45 mins)"
            },
            {
                "type": ExamType.MOCK.value,
                "label": "Mock Exam",
                "description": "Full-length practice exam (80 marks, 180 mins)"
            }
        ]
    }
