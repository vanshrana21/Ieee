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
from backend.orm.content_module import ContentModule, ModuleStatus
from backend.orm.subject_progress import SubjectProgress
from backend.routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/curriculum", tags=["Curriculum"])


# ================= HELPER FUNCTIONS =================

async def get_subjects_with_modules_and_progress(
    db: AsyncSession,
    user: User,
    course_id: int,
    semester_filter: str = "all"  # "current", "past", "all"
) -> List[Dict[str, Any]]:
    """
    Fetch subjects with content modules and progress for a user.
    
    This is the CORE Phase 4.1 function that:
    1. Fetches subjects based on curriculum mapping
    2. Eagerly loads content modules (with order)
    3. Joins user's progress data
    4. Calculates module lock status
    
    Args:
        db: Database session
        user: Current user (for progress and premium checks)
        course_id: User's enrolled course ID
        semester_filter: "current" | "past" | "all"
    
    Returns:
        List of subject dictionaries with modules and completion %
    """
    # Build base query
    stmt = select(CourseCurriculum).options(
        joinedload(CourseCurriculum.subject)
    ).where(
        CourseCurriculum.course_id == course_id,
        CourseCurriculum.is_active == True
    )
    
    # Apply semester filter
    if semester_filter == "current":
        stmt = stmt.where(CourseCurriculum.semester_number == user.current_semester)
    elif semester_filter == "past":
        stmt = stmt.where(CourseCurriculum.semester_number < user.current_semester)
    else:  # "all"
        stmt = stmt.where(CourseCurriculum.semester_number <= user.current_semester)
    
    # Order by semester (desc) and display order
    stmt = stmt.order_by(
        CourseCurriculum.semester_number.desc(),
        CourseCurriculum.display_order,
        CourseCurriculum.id
    )
    
    result = await db.execute(stmt)
    curriculum_items = result.scalars().all()
    
    # Collect subject IDs for batch queries
    subject_ids = [item.subject_id for item in curriculum_items if item.subject]
    
    if not subject_ids:
        return []
    
    # Batch fetch content modules for all subjects
    modules_stmt = (
        select(ContentModule)
        .where(ContentModule.subject_id.in_(subject_ids))
        .order_by(ContentModule.subject_id, ContentModule.order_index)
    )
    modules_result = await db.execute(modules_stmt)
    all_modules = modules_result.scalars().all()
    
    # Group modules by subject_id
    modules_by_subject = {}
    for module in all_modules:
        if module.subject_id not in modules_by_subject:
            modules_by_subject[module.subject_id] = []
        modules_by_subject[module.subject_id].append(module)
    
    # Batch fetch subject progress for user
    progress_stmt = (
        select(SubjectProgress)
        .where(
            SubjectProgress.user_id == user.id,
            SubjectProgress.subject_id.in_(subject_ids)
        )
    )
    progress_result = await db.execute(progress_stmt)
    all_progress = progress_result.scalars().all()
    
    # Map progress by subject_id
    progress_by_subject = {p.subject_id: p for p in all_progress}
    
    # Build response
    subjects = []
    for item in curriculum_items:
        if not item.subject:
            continue
        
        subject = item.subject
        subject_id = subject.id
        
        # Get progress (default 0% if not started)
        progress = progress_by_subject.get(subject_id)
        completion_percentage = progress.completion_percentage if progress else 0.0
        
        # Get modules for this subject
        subject_modules = modules_by_subject.get(subject_id, [])
        
        # Transform modules to API format with lock calculation
        modules_data = []
        for module in subject_modules:
            is_locked = calculate_module_lock_status(module, user)
            
            modules_data.append({
                "id": module.id,
                "module_type": module.module_type.value,
                "title": module.title,
                "description": module.description,
                "order_index": module.order_index,
                "status": module.status.value,
                "is_locked": is_locked,
                "is_free": module.is_free,
            })
        
        # Build subject data
        subjects.append({
            "id": subject.id,
            "title": subject.title,
            "code": subject.code,
            "semester": item.semester_number,
            "category": subject.category.value if subject.category else None,
            "is_elective": item.is_elective,
            "description": subject.description,
            "completion_percentage": round(completion_percentage, 1),
            "modules": modules_data,
        })
    
    return subjects


