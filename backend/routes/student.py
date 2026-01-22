"""
backend/routes/student.py
Phase 3 & 4: Student-facing APIs for content availability, modules, and learning content
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime

from backend.database import get_db
from backend.orm.user import User
from backend.orm.curriculum import CourseCurriculum
from backend.orm.course import Course
from backend.orm.content_module import ContentModule, ModuleType, ModuleStatus
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion
from backend.orm.user_notes import UserNotes
from backend.orm.user_content_progress import UserContentProgress, ContentType
from backend.orm.subject import Subject
from backend.routes.auth import get_current_user

router = APIRouter(prefix="/student", tags=["Student"])


async def get_allowed_subject_ids(user: User, db: AsyncSession) -> List[int]:
    """
    Get subject IDs the user is allowed to access based on course + semester.
    Returns only subjects for user's current semester.
    """
    if not user.course_id or not user.current_semester:
        return []
    
    stmt = select(CourseCurriculum.subject_id).where(
        and_(
            CourseCurriculum.course_id == user.course_id,
            CourseCurriculum.semester_number == user.current_semester,
            CourseCurriculum.is_active == True
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def verify_subject_access(user: User, subject_id: int, db: AsyncSession) -> bool:
    """
    Verify user can access a specific subject based on course + semester.
    """
    allowed_ids = await get_allowed_subject_ids(user, db)
    return subject_id in allowed_ids


class SubjectListItem(BaseModel):
    id: int
    title: str
    code: Optional[str] = None
    description: Optional[str] = None
    unit_count: int = 0
    module_count: int = 0
    units: List[Dict] = []


class SubjectListResponse(BaseModel):
    subjects: List[SubjectListItem]
    course_name: Optional[str] = None
    current_semester: Optional[int] = None


class AcademicProfileRequest(BaseModel):
    course_id: int
    current_semester: int


class AcademicProfileResponse(BaseModel):
    success: bool
    message: str
    course_id: int
    course_name: str
    current_semester: int


class CourseListItem(BaseModel):
    id: int
    name: str
    code: str
    duration_years: int
    total_semesters: int


class CoursesListResponse(BaseModel):
    courses: List[CourseListItem]


@router.get("/courses", response_model=CoursesListResponse)
async def get_available_courses(
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of available courses for enrollment.
    No auth required - used during onboarding.
    """
    stmt = select(Course).order_by(Course.id)
    result = await db.execute(stmt)
    courses = result.scalars().all()
    
    return CoursesListResponse(
        courses=[
            CourseListItem(
                id=c.id,
                name=c.name,
                code=c.code,
                duration_years=c.duration_years,
                total_semesters=c.total_semesters
            ) for c in courses
        ]
    )


