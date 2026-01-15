"""
backend/routes/bookmarks.py
Phase 6.2: Bookmark Management API
Handles creation, retrieval, and deletion of user bookmarks
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, delete
from sqlalchemy.orm import selectinload
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime

from backend.database import get_db
from backend.orm.user import User
from backend.orm.bookmark import Bookmark
from backend.orm.subject import Subject
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion
from backend.orm.content_module import ContentModule
from backend.routes.auth import get_current_user

router = APIRouter(prefix="/api/bookmarks", tags=["bookmarks"])

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class BookmarkCreate(BaseModel):
    """Request to create a bookmark"""
    content_type: Literal["subject", "learn", "case", "practice"]
    content_id: int = Field(..., gt=0)
    note: Optional[str] = Field(None, max_length=500)


class BookmarkResponse(BaseModel):
    """Bookmark with enriched content data"""
    id: int
    content_type: str
    content_id: int
    note: Optional[str]
    created_at: str
    
    # Enriched content metadata
    title: str
    subject_code: Optional[str] = None
    subject_name: Optional[str] = None
    semester: Optional[int] = None
    
    # Type-specific fields
    case_citation: Optional[str] = None
    case_year: Optional[int] = None
    exam_importance: Optional[str] = None
    difficulty: Optional[str] = None
    question_type: Optional[str] = None

    class Config:
        from_attributes = True


class BookmarkListResponse(BaseModel):
    """Paginated bookmark list"""
    bookmarks: List[BookmarkResponse]
    total_count: int
    page: int
    page_size: int
    has_more: bool


# ============================================================================
# BOOKMARK CRUD OPERATIONS
# ============================================================================

@router.post("", response_model=BookmarkResponse, status_code=201)
async def create_bookmark(
    bookmark_data: BookmarkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new bookmark.
    
    Security:
    - Validates content exists and is accessible to user
    - Enforces course/semester restrictions
    - Prevents duplicate bookmarks (idempotent)
    """
    
    # Verify user is enrolled
    if not current_user.course_id or not current_user.current_semester:
        raise HTTPException(
            status_code=403,
            detail="You must be enrolled to create bookmarks"
        )
    
    # Validate content exists and is accessible
    content_metadata = await _validate_and_get_content(
        db=db,
        content_type=bookmark_data.content_type,
        content_id=bookmark_data.content_id,
        user=current_user
    )
    
    if not content_metadata:
        raise HTTPException(
            status_code=404,
            detail=f"{bookmark_data.content_type.capitalize()} not found or not accessible"
        )
    
    # Check if bookmark already exists (idempotent)
    existing = await db.execute(
        select(Bookmark).where(
            and_(
                Bookmark.user_id == current_user.id,
                Bookmark.content_type == bookmark_data.content_type,
                Bookmark.content_id == bookmark_data.content_id
            )
        )
    )
    existing_bookmark = existing.scalar_one_or_none()
    
    if existing_bookmark:
        # Update note if provided
        if bookmark_data.note:
            existing_bookmark.note = bookmark_data.note
            await db.commit()
            await db.refresh(existing_bookmark)
        
        # Return existing bookmark
        return _enrich_bookmark_response(existing_bookmark, content_metadata)
    
    # Create new bookmark
    new_bookmark = Bookmark(
        user_id=current_user.id,
        content_type=bookmark_data.content_type,
        content_id=bookmark_data.content_id,
        note=bookmark_data.note
    )
    
    db.add(new_bookmark)
    await db.commit()
    await db.refresh(new_bookmark)
    
    return _enrich_bookmark_response(new_bookmark, content_metadata)


