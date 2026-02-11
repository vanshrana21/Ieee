"""
backend/routes/user.py
User profile and enrollment management routes
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from backend.database import get_db
from backend.orm.user import User
from backend.orm.course import Course
from backend.routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


# ================= SCHEMAS =================

class EnrollmentRequest(BaseModel):
    """Request schema for course enrollment"""
    course_name: str  # Frontend sends name like "BA LLB (5 Year Integrated)"
    current_semester: int


# ================= ROUTES =================

@router.get("/profile")
async def get_user_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's profile with course information.
    
    Returns:
        User profile with enrolled course details
    """
    # Fetch user with course relationship
    stmt = select(User).where(User.id == current_user.id)
    result = await db.execute(stmt)
    user = result.scalar_one()
    
    profile = user.to_dict()
    
    # Add course details if enrolled
    if user.course_id:
        course_stmt = select(Course).where(Course.id == user.course_id)
        course_result = await db.execute(course_stmt)
        course = course_result.scalar_one_or_none()
        if course:
            profile["course"] = course.to_dict()
    
    return profile


@router.post("/enroll")
async def enroll_in_course(
    enrollment: EnrollmentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Enroll user in a course and set current semester.
    
    Args:
        enrollment: Course name (from frontend) and starting semester
    
    Returns:
        Updated user profile
    """
    # Normalize course name from frontend
    # Frontend sends: "BA LLB (5 Year Integrated)"
    # Database has: "BA LLB", "BBA LLB", "LLB"
    normalized_name = enrollment.course_name.strip()
    
    # Remove parenthetical descriptions like "(5 Year Integrated)"
    if "(" in normalized_name:
        normalized_name = normalized_name.split("(")[0].strip()
    
    # Case-insensitive lookup
    course_stmt = select(Course).where(Course.name.ilike(normalized_name))
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    
    if not course:
        # Log available courses for debugging
        all_courses_stmt = select(Course)
        all_courses_result = await db.execute(all_courses_stmt)
        available_courses = [c.name for c in all_courses_result.scalars().all()]
        logger.warning(f"Course not found: '{normalized_name}' (original: '{enrollment.course_name}'). Available: {available_courses}")
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course '{enrollment.course_name}' not found. Available courses: {', '.join(available_courses)}"
        )
    
    # Validate semester is within course range
    if enrollment.current_semester < 1 or enrollment.current_semester > course.total_semesters:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Semester must be between 1 and {course.total_semesters}"
        )
    
    # Update user enrollment
    current_user.course_id = course.id
    current_user.current_semester = enrollment.current_semester
    
    await db.commit()
    await db.refresh(current_user)
    
    logger.info(
        f"User {current_user.email} enrolled in course {course.name}, "
        f"semester {enrollment.current_semester}"
    )
    
    return {
        "message": "Enrollment successful",
        "user": current_user.to_dict_with_course()
    }