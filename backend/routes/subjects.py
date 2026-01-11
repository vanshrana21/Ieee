from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from backend.database import get_db
from backend.orm.models import Subject, SubjectCourse, SubjectSemester, get_subjects_for_course_semester
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.schemas import SubjectListResponse, SubjectResponse

router = APIRouter(prefix="/subjects", tags=["Subjects"])

@router.get("", response_model=SubjectListResponse)
async def list_subjects(
    course: Optional[str] = Query(None, description="Filter by course code"),
    semester: Optional[int] = Query(None, ge=1, le=10),
    category: Optional[str] = Query(None),
    status: str = Query("active", pattern="^(active|archived|draft)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List subjects with optional filters"""
    stmt = select(Subject).where(Subject.status == status)
    
    if course:
        stmt = stmt.join(SubjectCourse).where(SubjectCourse.course_code == course)
    if semester:
        stmt = stmt.join(SubjectSemester).where(SubjectSemester.semester == semester)
    if category:
        stmt = stmt.where(Subject.category == category)
    
    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()
    
    # Paginate
    stmt = stmt.offset((page - 1) * page_size).limit(page_size).order_by(Subject.name)
    result = await db.execute(stmt)
    subjects = result.scalars().all()
    
    return SubjectListResponse(
        total=total,
        page=page,
        page_size=page_size,
        subjects=[SubjectResponse.model_validate(s) for s in subjects]
    )

@router.get("/{subject_id}", response_model=SubjectResponse)
async def get_subject(subject_id: int, db: AsyncSession = Depends(get_db)):
    """Get subject by ID"""
    result = await db.execute(select(Subject).where(Subject.id == subject_id))
    subject = result.scalar_one_or_none()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return SubjectResponse.model_validate(subject)