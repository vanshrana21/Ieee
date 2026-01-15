"""
backend/services/search_service.py
Phase 6.1/6.2: Reusable search logic
Shared by search routes and saved search execution
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from typing import List, Optional, Dict, Any
from backend.orm.user import User
from backend.orm.subject import Subject
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion
from backend.orm.content_module import ContentModule
from backend.orm.curriculum import CourseCurriculum


async def execute_search(
    q: str,
    content_types: Optional[List[str]],
    subject_id: Optional[int],
    semester: Optional[int],
    page: int,
    page_size: int,
    db: AsyncSession,
    current_user: User
) -> Dict[str, Any]:
    """
    Execute search across content types with access control.
    
    Args:
        q: Search query string
        content_types: List of content types to search (subject, learn, case, practice)
        subject_id: Optional subject filter
        semester: Optional semester filter
        page: Page number (1-indexed)
        page_size: Results per page
        db: Database session
        current_user: Authenticated user
    
    Returns:
        Dict with keys: results, total_count, page, page_size, has_more
    
    Security:
        - Only searches user's enrolled course
        - Only searches accessible semesters (≤ current_semester)
        - Excludes locked modules
    """
    
    # Verify enrollment
    if not current_user.course_id or not current_user.current_semester:
        return {
            "results": [],
            "total_count": 0,
            "page": page,
            "page_size": page_size,
            "has_more": False
        }
    
    # Parse content types
    allowed_types = {"subject", "learn", "case", "practice"}
    if content_types:
        search_types = set(content_types) & allowed_types
    else:
        search_types = allowed_types
    
    # Build search pattern
    search_pattern = f"%{q}%"
    
    all_results = []
    
    # Search Subjects
    if "subject" in search_types:
        subject_stmt = select(Subject, CourseCurriculum).join(
            CourseCurriculum, Subject.id == CourseCurriculum.subject_id
        ).where(
            and_(
                CourseCurriculum.course_id == current_user.course_id,
                CourseCurriculum.semester <= current_user.current_semester,
                or_(
                    Subject.title.ilike(search_pattern),
                    Subject.code.ilike(search_pattern),
                    Subject.description.ilike(search_pattern)
                )
            )
        )
        
        if subject_id:
            subject_stmt = subject_stmt.where(Subject.id == subject_id)
        if semester:
            subject_stmt = subject_stmt.where(CourseCurriculum.semester == semester)
        
        subject_results = await db.execute(subject_stmt)
        for subj, curr in subject_results.all():
            all_results.append({
                "id": subj.id,
                "content_type": "subject",
                "title": subj.title,
                "description": subj.description,
                "subject_code": subj.code,
                "subject_name": subj.title,
                "semester": curr.semester
            })
    
    # Search Learn Content
    if "learn" in search_types:
        learn_stmt = select(LearnContent, Subject, ContentModule, CourseCurriculum).join(
            ContentModule, LearnContent.module_id == ContentModule.id
        ).join(
            Subject, ContentModule.subject_id == Subject.id
        ).join(
            CourseCurriculum, Subject.id == CourseCurriculum.subject_id
        ).where(
            and_(
                CourseCurriculum.course_id == current_user.course_id,
                CourseCurriculum.semester <= current_user.current_semester,
                ContentModule.is_locked == False,
                or_(
                    LearnContent.title.ilike(search_pattern),
                    LearnContent.summary.ilike(search_pattern)
                )
            )
        )
        
        if subject_id:
            learn_stmt = learn_stmt.where(Subject.id == subject_id)
        if semester:
            learn_stmt = learn_stmt.where(CourseCurriculum.semester == semester)
        
        learn_results = await db.execute(learn_stmt)
        for learn, subj, mod, curr in learn_results.all():
            all_results.append({
                "id": learn.id,
                "content_type": "learn",
                "title": learn.title,
                "description": learn.summary,
                "subject_code": subj.code,
                "subject_name": subj.title,
                "semester": curr.semester,
                "module_id": mod.id,
                "module_title": mod.title,
                "tags": learn.tags
            })
    
    # Search Case Content
    if "case" in search_types:
        case_stmt = select(CaseContent, Subject, ContentModule, CourseCurriculum).join(
            ContentModule, CaseContent.module_id == ContentModule.id
        ).join(
            Subject, ContentModule.subject_id == Subject.id
        ).join(
            CourseCurriculum, Subject.id == CourseCurriculum.subject_id
        ).where(
            and_(
                CourseCurriculum.course_id == current_user.course_id,
                CourseCurriculum.semester <= current_user.current_semester,
                ContentModule.is_locked == False,
                or_(
                    CaseContent.case_name.ilike(search_pattern),
                    CaseContent.citation.ilike(search_pattern),
                    CaseContent.summary.ilike(search_pattern)
                )
            )
        )
        
        if subject_id:
            case_stmt = case_stmt.where(Subject.id == subject_id)
        if semester:
            case_stmt = case_stmt.where(CourseCurriculum.semester == semester)
        
        case_results = await db.execute(case_stmt)
        for case, subj, mod, curr in case_results.all():
            all_results.append({
                "id": case.id,
                "content_type": "case",
                "title": case.case_name,
                "description": case.summary,
                "subject_code": subj.code,
                "subject_name": subj.title,
                "semester": curr.semester,
                "module_id": mod.id,
                "module_title": mod.title,
                "case_citation": case.citation,
                "case_year": case.year,
                "exam_importance": case.exam_importance,
                "tags": case.tags
            })
    
    # Search Practice Questions
    if "practice" in search_types:
        practice_stmt = select(PracticeQuestion, Subject, ContentModule, CourseCurriculum).join(
            ContentModule, PracticeQuestion.module_id == ContentModule.id
        ).join(
            Subject, ContentModule.subject_id == Subject.id
        ).join(
            CourseCurriculum, Subject.id == CourseCurriculum.subject_id
        ).where(
            and_(
                CourseCurriculum.course_id == current_user.course_id,
                CourseCurriculum.semester <= current_user.current_semester,
                ContentModule.is_locked == False,
                PracticeQuestion.question.ilike(search_pattern)
            )
        )
        
        if subject_id:
            practice_stmt = practice_stmt.where(Subject.id == subject_id)
        if semester:
            practice_stmt = practice_stmt.where(CourseCurriculum.semester == semester)
        
        practice_results = await db.execute(practice_stmt)
        for question, subj, mod, curr in practice_results.all():
            all_results.append({
                "id": question.id,
                "content_type": "practice",
                "title": f"Question: {question.question[:100]}...",
                "description": question.question[:200],
                "subject_code": subj.code,
                "subject_name": subj.title,
                "semester": curr.semester,
                "module_id": mod.id,
                "module_title": mod.title,
                "question_type": question.question_type,
                "difficulty": question.difficulty,
                "marks": question.marks,
                "tags": question.tags
            })
    
    # Pagination
    total_count = len(all_results)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_results = all_results[start_idx:end_idx]
    
    return {
        "results": paginated_results,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "has_more": end_idx < total_count
    }
