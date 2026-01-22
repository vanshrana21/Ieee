"""
backend/routes/ba_llb.py
BA LLB Curriculum API Routes

Endpoints:
- GET /api/ba-llb/semesters - Get all semesters with subject counts
- GET /api/ba-llb/semesters/{semester_number}/subjects - Get subjects for a semester with module counts
- GET /api/ba-llb/subjects/{subject_id}/modules - Get modules for a subject

ZERO-MODULE BUG PREVENTION:
- Module counts are ALWAYS computed dynamically via COUNT() query
- Frontend receives pre-computed counts (never computes itself)
- No fallback to zero - if modules exist, count is accurate
"""
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.orm.ba_llb_curriculum import BALLBSemester, BALLBSubject, BALLBModule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ba-llb", tags=["BA LLB Curriculum"])


@router.get("/semesters")
async def get_all_semesters(db: AsyncSession = Depends(get_db)):
    """
    Get all BA LLB semesters with subject count per semester.
    
    Returns:
        {
            "course": {
                "name": "BA LLB",
                "duration_years": 5,
                "total_semesters": 10
            },
            "semesters": [
                {
                    "id": 1,
                    "semester_number": 1,
                    "name": "Semester 1",
                    "subject_count": 5,
                    "total_modules": 35
                }
            ]
        }
    """
    logger.info("Fetching BA LLB semesters")
    
    stmt = select(BALLBSemester).order_by(BALLBSemester.semester_number)
    result = await db.execute(stmt)
    semesters = result.scalars().all()
    
    if not semesters:
        return {
            "course": {
                "name": "BA LLB",
                "duration_years": 5,
                "total_semesters": 10
            },
            "semesters": []
        }
    
    semester_list = []
    for sem in semesters:
        subj_count_stmt = select(func.count(BALLBSubject.id)).where(
            BALLBSubject.semester_id == sem.id
        )
        subj_result = await db.execute(subj_count_stmt)
        subject_count = subj_result.scalar() or 0
        
        module_count_stmt = (
            select(func.count(BALLBModule.id))
            .join(BALLBSubject, BALLBModule.subject_id == BALLBSubject.id)
            .where(BALLBSubject.semester_id == sem.id)
        )
        mod_result = await db.execute(module_count_stmt)
        total_modules = mod_result.scalar() or 0
        
        semester_list.append({
            "id": sem.id,
            "semester_number": sem.semester_number,
            "name": sem.name,
            "subject_count": subject_count,
            "total_modules": total_modules
        })
    
    logger.info(f"Returning {len(semester_list)} semesters")
    
    return {
        "course": {
            "name": "BA LLB",
            "duration_years": 5,
            "total_semesters": 10
        },
        "semesters": semester_list
    }


