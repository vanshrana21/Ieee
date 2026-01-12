"""
backend/routes/curriculum.py
Curriculum dashboard routes - Returns subjects based on user's course and semester

This module provides the core dashboard logic for JurisAI:
- Active subjects (current semester)
- Archive subjects (past semesters)
- Future subjects are NEVER returned (locked until user progresses)
"""
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from backend.database import get_db
from backend.orm.user import User
from backend.orm.course import Course
from backend.orm.curriculum import CourseCurriculum
from backend.orm.subject import Subject
from backend.routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/curriculum", tags=["Curriculum"])


# ================= HELPER FUNCTIONS =================

async def get_subjects_for_semester(
    db: AsyncSession,
    course_id: int,
    semester_number: int
) -> List[Dict[str, Any]]:
    """
    Fetch subjects for a specific course and semester.
    
    Args:
        db: Database session
        course_id: User's enrolled course ID
        semester_number: Semester to fetch subjects for
    
    Returns:
        List of subject dictionaries with curriculum metadata
    """
    # Query course_curriculum with joined subject data
    stmt = (
        select(CourseCurriculum)
        .options(joinedload(CourseCurriculum.subject))
        .where(
            CourseCurriculum.course_id == course_id,
            CourseCurriculum.semester_number == semester_number,
            CourseCurriculum.is_active == True
        )
        .order_by(
            CourseCurriculum.display_order,
            CourseCurriculum.id
        )
    )
    
    result = await db.execute(stmt)
    curriculum_items = result.scalars().all()
    
    # Transform to API response format
    subjects = []
    for item in curriculum_items:
        if item.subject:  # Ensure subject relationship is loaded
            subjects.append({
                "id": item.subject.id,
                "title": item.subject.title,
                "code": item.subject.code,
                "semester": item.semester_number,
                "category": item.subject.category.value if item.subject.category else None,
                "is_elective": item.is_elective,
                "description": item.subject.description,
            })
    
    return subjects


async def get_archive_subjects(
    db: AsyncSession,
    course_id: int,
    current_semester: int
) -> List[Dict[str, Any]]:
    """
    Fetch all subjects from past semesters (archive).
    
    Args:
        db: Database session
        course_id: User's enrolled course ID
        current_semester: User's current semester
    
    Returns:
        List of archived subjects grouped by semester (descending order)
    """
    # Query all past semesters
    stmt = (
        select(CourseCurriculum)
        .options(joinedload(CourseCurriculum.subject))
        .where(
            CourseCurriculum.course_id == course_id,
            CourseCurriculum.semester_number < current_semester,
            CourseCurriculum.is_active == True
        )
        .order_by(
            CourseCurriculum.semester_number.desc(),  # Most recent first
            CourseCurriculum.display_order,
            CourseCurriculum.id
        )
    )
    
    result = await db.execute(stmt)
    curriculum_items = result.scalars().all()
    
    # Transform to API response format
    subjects = []
    for item in curriculum_items:
        if item.subject:
            subjects.append({
                "id": item.subject.id,
                "title": item.subject.title,
                "code": item.subject.code,
                "semester": item.semester_number,
                "category": item.subject.category.value if item.subject.category else None,
                "is_elective": item.is_elective,
                "description": item.subject.description,
            })
    
    return subjects


# ================= API ROUTES =================

