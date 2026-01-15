"""
backend/routes/search.py
Phase 6.1: Search, Filtering & Discovery
Unified search endpoint with access control
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.orm.user import User
from backend.orm.subject import Subject
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion
from backend.orm.content_module import ContentModule

router = APIRouter(prefix="/api/search", tags=["search"])

# ============================================================================
# RESPONSE MODELS
# ============================================================================

class SearchResultItem(BaseModel):
    """Unified search result item"""
    id: int
    content_type: Literal["subject", "learn", "case", "practice"]
    title: str
    description: Optional[str] = None
    subject_code: Optional[str] = None
    subject_name: Optional[str] = None
    semester: Optional[int] = None
    module_id: Optional[int] = None
    module_title: Optional[str] = None
    
    # Type-specific fields
    case_citation: Optional[str] = None
    case_year: Optional[int] = None
    exam_importance: Optional[str] = None
    question_type: Optional[str] = None
    difficulty: Optional[str] = None
    marks: Optional[int] = None
    tags: Optional[List[str]] = None

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    """Paginated search response"""
    results: List[SearchResultItem]
    total_count: int
    page: int
    page_size: int
    has_more: bool


# ============================================================================
# SEARCH ENDPOINT
# ============================================================================

@router.get("", response_model=SearchResponse)
async def search_content(
    q: str = Query(..., min_length=2, max_length=200, description="Search query"),
    content_types: Optional[str] = Query(
        None, 
        description="Comma-separated content types: subject,learn,case,practice"
    ),
    subject_id: Optional[int] = Query(None, description="Filter by subject ID"),
    semester: Optional[int] = Query(None, ge=1, le=10, description="Filter by semester"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Unified search endpoint across all content types.
    
    Security:
    - User must be enrolled (has course_id and current_semester)
    - Only returns content from user's course
    - Only returns content from unlocked semesters (≤ current_semester)
    - Respects module lock status
    
    Performance:
    - Uses indexed columns only (title, case_name, citation, tags)
    - Bounded by page_size (max 100)
    - Pagination required
    """
    
    # Verify enrollment
    if not current_user.course_id or not current_user.current_semester:
        raise HTTPException(
            status_code=403,
            detail="You must be enrolled in a course to use search"
        )
    
    # Parse content type filter
    allowed_types = {"subject", "learn", "case", "practice"}
    if content_types:
        requested_types = set(t.strip() for t in content_types.split(","))
        search_types = requested_types & allowed_types
    else:
        search_types = allowed_types
    
    # Build search pattern (case-insensitive)
    search_pattern = f"%{q}%"
    
    all_results = []
    
    # ========================================================================
    # SEARCH SUBJECTS
    # ========================================================================
    if "subject" in search_types:
        subject_query = db.query(Subject).filter(
            and_(
                Subject.course_id == current_user.course_id,
                Subject.semester <= current_user.current_semester,
                or_(
                    Subject.title.ilike(search_pattern),
                    Subject.code.ilike(search_pattern),
                    Subject.description.ilike(search_pattern)
                )
            )
        )
        
        # Apply subject filter if provided
        if subject_id:
            subject_query = subject_query.filter(Subject.id == subject_id)
        
        # Apply semester filter if provided
        if semester:
            subject_query = subject_query.filter(Subject.semester == semester)
        
        subjects = subject_query.all()
        
        for subj in subjects:
            all_results.append(SearchResultItem(
                id=subj.id,
                content_type="subject",
                title=subj.title,
                description=subj.description,
                subject_code=subj.code,
                subject_name=subj.title,
                semester=subj.semester
            ))
    
    # ========================================================================
    # SEARCH LEARN CONTENT
    # ========================================================================
    if "learn" in search_types:
        learn_query = db.query(
            LearnContent,
            Subject,
            ContentModule
        ).join(
            ContentModule, LearnContent.module_id == ContentModule.id
        ).join(
            Subject, ContentModule.subject_id == Subject.id
        ).filter(
            and_(
                Subject.course_id == current_user.course_id,
                Subject.semester <= current_user.current_semester,
                ContentModule.is_locked == False,
                or_(
                    LearnContent.title.ilike(search_pattern),
                    LearnContent.summary.ilike(search_pattern),
                    LearnContent.tags.contains([q.lower()])  # GIN index
                )
            )
        )
        
        # Apply filters
        if subject_id:
            learn_query = learn_query.filter(Subject.id == subject_id)
        if semester:
            learn_query = learn_query.filter(Subject.semester == semester)
        
        learn_results = learn_query.all()
        
        for learn, subj, module in learn_results:
            all_results.append(SearchResultItem(
                id=learn.id,
                content_type="learn",
                title=learn.title,
                description=learn.summary,
                subject_code=subj.code,
                subject_name=subj.title,
                semester=subj.semester,
                module_id=module.id,
                module_title=module.title,
                tags=learn.tags
            ))
    
    # ========================================================================
    # SEARCH CASE CONTENT
    # ========================================================================
    if "case" in search_types:
        case_query = db.query(
            CaseContent,
            Subject,
            ContentModule
        ).join(
            ContentModule, CaseContent.module_id == ContentModule.id
        ).join(
            Subject, ContentModule.subject_id == Subject.id
        ).filter(
            and_(
                Subject.course_id == current_user.course_id,
                Subject.semester <= current_user.current_semester,
                ContentModule.is_locked == False,
                or_(
                    CaseContent.case_name.ilike(search_pattern),
                    CaseContent.citation.ilike(search_pattern),
                    CaseContent.summary.ilike(search_pattern),
                    CaseContent.tags.contains([q.lower()])  # GIN index
                )
            )
        )
        
        # Apply filters
        if subject_id:
            case_query = case_query.filter(Subject.id == subject_id)
        if semester:
            case_query = case_query.filter(Subject.semester == semester)
        
        case_results = case_query.all()
        
        for case, subj, module in case_results:
            all_results.append(SearchResultItem(
                id=case.id,
                content_type="case",
                title=case.case_name,
                description=case.summary,
                subject_code=subj.code,
                subject_name=subj.title,
                semester=subj.semester,
                module_id=module.id,
                module_title=module.title,
                case_citation=case.citation,
                case_year=case.year,
                exam_importance=case.exam_importance,
                tags=case.tags
            ))
    
    # ========================================================================
    # SEARCH PRACTICE QUESTIONS
    # ========================================================================
    if "practice" in search_types:
        practice_query = db.query(
            PracticeQuestion,
            Subject,
            ContentModule
        ).join(
            ContentModule, PracticeQuestion.module_id == ContentModule.id
        ).join(
            Subject, ContentModule.subject_id == Subject.id
        ).filter(
            and_(
                Subject.course_id == current_user.course_id,
                Subject.semester <= current_user.current_semester,
                ContentModule.is_locked == False,
                or_(
                    PracticeQuestion.question.ilike(search_pattern),
                    PracticeQuestion.tags.contains([q.lower()])  # GIN index
                )
            )
        )
        
        # Apply filters
        if subject_id:
            practice_query = practice_query.filter(Subject.id == subject_id)
        if semester:
            practice_query = practice_query.filter(Subject.semester == semester)
        
        practice_results = practice_query.all()
        
        for question, subj, module in practice_results:
            all_results.append(SearchResultItem(
                id=question.id,
                content_type="practice",
                title=f"Question: {question.question[:100]}...",
                description=question.question[:200],
                subject_code=subj.code,
                subject_name=subj.title,
                semester=subj.semester,
                module_id=module.id,
                module_title=module.title,
                question_type=question.question_type,
                difficulty=question.difficulty,
                marks=question.marks,
                tags=question.tags
            ))
    
    # ========================================================================
    # PAGINATION
    # ========================================================================
    total_count = len(all_results)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_results = all_results[start_idx:end_idx]
    
    return SearchResponse(
        results=paginated_results,
        total_count=total_count,
        page=page,
        page_size=page_size,
        has_more=end_idx < total_count
    )