@router.get("/semesters/{semester_number}/subjects")
async def get_subjects_by_semester(
    semester_number: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all subjects for a specific semester with DYNAMIC module counts.
    
    Module counts are computed via database query - NEVER hardcoded.
    
    Args:
        semester_number: 1-10
    
    Returns:
        {
            "semester": {
                "id": 1,
                "semester_number": 1,
                "name": "Semester 1"
            },
            "subjects": [
                {
                    "id": 1,
                    "name": "General English",
                    "code": "SEM1_ENG",
                    "subject_type": "core",
                    "is_optional": false,
                    "option_group": null,
                    "is_variable": false,
                    "module_count": 7  # DYNAMIC - computed from database
                }
            ]
        }
    """
    logger.info(f"Fetching subjects for semester {semester_number}")
    
    if semester_number < 1 or semester_number > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Semester number must be between 1 and 10"
        )
    
    stmt = select(BALLBSemester).where(
        BALLBSemester.semester_number == semester_number
    )
    result = await db.execute(stmt)
    semester = result.scalar_one_or_none()
    
    if not semester:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Semester {semester_number} not found. Please run seed script."
        )
    
    subj_stmt = (
        select(BALLBSubject)
        .where(BALLBSubject.semester_id == semester.id)
        .order_by(BALLBSubject.display_order)
    )
    subj_result = await db.execute(subj_stmt)
    subjects = subj_result.scalars().all()
    
    subject_list = []
    for subj in subjects:
        # Load units for each subject
        unit_stmt = (
            select(BALLBModule)
            .where(BALLBModule.subject_id == subj.id)
            .order_by(BALLBModule.sequence_order)
        )
        unit_result = await db.execute(unit_stmt)
        units = unit_result.scalars().all()
        
        unit_list = [
            {
                "id": unit.id,
                "title": unit.title,
                "sequence_order": unit.sequence_order,
                "description": unit.description
            }
            for unit in units
        ]
        
        subject_list.append({
            "id": subj.id,
            "name": subj.name,
            "code": subj.code,
            "description": subj.description,
            "subject_type": subj.subject_type,
            "is_foundation": subj.is_foundation,
            "is_optional": subj.is_optional,
            "option_group": subj.option_group,
            "is_variable": subj.is_variable,
            "display_order": subj.display_order,
            "module_count": len(unit_list),
            "unit_count": len(unit_list),
            "units": unit_list
        })
    
    logger.info(f"Returning {len(subject_list)} subjects for semester {semester_number}")
    
    return {
        "semester": {
            "id": semester.id,
            "semester_number": semester.semester_number,
            "name": semester.name
        },
        "subjects": subject_list
    }


@router.get("/subjects/{subject_id}/modules")
async def get_modules_by_subject(
    subject_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all modules for a specific subject in correct order.
    
    Args:
        subject_id: Subject ID
    
    Returns:
        {
            "subject": {
                "id": 1,
                "name": "General English",
                "code": "SEM1_ENG",
                "semester_number": 1,
                "subject_type": "core"
            },
            "modules": [
                {
                    "id": 1,
                    "title": "Basic Grammar: Tense, Voice, Direct/Indirect Speech",
                    "sequence_order": 1,
                    "description": null
                }
            ],
            "module_count": 7
        }
    """
    logger.info(f"Fetching modules for subject {subject_id}")
    
    stmt = (
        select(BALLBSubject)
        .options(selectinload(BALLBSubject.semester))
        .where(BALLBSubject.id == subject_id)
    )
    result = await db.execute(stmt)
    subject = result.scalar_one_or_none()
    
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with ID {subject_id} not found"
        )
    
    mod_stmt = (
        select(BALLBModule)
        .where(BALLBModule.subject_id == subject_id)
        .order_by(BALLBModule.sequence_order)
    )
    mod_result = await db.execute(mod_stmt)
    modules = mod_result.scalars().all()
    
    module_list = [
        {
            "id": mod.id,
            "title": mod.title,
            "sequence_order": mod.sequence_order,
            "description": mod.description
        }
        for mod in modules
    ]
    
    logger.info(f"Returning {len(module_list)} modules for subject {subject_id}")
    
    return {
        "subject": {
            "id": subject.id,
            "name": subject.name,
            "code": subject.code,
            "semester_number": subject.semester.semester_number if subject.semester else None,
            "subject_type": subject.subject_type,
            "is_optional": subject.is_optional,
            "option_group": subject.option_group
        },
        "modules": module_list,
        "module_count": len(module_list),
        "units": module_list,
        "unit_count": len(module_list)
    }


@router.get("/modules/{module_id}")
async def get_module_detail(
    module_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a specific module.
    
    Args:
        module_id: Module ID
    
    Returns:
        Module details with subject and semester context
    """
    logger.info(f"Fetching module {module_id}")
    
    stmt = (
        select(BALLBModule)
        .options(
            selectinload(BALLBModule.subject).selectinload(BALLBSubject.semester)
        )
        .where(BALLBModule.id == module_id)
    )
    result = await db.execute(stmt)
    module = result.scalar_one_or_none()
    
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module with ID {module_id} not found"
        )
    
    return {
        "module": {
            "id": module.id,
            "title": module.title,
            "sequence_order": module.sequence_order,
            "description": module.description
        },
        "subject": {
            "id": module.subject.id,
            "name": module.subject.name,
            "code": module.subject.code,
            "subject_type": module.subject.subject_type
        },
        "semester": {
            "semester_number": module.subject.semester.semester_number,
            "name": module.subject.semester.name
        } if module.subject.semester else None
    }


@router.get("/stats")
async def get_curriculum_stats(db: AsyncSession = Depends(get_db)):
    """
    Get overall BA LLB curriculum statistics.
    
    Returns:
        {
            "total_semesters": 10,
            "total_subjects": 46,
            "total_modules": 305,
            "subjects_by_type": {
                "core": 25,
                "major": 6,
                "minor_i": 3,
                "minor_ii": 3,
                "optional": 6,
                "clinical": 4
            }
        }
    """
    logger.info("Fetching BA LLB curriculum stats")
    
    sem_count_stmt = select(func.count(BALLBSemester.id))
    sem_result = await db.execute(sem_count_stmt)
    total_semesters = sem_result.scalar() or 0
    
    subj_count_stmt = select(func.count(BALLBSubject.id))
    subj_result = await db.execute(subj_count_stmt)
    total_subjects = subj_result.scalar() or 0
    
    mod_count_stmt = select(func.count(BALLBModule.id))
    mod_result = await db.execute(mod_count_stmt)
    total_modules = mod_result.scalar() or 0
    
    type_count_stmt = (
        select(BALLBSubject.subject_type, func.count(BALLBSubject.id))
        .group_by(BALLBSubject.subject_type)
    )
    type_result = await db.execute(type_count_stmt)
    subjects_by_type = {row[0]: row[1] for row in type_result.fetchall()}
    
    return {
        "course_name": "BA LLB (5-Year Integrated)",
        "total_semesters": total_semesters,
        "total_subjects": total_subjects,
        "total_modules": total_modules,
        "subjects_by_type": subjects_by_type
    }