@router.get("/dashboard")
async def get_curriculum_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get curriculum dashboard for logged-in user.
    
    Returns subjects divided into:
    - active_subjects: Current semester subjects
    - archive_subjects: Past semester subjects
    - Future subjects are NOT returned (locked)
    
    Business Logic:
    1. User must be enrolled in a course (course_id not NULL)
    2. User must have a current_semester set
    3. Only returns subjects <= current_semester
    4. Subjects are fetched via course_curriculum mapping
    
    Response:
        {
            "course": {
                "id": 1,
                "name": "BA LLB",
                "code": "BA_LLB",
                "total_semesters": 10
            },
            "current_semester": 5,
            "active_subjects": [...],
            "archive_subjects": [...]
        }
    """
    logger.info(f"Dashboard request from user: {current_user.email}")
    
    # ========== VALIDATION ==========
    
    # Check if user has enrolled in a course
    if not current_user.course_id:
        logger.warning(f"User {current_user.email} has no enrolled course")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not enrolled in any course. Please complete enrollment first."
        )
    
    # Check if user has a current semester set
    if not current_user.current_semester:
        logger.warning(f"User {current_user.email} has no current_semester set")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current semester not set. Please contact administrator."
        )
    
    # ========== FETCH COURSE DETAILS ==========
    
    # Get user's enrolled course
    course_stmt = select(Course).where(Course.id == current_user.course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    
    if not course:
        logger.error(f"Course ID {current_user.course_id} not found for user {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrolled course not found in database"
        )
    
    # Validate semester number doesn't exceed course limit
    if current_user.current_semester > course.total_semesters:
        logger.warning(
            f"User {current_user.email} semester ({current_user.current_semester}) "
            f"exceeds course limit ({course.total_semesters})"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Current semester ({current_user.current_semester}) exceeds "
                   f"course duration ({course.total_semesters} semesters)"
        )
    
    # ========== FETCH SUBJECTS ==========
    
    # Get active subjects (current semester)
    active_subjects = await get_subjects_for_semester(
        db,
        current_user.course_id,
        current_user.current_semester
    )
    
    # Get archive subjects (past semesters)
    archive_subjects = await get_archive_subjects(
        db,
        current_user.course_id,
        current_user.current_semester
    )
    
    logger.info(
        f"Dashboard data prepared for {current_user.email}: "
        f"{len(active_subjects)} active, {len(archive_subjects)} archived"
    )
    
    # ========== RETURN RESPONSE ==========
    
    return {
        "course": {
            "id": course.id,
            "name": course.name,
            "code": course.code,
            "total_semesters": course.total_semesters,
            "duration_years": course.duration_years,
        },
        "current_semester": current_user.current_semester,
        "active_subjects": active_subjects,
        "archive_subjects": archive_subjects,
    }


@router.get("/subjects/{subject_id}")
async def get_subject_details(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a specific subject.
    
    Security:
    - User can only access subjects from their course
    - User can only access subjects from current or past semesters
    - Future subjects are forbidden
    
    Args:
        subject_id: Subject ID to fetch
    
    Returns:
        Detailed subject information with access validation
    """
    logger.info(f"Subject detail request: subject_id={subject_id}, user={current_user.email}")
    
    # Validate user enrollment
    if not current_user.course_id or not current_user.current_semester:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User enrollment incomplete"
        )
    
    # Fetch subject with curriculum mapping
    stmt = (
        select(CourseCurriculum)
        .options(joinedload(CourseCurriculum.subject))
        .where(
            CourseCurriculum.course_id == current_user.course_id,
            CourseCurriculum.subject_id == subject_id,
            CourseCurriculum.is_active == True
        )
    )
    
    result = await db.execute(stmt)
    curriculum_item = result.scalar_one_or_none()
    
    # Check if subject exists in user's course
    if not curriculum_item:
        logger.warning(
            f"Subject {subject_id} not found in course {current_user.course_id} "
            f"for user {current_user.email}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found in your enrolled course"
        )
    
    # Check if user can access this subject (semester lock)
    if curriculum_item.semester_number > current_user.current_semester:
        logger.warning(
            f"User {current_user.email} attempted to access future subject: "
            f"subject_semester={curriculum_item.semester_number}, "
            f"user_semester={current_user.current_semester}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This subject is locked. Available in Semester {curriculum_item.semester_number}."
        )
    
    # Return subject details
    subject = curriculum_item.subject
    return {
        "id": subject.id,
        "title": subject.title,
        "code": subject.code,
        "description": subject.description,
        "category": subject.category.value if subject.category else None,
        "syllabus": subject.syllabus,
        "semester": curriculum_item.semester_number,
        "is_elective": curriculum_item.is_elective,
        "access_status": "active" if curriculum_item.semester_number == current_user.current_semester else "archived",
        "created_at": subject.created_at.isoformat() if subject.created_at else None,
    }