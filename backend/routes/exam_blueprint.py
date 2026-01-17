"""
backend/routes/exam_blueprint.py
Phase 7.1: Exam Blueprint API Routes

Provides endpoints for generating exam-accurate blueprints.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.services.exam_blueprint_service import (
    generate_exam_blueprint,
    get_available_exam_types,
    validate_blueprint,
    ExamType,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exams", tags=["exams"])


class BlueprintQuestionResponse(BaseModel):
    question_id: int
    question_text: str
    marks: int
    type: str
    topic_tag: str
    subject_id: int
    subject_name: str
    difficulty: str
    why_selected: str
    mastery_reference: float
    syllabus_reference: str


class BlueprintSectionResponse(BaseModel):
    section: str
    instructions: str
    marks_per_question: int
    total_marks: int
    question_count: int
    questions: List[BlueprintQuestionResponse]


class CoverageSummaryResponse(BaseModel):
    topics_covered: int = 0
    topic_distribution: Dict[str, int] = {}
    question_types: Dict[str, int] = {}
    subjects_covered: int = 0
    weak_topics_targeted: int = 0
    total_questions: int = 0


class ExamBlueprintResponse(BaseModel):
    exam_type: str
    subject_id: Optional[int]
    subject_name: Optional[str]
    total_marks: int
    duration_minutes: int
    sections: List[BlueprintSectionResponse]
    generated_at: str
    user_id: int
    coverage_summary: Dict[str, Any]
    total_questions: int


class ExamTypeResponse(BaseModel):
    type: str
    display_name: str
    total_marks: int
    duration_minutes: int
    description: str


class ValidationResponse(BaseModel):
    is_valid: bool
    issues: List[str]
    warnings: List[str]
    question_count: int
    sections_count: int


@router.get("/blueprint", response_model=ExamBlueprintResponse)
async def get_exam_blueprint(
    exam_type: str = Query(default="mock_exam", description="Type of exam"),
    subject_id: Optional[int] = Query(default=None, description="Specific subject ID (optional)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate an exam blueprint.
    
    The blueprint:
    - Mirrors real Indian law exam structure
    - Prioritizes weak topics
    - Balances conceptual + application questions
    - Is deterministic (same inputs = same output)
    
    Every question includes:
    - why_selected: Explanation for selection
    - mastery_reference: User's mastery level
    - syllabus_reference: Subject/module path
    
    Exam Types:
    - internal_assessment: 30 marks, 60 minutes
    - end_semester: 80 marks, 180 minutes
    - unit_test: 20 marks, 45 minutes
    - mock_exam: 80 marks, 180 minutes (default)
    """
    try:
        try:
            exam_type_enum = ExamType(exam_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid exam_type. Valid options: {[e.value for e in ExamType]}"
            )
        
        blueprint = await generate_exam_blueprint(
            user_id=current_user.id,
            db=db,
            exam_type=exam_type_enum,
            subject_id=subject_id
        )
        
        return ExamBlueprintResponse(**blueprint.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Blueprint generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate exam blueprint"
        )


@router.get("/blueprint/validate")
async def validate_exam_blueprint(
    exam_type: str = Query(default="mock_exam"),
    subject_id: Optional[int] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate and validate an exam blueprint.
    
    Returns validation report with:
    - is_valid: Whether blueprint meets minimum requirements
    - issues: Critical problems that prevent exam use
    - warnings: Non-critical suggestions for improvement
    """
    try:
        try:
            exam_type_enum = ExamType(exam_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid exam_type"
            )
        
        blueprint = await generate_exam_blueprint(
            user_id=current_user.id,
            db=db,
            exam_type=exam_type_enum,
            subject_id=subject_id
        )
        
        validation = await validate_blueprint(blueprint)
        
        return {
            "blueprint_summary": {
                "exam_type": blueprint.exam_type.value,
                "total_marks": blueprint.total_marks,
                "total_questions": blueprint.coverage_summary.get("total_questions", 0),
            },
            "validation": validation,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Blueprint validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate blueprint"
        )


@router.get("/types", response_model=List[ExamTypeResponse])
async def list_exam_types():
    """
    Get all available exam types with their configurations.
    
    Returns:
    - type: Exam type identifier
    - display_name: Human-readable name
    - total_marks: Maximum marks
    - duration_minutes: Time allowed
    - description: Brief description
    """
    return await get_available_exam_types()


@router.get("/blueprint/subject/{subject_id}", response_model=ExamBlueprintResponse)
async def get_subject_blueprint(
    subject_id: int,
    exam_type: str = Query(default="mock_exam"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate an exam blueprint for a specific subject.
    
    Questions are selected only from the specified subject.
    """
    try:
        try:
            exam_type_enum = ExamType(exam_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid exam_type"
            )
        
        blueprint = await generate_exam_blueprint(
            user_id=current_user.id,
            db=db,
            exam_type=exam_type_enum,
            subject_id=subject_id
        )
        
        if not blueprint.sections or all(len(s.questions) == 0 for s in blueprint.sections):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No questions available for subject {subject_id}. Add practice content first."
            )
        
        return ExamBlueprintResponse(**blueprint.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Subject blueprint generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate subject blueprint"
        )


@router.get("/blueprint/preview")
async def preview_blueprint_structure(
    exam_type: str = Query(default="mock_exam"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a lightweight preview of blueprint structure without full questions.
    
    Useful for showing exam structure before generation.
    """
    try:
        try:
            exam_type_enum = ExamType(exam_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid exam_type"
            )
        
        blueprint = await generate_exam_blueprint(
            user_id=current_user.id,
            db=db,
            exam_type=exam_type_enum
        )
        
        sections_preview = []
        for section in blueprint.sections:
            sections_preview.append({
                "section": section.section,
                "marks_per_question": section.marks_per_question,
                "question_count": len(section.questions),
                "total_marks": section.total_marks,
                "topics": list(set(q.topic_tag for q in section.questions))[:5],
            })
        
        return {
            "exam_type": blueprint.exam_type.value,
            "total_marks": blueprint.total_marks,
            "duration_minutes": blueprint.duration_minutes,
            "total_questions": sum(len(s.questions) for s in blueprint.sections),
            "sections": sections_preview,
            "coverage": {
                "topics_covered": blueprint.coverage_summary.get("topics_covered", 0),
                "subjects_covered": blueprint.coverage_summary.get("subjects_covered", 0),
                "weak_topics_targeted": blueprint.coverage_summary.get("weak_topics_targeted", 0),
            },
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Blueprint preview failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate blueprint preview"
        )