@router.delete("/{bookmark_id}", status_code=204)
async def delete_bookmark(
    bookmark_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a bookmark.
    
    Security:
    - Only owner can delete
    - 404 if not found or not owned by user
    """
    
    result = await db.execute(
        select(Bookmark).where(
            and_(
                Bookmark.id == bookmark_id,
                Bookmark.user_id == current_user.id
            )
        )
    )
    bookmark = result.scalar_one_or_none()
    
    if not bookmark:
        raise HTTPException(
            status_code=404,
            detail="Bookmark not found"
        )
    
    await db.delete(bookmark)
    await db.commit()
    
    return None


@router.delete("", status_code=204)
async def delete_bookmark_by_content(
    content_type: Literal["subject", "learn", "case", "practice"] = Query(...),
    content_id: int = Query(..., gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete bookmark by content reference.
    
    Useful for toggle functionality in UI.
    """
    
    await db.execute(
        delete(Bookmark).where(
            and_(
                Bookmark.user_id == current_user.id,
                Bookmark.content_type == content_type,
                Bookmark.content_id == content_id
            )
        )
    )
    await db.commit()
    
    return None


@router.get("", response_model=BookmarkListResponse)
async def list_bookmarks(
    content_type: Optional[str] = Query(None, description="Filter by content type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List user's bookmarks with pagination.
    
    Security:
    - Only returns user's own bookmarks
    - Filters out locked/inaccessible content
    - Enriches with current content metadata
    """
    
    # Build query
    query = select(Bookmark).where(Bookmark.user_id == current_user.id)
    
    if content_type:
        query = query.where(Bookmark.content_type == content_type)
    
    query = query.order_by(Bookmark.created_at.desc())
    
    # Get total count
    count_result = await db.execute(
        select(Bookmark).where(Bookmark.user_id == current_user.id)
    )
    total_count = len(count_result.all())
    
    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    result = await db.execute(query)
    bookmarks = result.scalars().all()
    
    # Enrich bookmarks with content metadata
    enriched_bookmarks = []
    for bookmark in bookmarks:
        content_metadata = await _validate_and_get_content(
            db=db,
            content_type=bookmark.content_type,
            content_id=bookmark.content_id,
            user=current_user,
            skip_access_check=False  # Still check access
        )
        
        # Skip if content no longer accessible (locked/deleted)
        if not content_metadata:
            continue
        
        enriched_bookmarks.append(
            _enrich_bookmark_response(bookmark, content_metadata)
        )
    
    return BookmarkListResponse(
        bookmarks=enriched_bookmarks,
        total_count=len(enriched_bookmarks),  # Actual accessible count
        page=page,
        page_size=page_size,
        has_more=(offset + page_size) < total_count
    )


@router.get("/check")
async def check_bookmark(
    content_type: Literal["subject", "learn", "case", "practice"] = Query(...),
    content_id: int = Query(..., gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check if content is bookmarked.
    
    Returns: {"is_bookmarked": true/false, "bookmark_id": int or null}
    """
    
    result = await db.execute(
        select(Bookmark).where(
            and_(
                Bookmark.user_id == current_user.id,
                Bookmark.content_type == content_type,
                Bookmark.content_id == content_id
            )
        )
    )
    bookmark = result.scalar_one_or_none()
    
    return {
        "is_bookmarked": bookmark is not None,
        "bookmark_id": bookmark.id if bookmark else None
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def _validate_and_get_content(
    db: AsyncSession,
    content_type: str,
    content_id: int,
    user: User,
    skip_access_check: bool = False
) -> Optional[dict]:
    """
    Validate content exists and user has access.
    Returns metadata dict or None if invalid.
    """
    
    try:
        if content_type == "subject":
            # Check subject exists in user's course and accessible semester
            stmt = select(Subject).join(
                "curriculum"
            ).where(
                and_(
                    Subject.id == content_id,
                    "CourseCurriculum.course_id" == user.course_id,
                    "CourseCurriculum.semester" <= user.current_semester
                )
            )
            
            result = await db.execute(stmt)
            subject = result.scalar_one_or_none()
            
            if not subject:
                return None
            
            # Get semester from curriculum
            curriculum_stmt = select("CourseCurriculum").where(
                and_(
                    "CourseCurriculum.subject_id" == content_id,
                    "CourseCurriculum.course_id" == user.course_id
                )
            )
            curriculum_result = await db.execute(curriculum_stmt)
            curriculum = curriculum_result.scalar_one_or_none()
            
            return {
                "title": subject.title,
                "subject_code": subject.code,
                "subject_name": subject.title,
                "semester": curriculum.semester if curriculum else None
            }
        
        elif content_type == "learn":
            # Join through module to subject
            stmt = select(LearnContent, Subject, ContentModule).join(
                ContentModule, LearnContent.module_id == ContentModule.id
            ).join(
                Subject, ContentModule.subject_id == Subject.id
            ).join(
                "curriculum"
            ).where(
                and_(
                    LearnContent.id == content_id,
                    "CourseCurriculum.course_id" == user.course_id,
                    "CourseCurriculum.semester" <= user.current_semester,
                    ContentModule.is_locked == False
                )
            )
            
            result = await db.execute(stmt)
            row = result.first()
            
            if not row:
                return None
            
            learn, subject, module = row
            
            return {
                "title": learn.title,
                "subject_code": subject.code,
                "subject_name": subject.title,
                "semester": None  # Get from curriculum if needed
            }
        
        elif content_type == "case":
            # Similar to learn content
            stmt = select(CaseContent, Subject, ContentModule).join(
                ContentModule, CaseContent.module_id == ContentModule.id
            ).join(
                Subject, ContentModule.subject_id == Subject.id
            ).join(
                "curriculum"
            ).where(
                and_(
                    CaseContent.id == content_id,
                    "CourseCurriculum.course_id" == user.course_id,
                    "CourseCurriculum.semester" <= user.current_semester,
                    ContentModule.is_locked == False
                )
            )
            
            result = await db.execute(stmt)
            row = result.first()
            
            if not row:
                return None
            
            case, subject, module = row
            
            return {
                "title": case.case_name,
                "subject_code": subject.code,
                "subject_name": subject.title,
                "case_citation": case.citation,
                "case_year": case.year,
                "exam_importance": case.exam_importance,
                "semester": None
            }
        
        elif content_type == "practice":
            # Similar to learn content
            stmt = select(PracticeQuestion, Subject, ContentModule).join(
                ContentModule, PracticeQuestion.module_id == ContentModule.id
            ).join(
                Subject, ContentModule.subject_id == Subject.id
            ).join(
                "curriculum"
            ).where(
                and_(
                    PracticeQuestion.id == content_id,
                    "CourseCurriculum.course_id" == user.course_id,
                    "CourseCurriculum.semester" <= user.current_semester,
                    ContentModule.is_locked == False
                )
            )
            
            result = await db.execute(stmt)
            row = result.first()
            
            if not row:
                return None
            
            question, subject, module = row
            
            return {
                "title": f"Question: {question.question[:100]}...",
                "subject_code": subject.code,
                "subject_name": subject.title,
                "difficulty": question.difficulty,
                "question_type": question.question_type,
                "semester": None
            }
        
        else:
            return None
    
    except Exception as e:
        print(f"Error validating content: {e}")
        return None


def _enrich_bookmark_response(bookmark: Bookmark, metadata: dict) -> BookmarkResponse:
    """Combine bookmark with content metadata"""
    return BookmarkResponse(
        id=bookmark.id,
        content_type=bookmark.content_type,
        content_id=bookmark.content_id,
        note=bookmark.note,
        created_at=bookmark.created_at.isoformat(),
        **metadata
    )
