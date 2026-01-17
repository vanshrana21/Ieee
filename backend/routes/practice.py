"""
backend/routes/practice.py
Practice Mode API - Phase 3.3

Module-aware practice mode for Indian law students.
Serves MCQs and short answers from database, auto-grades MCQs,
and feeds mastery analytics engine.
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from pydantic import BaseModel

from backend.database import get_db
from backend.orm.user import User
from backend.orm.content_module import ContentModule, ModuleType
from backend.orm.practice_question import PracticeQuestion, QuestionType, Difficulty
from backend.routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/practice", tags=["Practice Mode"])


class PracticeQuestionResponse(BaseModel):
    id: int
    type: str
    question: str
    options: Optional[List[str]] = None
    topic_tag: Optional[str] = None
    difficulty: str


class ModuleInfo(BaseModel):
    id: int
    title: str
    subject_id: int


class PracticeModuleResponse(BaseModel):
    module: ModuleInfo
    questions: List[PracticeQuestionResponse]
    total_count: int


@router.get("/module/{module_id}", response_model=PracticeModuleResponse)
async def get_practice_questions_for_module(
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all practice questions for a module.
    
    Phase 3.3: Module-Aware Practice Mode
    
    Rules:
    - Returns ONLY active questions (all questions in DB are considered active)
    - Ordered by difficulty ASC (easy → medium → hard)
    - NO answers returned (use attempt endpoint for grading)
    - Returns empty list if no questions exist
    
    Returns:
        {
            "module": { "id", "title", "subject_id" },
            "questions": [...],
            "total_count": int
        }
    """
    logger.info(f"Practice fetch: module_id={module_id}, user={current_user.email}")
    
    stmt = (
        select(ContentModule)
        .options(joinedload(ContentModule.subject))
        .where(ContentModule.id == module_id)
    )
    result = await db.execute(stmt)
    module = result.scalar_one_or_none()
    
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found"
        )
    
    if module.module_type != ModuleType.PRACTICE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This module does not contain practice questions"
        )
    
    difficulty_order = {
        Difficulty.EASY: 1,
        Difficulty.MEDIUM: 2,
        Difficulty.HARD: 3
    }
    
    questions_stmt = (
        select(PracticeQuestion)
        .where(PracticeQuestion.module_id == module_id)
        .order_by(PracticeQuestion.difficulty, PracticeQuestion.order_index)
    )
    questions_result = await db.execute(questions_stmt)
    questions = questions_result.scalars().all()
    
    sorted_questions = sorted(
        questions, 
        key=lambda q: (difficulty_order.get(q.difficulty, 2), q.order_index)
    )
    
    formatted_questions = []
    for q in sorted_questions:
        options = None
        if q.question_type == QuestionType.MCQ:
            options = [q.option_a, q.option_b, q.option_c, q.option_d]
            options = [opt for opt in options if opt]
        
        topic_tag = q.tags.split(",")[0].strip() if q.tags else None
        
        formatted_questions.append(PracticeQuestionResponse(
            id=q.id,
            type=q.question_type.value if q.question_type else "mcq",
            question=q.question,
            options=options,
            topic_tag=topic_tag,
            difficulty=q.difficulty.value if q.difficulty else "medium"
        ))
    
    logger.info(f"Practice fetch complete: {len(formatted_questions)} questions for module {module_id}")
    
    return PracticeModuleResponse(
        module=ModuleInfo(
            id=module.id,
            title=module.title,
            subject_id=module.subject_id
        ),
        questions=formatted_questions,
        total_count=len(formatted_questions)
    )