@router.post("/academic-profile", response_model=AcademicProfileResponse)
async def save_academic_profile(
    profile: AcademicProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Save student's academic profile (course + semester).
    Validates course exists and semester is valid for that course.
    """
    course_stmt = select(Course).where(Course.id == profile.course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    
    if not course:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid course ID"
        )
    
    if profile.current_semester < 1 or profile.current_semester > course.total_semesters:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid semester. {course.name} has semesters 1-{course.total_semesters}"
        )
    
    current_user.course_id = profile.course_id
    current_user.current_semester = profile.current_semester
    await db.commit()
    await db.refresh(current_user)
    
    return AcademicProfileResponse(
        success=True,
        message=f"Academic profile updated to {course.name}, Semester {profile.current_semester}",
        course_id=course.id,
        course_name=course.name,
        current_semester=profile.current_semester
    )


@router.get("/academic-profile")
async def get_academic_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get student's current academic profile.
    """
    course = None
    if current_user.course_id:
        course_stmt = select(Course).where(Course.id == current_user.course_id)
        course_result = await db.execute(course_stmt)
        course = course_result.scalar_one_or_none()
    
    return {
        "course_id": current_user.course_id,
        "course_name": course.name if course else None,
        "current_semester": current_user.current_semester,
        "total_semesters": course.total_semesters if course else None
    }


@router.get("/subjects", response_model=SubjectListResponse)
async def get_student_subjects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get subjects for student's CURRENT SEMESTER ONLY.
    
    Enforces course + semester filtering:
    - BA LLB Sem 3 user → only Sem 3 subjects
    - LLB Sem 1 user → only Sem 1 subjects
    
    Returns [] if no subjects - never throws 404 for valid users.
    """
    if not current_user.course_id or not current_user.current_semester:
        return SubjectListResponse(subjects=[], course_name=None, current_semester=None)
    
    course_stmt = select(Course).where(Course.id == current_user.course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    course_name = course.name if course else None
    
    stmt = select(CourseCurriculum).where(
        and_(
            CourseCurriculum.course_id == current_user.course_id,
            CourseCurriculum.semester_number == current_user.current_semester,
            CourseCurriculum.is_active == True
        )
    ).order_by(CourseCurriculum.display_order)
    
    result = await db.execute(stmt)
    curriculum_items = result.scalars().all()
    
    if not curriculum_items:
        return SubjectListResponse(
            subjects=[],
            course_name=course_name,
            current_semester=current_user.current_semester
        )
    
    subject_ids = [item.subject_id for item in curriculum_items]
    
    subjects_stmt = select(Subject).where(Subject.id.in_(subject_ids))
    subjects_result = await db.execute(subjects_stmt)
    subjects_map = {s.id: s for s in subjects_result.scalars().all()}
    
    # BA LLB check
    is_ba_llb = False
    if current_user.course_id:
        course_stmt = select(Course).where(Course.id == current_user.course_id)
        course_result = await db.execute(course_stmt)
        course = course_result.scalar_one_or_none()
        if course and ("BA LLB" in course.name.upper() or "BA.LLB" in course.name.upper()):
            is_ba_llb = True

    subjects_list = []
    for item in curriculum_items:
        subject = subjects_map.get(item.subject_id)
        if subject:
            unit_list = []
            if is_ba_llb:
                from backend.orm.ba_llb_curriculum import BALLBModule
                unit_stmt = (
                    select(BALLBModule)
                    .where(BALLBModule.subject_id == subject.id)
                    .order_by(BALLBModule.sequence_order)
                )
                unit_result = await db.execute(unit_stmt)
                units = unit_result.scalars().all()
                unit_list = [
                    {
                        "id": u.id,
                        "title": u.title,
                        "sequence_order": u.sequence_order,
                        "description": u.description
                    }
                    for u in units
                ]
            else:
                # For generic subjects, map ContentModule to units
                mod_stmt = select(ContentModule).where(
                    and_(
                        ContentModule.subject_id == subject.id,
                        ContentModule.module_type == "learn",
                        ContentModule.status == "active"
                    )
                ).order_by(ContentModule.order_index)
                mod_result = await db.execute(mod_stmt)
                mods = mod_result.scalars().all()
                unit_list = [
                    {
                        "id": m.id,
                        "title": m.title,
                        "sequence_order": m.order_index,
                        "description": None
                    }
                    for m in mods
                ]

            subjects_list.append(SubjectListItem(
                id=subject.id, 
                title=subject.title,
                code=subject.code,
                description=subject.description,
                unit_count=len(unit_list),
                units=unit_list
            ))
    
    return SubjectListResponse(
        subjects=subjects_list,
        course_name=course_name,
        current_semester=current_user.current_semester
    )


class ContentAvailabilityResponse(BaseModel):
    subject_id: int
    has_learning_content: bool
    has_modules: bool
    has_cases: bool
    has_practice: bool
    has_notes: bool
    first_learning_content_id: Optional[int] = None
    first_case_id: Optional[int] = None
    first_practice_id: Optional[int] = None
    learn_count: int = 0
    modules_count: int = 0
    cases_count: int = 0
    practice_count: int = 0
    notes_count: int = 0


class ModuleListItem(BaseModel):
    module_id: int
    title: str
    sequence_order: int
    total_contents: int
    completed_contents: int
    is_completed: bool


class SubjectModulesResponse(BaseModel):
    subject_id: int
    subject_name: str
    modules: List[ModuleListItem]
    units: Optional[List[Dict]] = None
    unit_count: Optional[int] = 0

class ModuleResumeResponse(BaseModel):
    module_id: int
    next_content_id: Optional[int] = None
    message: Optional[str] = None


class ContentListItem(BaseModel):
    content_id: int
    title: str
    sequence_order: int
    is_completed: bool


class ModuleContentResponse(BaseModel):
    module_id: int
    content: List[ContentListItem]


class LearnContentDetailResponse(BaseModel):
    content_id: int
    module_id: int
    title: str
    body: str
    sequence_order: int
    is_completed: bool


@router.get("/subject/{subject_id}/availability", response_model=ContentAvailabilityResponse)
async def get_subject_availability(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Check what content exists for a subject.
    Enforces course + semester access control.
    """
    if not current_user.course_id or not current_user.current_semester:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please set your course and semester first"
        )

    if not await verify_subject_access(current_user, subject_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subject not available in your current semester"
        )

    # BA LLB check
    is_ba_llb = False
    if current_user.course_id:
        course_stmt = select(Course).where(Course.id == current_user.course_id)
        course_result = await db.execute(course_stmt)
        course = course_result.scalar_one_or_none()
        if course and ("BA LLB" in course.name.upper() or "BA.LLB" in course.name.upper()):
            is_ba_llb = True

    if is_ba_llb:
        from backend.orm.ba_llb_curriculum import BALLBModule
        unit_stmt = select(func.count(BALLBModule.id)).where(BALLBModule.subject_id == subject_id)
        unit_result = await db.execute(unit_stmt)
        units_count = unit_result.scalar() or 0
        
        return ContentAvailabilityResponse(
            subject_id=subject_id,
            has_learning_content=units_count > 0,
            has_modules=units_count > 0,
            has_cases=False, # Add logic if BA LLB cases are implemented
            has_practice=False, # Add logic if BA LLB practice is implemented
            has_notes=True,
            learn_count=units_count,
            modules_count=units_count,
            cases_count=0,
            practice_count=0,
            notes_count=0 # You can add actual notes count here
        )

    learn_module_stmt = select(ContentModule).where(
        and_(
            ContentModule.subject_id == subject_id,
            ContentModule.module_type == "learn",
            ContentModule.status == "active"
        )
    )
    learn_module_result = await db.execute(learn_module_stmt)
    learn_modules = learn_module_result.scalars().all()

    first_learn_id = None
    total_learn_count = 0
    if learn_modules:
        for module in learn_modules:
            learn_stmt = select(func.count(LearnContent.id)).where(LearnContent.module_id == module.id)
            learn_result = await db.execute(learn_stmt)
            total_learn_count += (learn_result.scalar() or 0)
            
            if first_learn_id is None:
                first_item_stmt = select(LearnContent.id).where(LearnContent.module_id == module.id).order_by(LearnContent.order_index).limit(1)
                first_item_result = await db.execute(first_item_stmt)
                first_learn_id = first_item_result.scalar()

    cases_module_stmt = select(ContentModule).where(
        and_(
            ContentModule.subject_id == subject_id,
            ContentModule.module_type == "cases",
            ContentModule.status == "active"
        )
    )
    cases_module_result = await db.execute(cases_module_stmt)
    cases_module = cases_module_result.scalar_one_or_none()

    first_case_id = None
    cases_count = 0
    if cases_module:
        cases_stmt = (
            select(CaseContent)
            .where(CaseContent.module_id == cases_module.id)
            .order_by(CaseContent.year.desc())
        )
        cases_result = await db.execute(cases_stmt)
        case_items = cases_result.scalars().all()
        cases_count = len(case_items)
        if case_items:
            first_case_id = case_items[0].id

    practice_module_stmt = select(ContentModule).where(
        and_(
            ContentModule.subject_id == subject_id,
            ContentModule.module_type == "practice",
            ContentModule.status == "active"
        )
    )
    practice_module_result = await db.execute(practice_module_stmt)
    practice_module = practice_module_result.scalar_one_or_none()

    first_practice_id = None
    practice_count = 0
    if practice_module:
        practice_stmt = (
            select(PracticeQuestion)
            .where(PracticeQuestion.module_id == practice_module.id)
            .order_by(PracticeQuestion.order_index)
        )
        practice_result = await db.execute(practice_stmt)
        practice_items = practice_result.scalars().all()
        practice_count = len(practice_items)
        if practice_items:
            first_practice_id = practice_items[0].id

    notes_stmt = select(func.count(UserNotes.id)).where(
        and_(
            UserNotes.user_id == current_user.id,
            UserNotes.subject_id == subject_id
        )
    )
    notes_result = await db.execute(notes_stmt)
    notes_count = notes_result.scalar() or 0

    modules_count = len(learn_modules)

    return ContentAvailabilityResponse(
        subject_id=subject_id,
        has_learning_content=total_learn_count > 0,
        has_modules=modules_count > 0,
        has_cases=cases_count > 0,
        has_practice=practice_count > 0,
        has_notes=True,
        first_learning_content_id=first_learn_id,
        first_case_id=first_case_id,
        first_practice_id=first_practice_id,
        learn_count=total_learn_count,
        modules_count=modules_count,
        cases_count=cases_count,
        practice_count=practice_count,
        notes_count=notes_count
    )