def calculate_module_lock_status(module: ContentModule, user: User) -> bool:
    """
    Determine if a module should be locked for the user.
    
    Lock Rules:
    1. LOCKED status → Always locked
    2. COMING_SOON status → Always locked
    3. ACTIVE + not free + not premium → Locked (paywall)
    4. ACTIVE + (free OR premium) → Unlocked
    
    Args:
        module: ContentModule to check
        user: Current user with premium status
    
    Returns:
        True if locked, False if accessible
    """
    # Rule 1: Explicitly locked modules
    if module.status == ModuleStatus.LOCKED:
        return True
    
    # Rule 2: Coming soon modules
    if module.status == ModuleStatus.COMING_SOON:
        return True
    
    # Rule 3: Premium paywall
    if not module.is_free and not user.is_premium:
        return True
    
    # Rule 4: Accessible
    return False


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
    
    PHASE 4.1 ENHANCEMENT:
    - Returns subjects with content modules
    - Includes user's progress percentage per subject
    - Calculates module lock status (premium/locked/coming_soon)
    - Ordered by curriculum.display_order
    
    Returns subjects divided into:
    - active_subjects: Current semester subjects
    - archive_subjects: Past semester subjects
    - Future subjects are NOT returned (locked)
    
    Business Logic:
    1. User must be enrolled in a course (course_id not NULL)
    2. User must have a current_semester set
    3. Only returns subjects <= current_semester
    4. Subjects are fetched via course_curriculum mapping
    5. Content modules are eagerly loaded per subject
    6. Progress is fetched from subject_progress table
    
    Response:
        {
            "course": {
                "id": 1,
                "name": "BA LLB",
                "code": "BA_LLB",
                "total_semesters": 10
            },
            "current_semester": 5,
            "active_subjects": [
                {
                    "id": 1,
                    "title": "Contract Law",
                    "completion_percentage": 45.5,
                    "modules": [
                        {
                            "id": 1,
                            "module_type": "learn",
                            "title": "Learn Contract Law",
                            "is_locked": false,
                            "order_index": 0
                        },
                        ...
                    ]
                }
            ],
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
    
    # ========== FETCH SUBJECTS WITH MODULES AND PROGRESS ==========
    
    # Get active subjects (current semester) with modules
    active_subjects = await get_subjects_with_modules_and_progress(
        db,
        current_user,
        current_user.course_id,
        semester_filter="current"
    )
    
    # Get archive subjects (past semesters) with modules
    archive_subjects = await get_subjects_with_modules_and_progress(
        db,
        current_user,
        current_user.course_id,
        semester_filter="past"
    )
    
    logger.info(
        f"Dashboard data prepared for {current_user.email}: "
        f"{len(active_subjects)} active, {len(archive_subjects)} archived "
        f"(with modules and progress)"
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
    Get detailed information about a specific subject with modules.
    
    PHASE 4.1 ENHANCEMENT:
    - Returns content modules with lock status
    - Includes user's progress data
    - Validates semester access control
    
    Security:
    - User can only access subjects from their course
    - User can only access subjects from current or past semesters
    - Future subjects are forbidden
    
    Args:
        subject_id: Subject ID to fetch
    
    Returns:
        Detailed subject information with modules and progress
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
    
    subject = curriculum_item.subject
    
    # ========== FETCH CONTENT MODULES ==========
    
    modules_stmt = (
        select(ContentModule)
        .where(ContentModule.subject_id == subject_id)
        .order_by(ContentModule.order_index)
    )
    modules_result = await db.execute(modules_stmt)
    modules = modules_result.scalars().all()
    
    # Transform modules with lock status
    modules_data = []
    for module in modules:
        is_locked = calculate_module_lock_status(module, current_user)
        
        modules_data.append({
            "id": module.id,
            "module_type": module.module_type.value,
            "title": module.title,
            "description": module.description,
            "order_index": module.order_index,
            "status": module.status.value,
            "is_locked": is_locked,
            "is_free": module.is_free,
        })
    
    # ========== FETCH USER PROGRESS ==========
    
    progress_stmt = (
        select(SubjectProgress)
        .where(
            SubjectProgress.user_id == current_user.id,
            SubjectProgress.subject_id == subject_id
        )
    )
    progress_result = await db.execute(progress_stmt)
    progress = progress_result.scalar_one_or_none()
    
    completion_percentage = progress.completion_percentage if progress else 0.0
    last_activity = progress.last_activity_at.isoformat() if progress and progress.last_activity_at else None
    
    # ========== RETURN RESPONSE ==========
    
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
        "completion_percentage": round(completion_percentage, 1),
        "last_activity_at": last_activity,
        "modules": modules_data,
        "created_at": subject.created_at.isoformat() if subject.created_at else None,
    }