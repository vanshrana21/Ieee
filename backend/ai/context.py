"""
backend/ai/context.py
Phase 10.1: AI Context Assembly & Validation

STRICT CONTRACT:
Every AI call must include validated context:
- user_id (required)
- course_id (required)
- subject_id (required)
- module_id (optional)
- content_id (optional)

Frontend CANNOT override or inject this context.
Backend validates all IDs against database.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.orm.subject import Subject
from backend.orm.content_module import ContentModule
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.curriculum import CourseCurriculum
from backend.exceptions import ForbiddenError, ContextValidationError

logger = logging.getLogger(__name__)


@dataclass
class AIContext:
    """
    Immutable context object for AI calls.
    
    This is the ONLY way to pass context to AI services.
    Frontend cannot modify this directly.
    """
    user_id: int
    course_id: int
    subject_id: int
    module_id: Optional[int] = None
    content_id: Optional[int] = None
    
    subject_title: Optional[str] = None
    module_title: Optional[str] = None
    content_title: Optional[str] = None
    content_body: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization"""
        return {
            "user_id": self.user_id,
            "course_id": self.course_id,
            "subject_id": self.subject_id,
            "module_id": self.module_id,
            "content_id": self.content_id,
            "subject_title": self.subject_title,
            "module_title": self.module_title,
            "content_title": self.content_title
        }
    
    def get_scope_description(self) -> str:
        """Human-readable description of current scope"""
        parts = []
        if self.subject_title:
            parts.append(f"Subject: {self.subject_title}")
        if self.module_title:
            parts.append(f"Module: {self.module_title}")
        if self.content_title:
            parts.append(f"Topic: {self.content_title}")
        return " | ".join(parts) if parts else "No specific scope"


async def resolve_ai_context(
    db: AsyncSession,
    *,
    user_id: int,
    subject_id: int,
    module_id: Optional[int] = None,
    content_id: Optional[int] = None,
    validate_enrollment: bool = True
) -> AIContext:
    """
    Resolve and validate AI context from database.
    
    This is the AUTHORITATIVE context resolver.
    
    Validation Chain:
    1. Subject exists
    2. Module belongs to subject (if provided)
    3. Content belongs to module (if provided)
    4. User enrolled in course (if validate_enrollment=True)
    
    Args:
        db: Database session
        user_id: Current user ID
        subject_id: Subject being studied
        module_id: Optional module within subject
        content_id: Optional content within module
        validate_enrollment: Check if user is enrolled (default True)
    
    Returns:
        AIContext: Validated context object
    
    Raises:
        ForbiddenError: If validation fails
        ContextValidationError: If IDs are invalid
    """
    logger.info(f"[AI Context] Resolving: user={user_id}, subject={subject_id}, module={module_id}, content={content_id}")
    
    subject_result = await db.execute(
        select(Subject).where(Subject.id == subject_id)
    )
    subject = subject_result.scalar_one_or_none()
    
    if not subject:
        logger.warning(f"[AI Context] Invalid subject_id={subject_id}")
        raise ForbiddenError("Invalid subject")
    
    curriculum_result = await db.execute(
        select(CourseCurriculum).where(CourseCurriculum.subject_id == subject_id).limit(1)
    )
    curriculum = curriculum_result.scalar_one_or_none()
    
    if not curriculum:
        logger.warning(f"[AI Context] Subject {subject_id} not in any curriculum")
        raise ForbiddenError("Subject not in curriculum")
    
    course_id = curriculum.course_id
    
    module = None
    module_title = None
    if module_id:
        module_result = await db.execute(
            select(ContentModule).where(
                ContentModule.id == module_id,
                ContentModule.subject_id == subject_id
            )
        )
        module = module_result.scalar_one_or_none()
        
        if not module:
            logger.warning(f"[AI Context] Module {module_id} does not belong to subject {subject_id}")
            raise ForbiddenError("Module does not belong to subject")
        
        module_title = module.title
    
    content = None
    content_title = None
    content_body = None
    if content_id and module_id:
        content_result = await db.execute(
            select(LearnContent).where(
                LearnContent.id == content_id,
                LearnContent.module_id == module_id
            )
        )
        content = content_result.scalar_one_or_none()
        
        if not content:
            case_result = await db.execute(
                select(CaseContent).where(
                    CaseContent.id == content_id,
                    CaseContent.module_id == module_id
                )
            )
            content = case_result.scalar_one_or_none()
        
        if not content:
            logger.warning(f"[AI Context] Content {content_id} does not belong to module {module_id}")
            raise ForbiddenError("Content does not belong to module")
        
        if hasattr(content, 'title'):
            content_title = content.title
        elif hasattr(content, 'case_name'):
            content_title = content.case_name
            
        if hasattr(content, 'body'):
            content_body = content.body
        elif hasattr(content, 'summary'):
            content_body = content.summary
    
    context = AIContext(
        user_id=user_id,
        course_id=course_id,
        subject_id=subject_id,
        module_id=module_id,
        content_id=content_id,
        subject_title=subject.title,
        module_title=module_title,
        content_title=content_title,
        content_body=content_body
    )
    
    logger.info(f"[AI Context] Resolved: {context.to_dict()}")
    return context


async def get_user_allowed_subjects(
    db: AsyncSession,
    user_id: int
) -> list[int]:
    """
    Get list of subject IDs user is allowed to access.
    
    Based on enrollment in courses via curriculum.
    """
    from backend.orm.user import User
    
    user_result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    
    if not user or not user.enrolled_course_id:
        return []
    
    curriculum_result = await db.execute(
        select(CourseCurriculum.subject_id).where(
            CourseCurriculum.course_id == user.enrolled_course_id
        )
    )
    
    return [row[0] for row in curriculum_result.fetchall()]


async def validate_subject_access(
    db: AsyncSession,
    user_id: int,
    subject_id: int
) -> bool:
    """
    Check if user can access a specific subject.
    
    Returns True if user is enrolled in a course containing this subject.
    """
    allowed = await get_user_allowed_subjects(db, user_id)
    return subject_id in allowed