@router.get("/subject/{subject_id}/modules", response_model=SubjectModulesResponse)
async def get_subject_modules(
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all LEARN modules for a subject in correct order.
    Enforces course + semester access control.
    """
    if not current_user.course_id or not current_user.current_semester:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please set your course and semester first"
        )
    
    if not await verify_subject_access(current_user, subject_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subject not available in your current semester"
        )
    
    subject_stmt = select(Subject).where(Subject.id == subject_id)
    subject_result = await db.execute(subject_stmt)
    subject = subject_result.scalar_one_or_none()
    
    subject_name = subject.title if subject else "Unknown Subject"
    
    # BA LLB check
    is_ba_llb = False
    if current_user.course_id:
        course_stmt = select(Course).where(Course.id == current_user.course_id)
        course_result = await db.execute(course_stmt)
        course = course_result.scalar_one_or_none()
        if course and ("BA LLB" in course.name.upper() or "BA.LLB" in course.name.upper()):
            is_ba_llb = True

    if is_ba_llb:
        from backend.orm.ba_llb_curriculum import BALLBModule
        stmt = (
            select(BALLBModule)
            .where(BALLBModule.subject_id == subject_id)
            .order_by(BALLBModule.sequence_order)
        )
        result = await db.execute(stmt)
        units = result.scalars().all()
        
        unit_list = [
            {
                "id": unit.id,
                "title": unit.title,
                "sequence_order": unit.sequence_order,
                "description": unit.description
            }
            for unit in units
        ]
        
        module_list = [
            ModuleListItem(
                module_id=unit.id,
                title=unit.title,
                sequence_order=unit.sequence_order,
                total_contents=0,
                completed_contents=0,
                is_completed=False
            )
            for unit in units
        ]
        
        return SubjectModulesResponse(
            subject_id=subject_id,
            subject_name=subject_name,
            modules=module_list,
            units=unit_list,
            unit_count=len(unit_list)
        )

    modules_stmt = select(ContentModule).where(
        and_(
            ContentModule.subject_id == subject_id,
            ContentModule.module_type == "learn",
            ContentModule.status == "active"
        )
    ).order_by(ContentModule.order_index)
    
    modules_result = await db.execute(modules_stmt)
    modules = modules_result.scalars().all()
    
    module_list = []
    for module in modules:
        content_ids_stmt = select(LearnContent.id).where(LearnContent.module_id == module.id)
        content_ids_result = await db.execute(content_ids_stmt)
        content_ids = content_ids_result.scalars().all()
        
        total_contents = len(content_ids)
        completed_contents = 0
        
        if content_ids:
            completed_count_stmt = select(func.count(UserContentProgress.id)).where(
                and_(
                    UserContentProgress.user_id == current_user.id,
                    UserContentProgress.content_type == ContentType.LEARN,
                    UserContentProgress.content_id.in_(content_ids),
                    UserContentProgress.is_completed == True
                )
            )
            completed_count_result = await db.execute(completed_count_stmt)
            completed_contents = completed_count_result.scalar() or 0
        
        is_completed = (completed_contents == total_contents) if total_contents > 0 else False
        
        module_list.append(ModuleListItem(
            module_id=module.id,
            title=module.title,
            sequence_order=module.order_index,
            total_contents=total_contents,
            completed_contents=completed_contents,
            is_completed=is_completed
        ))
    
    return SubjectModulesResponse(
        subject_id=subject_id,
        subject_name=subject_name,
        modules=module_list
    )


@router.get("/module/{module_id}/content", response_model=ModuleContentResponse)
async def get_module_content(
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all learning content for a module in correct order.
    """
    content_stmt = select(LearnContent).where(
        LearnContent.module_id == module_id
    ).order_by(LearnContent.order_index)
    
    content_result = await db.execute(content_stmt)
    contents = content_result.scalars().all()
    
    content_list = []
    for content in contents:
        progress_stmt = select(UserContentProgress).where(
            and_(
                UserContentProgress.user_id == current_user.id,
                UserContentProgress.content_type == ContentType.LEARN,
                UserContentProgress.content_id == content.id
            )
        )
        progress_result = await db.execute(progress_stmt)
        progress = progress_result.scalar_one_or_none()
        
        content_list.append(ContentListItem(
            content_id=content.id,
            title=content.title,
            sequence_order=content.order_index,
            is_completed=progress.is_completed if progress else False
        ))
    
    return ModuleContentResponse(
        module_id=module_id,
        content=content_list
    )


@router.get("/module/{module_id}/resume", response_model=ModuleResumeResponse)
async def get_module_resume(
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the next content to resume in a module.
    Returns earliest incomplete content, or last content if all complete.
    """
    content_stmt = select(LearnContent).where(
        LearnContent.module_id == module_id
    ).order_by(LearnContent.order_index)
    
    content_result = await db.execute(content_stmt)
    contents = content_result.scalars().all()
    
    if not contents:
        return ModuleResumeResponse(
            module_id=module_id,
            next_content_id=None,
            message="No learning content available in this module yet."
        )
    
    for content in contents:
        progress_stmt = select(UserContentProgress).where(
            and_(
                UserContentProgress.user_id == current_user.id,
                UserContentProgress.content_type == ContentType.LEARN,
                UserContentProgress.content_id == content.id,
                UserContentProgress.is_completed == True
            )
        )
        progress_result = await db.execute(progress_stmt)
        progress = progress_result.scalar_one_or_none()
        
        if not progress:
            return ModuleResumeResponse(
                module_id=module_id,
                next_content_id=content.id
            )
    
    return ModuleResumeResponse(
        module_id=module_id,
        next_content_id=contents[-1].id
    )


@router.get("/content/{content_id}", response_model=LearnContentDetailResponse)
async def get_content_detail(
    content_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed learning content.
    """
    content_stmt = select(LearnContent).where(LearnContent.id == content_id)
    content_result = await db.execute(content_stmt)
    content = content_result.scalar_one_or_none()
    
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    progress_stmt = select(UserContentProgress).where(
        and_(
            UserContentProgress.user_id == current_user.id,
            UserContentProgress.content_type == ContentType.LEARN,
            UserContentProgress.content_id == content.id
        )
    )
    progress_result = await db.execute(progress_stmt)
    progress = progress_result.scalar_one_or_none()
    
    if not progress:
        progress = UserContentProgress(
            user_id=current_user.id,
            content_type=ContentType.LEARN,
            content_id=content.id,
            is_completed=False,
            last_viewed_at=datetime.utcnow()
        )
        db.add(progress)
    else:
        progress.last_viewed_at = datetime.utcnow()
        progress.view_count += 1
    
    await db.commit()
    
    return LearnContentDetailResponse(
        content_id=content.id,
        module_id=content.module_id,
        title=content.title,
        body=content.body,
        sequence_order=content.order_index,
        is_completed=progress.is_completed if progress else False
    )


@router.post("/content/{content_id}/complete")
async def mark_content_complete(
    content_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark a learning content as completed.
    """
    progress_stmt = select(UserContentProgress).where(
        and_(
            UserContentProgress.user_id == current_user.id,
            UserContentProgress.content_type == ContentType.LEARN,
            UserContentProgress.content_id == content_id
        )
    )
    progress_result = await db.execute(progress_stmt)
    progress = progress_result.scalar_one_or_none()
    
    if not progress:
        progress = UserContentProgress(
            user_id=current_user.id,
            content_type=ContentType.LEARN,
            content_id=content_id,
            is_completed=True,
            completed_at=datetime.utcnow(),
            last_viewed_at=datetime.utcnow()
        )
        db.add(progress)
    else:
        progress.is_completed = True
        progress.completed_at = datetime.utcnow()
    
    await db.commit()
    return {"status": "success", "message": "Content marked as completed"}
