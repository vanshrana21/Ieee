"""
backend/services/mock_exam_service.py
Phase 7.2: Timed Mock Exam Engine

SYSTEM PURPOSE:
Convert an exam blueprint into a fully timed, real-exam simulation.

KEY FEATURES:
- Session lifecycle management (start → in_progress → submit)
- Timer enforcement (auto-submit on expiry)
- Answer tracking with time spent per question
- Session recovery after page refresh
- No answer modification after submission

TIMER RULES:
1. Global Timer: Starts when exam begins, auto-submit on expiry
2. Per-Question: Track time spent on each question
3. Remaining time calculated from started_at + duration_minutes
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update

from backend.orm.exam_session import ExamSession, ExamSessionStatus
from backend.orm.exam_answer import ExamAnswer
from backend.orm.practice_question import PracticeQuestion
from backend.services.exam_blueprint_service import (
    generate_exam_blueprint,
    ExamType,
)

logger = logging.getLogger(__name__)


async def start_exam_session(
    user_id: int,
    exam_type: str,
    db: AsyncSession,
    subject_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Start a new mock exam session.
    
    Lifecycle:
    1. Generate blueprint
    2. Create exam session
    3. Create answer placeholders for all questions
    4. Return session with questions
    
    Args:
        user_id: User starting the exam
        exam_type: Type of exam (mock_exam, end_semester, etc.)
        db: Database session
        subject_id: Optional subject filter
        
    Returns:
        Session data with questions and timer info
    """
    try:
        exam_type_enum = ExamType(exam_type)
    except ValueError:
        exam_type_enum = ExamType.MOCK_EXAM
    
    active_stmt = select(ExamSession).where(
        and_(
            ExamSession.user_id == user_id,
            ExamSession.status == ExamSessionStatus.IN_PROGRESS
        )
    )
    active_result = await db.execute(active_stmt)
    active_session = active_result.scalar_one_or_none()
    
    if active_session:
        if active_session.is_expired():
            await auto_submit_session(active_session.id, db)
        else:
            return await get_session_state(active_session.id, db)
    
    blueprint = await generate_exam_blueprint(
        user_id=user_id,
        db=db,
        exam_type=exam_type_enum,
        subject_id=subject_id
    )
    
    total_questions = sum(len(s.questions) for s in blueprint.sections)
    
    if total_questions == 0:
        return {
            "error": "No questions available for exam",
            "message": "Add practice questions to generate an exam blueprint"
        }
    
    session = ExamSession(
        user_id=user_id,
        exam_type=exam_type,
        subject_id=subject_id,
        blueprint_data=blueprint.to_dict(),
        total_marks=blueprint.total_marks,
        duration_minutes=blueprint.duration_minutes,
        started_at=datetime.utcnow(),
        status=ExamSessionStatus.IN_PROGRESS,
        total_questions=total_questions,
        questions_attempted=0
    )
    db.add(session)
    await db.flush()
    
    question_number = 0
    for section in blueprint.sections:
        for q in section.questions:
            question_number += 1
            answer = ExamAnswer(
                exam_session_id=session.id,
                question_id=q.question_id,
                section_label=section.section,
                question_number=question_number,
                marks_allocated=q.marks,
                answer_text=None,
                time_taken_seconds=0,
                word_count=0,
                is_flagged=False
            )
            db.add(answer)
    
    await db.commit()
    await db.refresh(session)
    
    logger.info(f"Started exam session {session.id} for user {user_id}")
    
    return await get_session_state(session.id, db)


async def get_session_state(
    session_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get current session state for frontend.
    
    Used for:
    - Initial load after starting exam
    - Session recovery after page refresh
    - Syncing timer and progress
    """
    session_stmt = select(ExamSession).where(ExamSession.id == session_id)
    session_result = await db.execute(session_stmt)
    session = session_result.scalar_one_or_none()
    
    if not session:
        return {"error": "Session not found"}
    
    if session.status == ExamSessionStatus.IN_PROGRESS and session.is_expired():
        await auto_submit_session(session_id, db)
        await db.refresh(session)
    
    answers_stmt = select(ExamAnswer).where(
        ExamAnswer.exam_session_id == session_id
    ).order_by(ExamAnswer.question_number)
    answers_result = await db.execute(answers_stmt)
    answers = answers_result.scalars().all()
    
    blueprint = session.blueprint_data
    
    sections_with_answers = []
    for section_data in blueprint.get("sections", []):
        section_answers = [a for a in answers if a.section_label == section_data["section"]]
        
        questions_with_state = []
        for q_data in section_data.get("questions", []):
            answer = next((a for a in section_answers if a.question_id == q_data["question_id"]), None)
            
            question_state = {
                **q_data,
                "answer_id": answer.id if answer else None,
                "is_attempted": answer.is_attempted() if answer else False,
                "is_flagged": answer.is_flagged if answer else False,
                "time_spent_seconds": answer.time_taken_seconds if answer else 0,
            }
            
            if session.status != ExamSessionStatus.IN_PROGRESS:
                question_state["user_answer"] = answer.answer_text if answer else None
            
            questions_with_state.append(question_state)
        
        sections_with_answers.append({
            "section": section_data["section"],
            "instructions": section_data["instructions"],
            "marks_per_question": section_data["marks_per_question"],
            "total_marks": section_data["total_marks"],
            "questions": questions_with_state
        })
    
    attempted_count = sum(1 for a in answers if a.is_attempted())
    flagged_count = sum(1 for a in answers if a.is_flagged)
    
    return {
        "session": session.to_dict(),
        "sections": sections_with_answers,
        "progress": {
            "attempted": attempted_count,
            "flagged": flagged_count,
            "total": session.total_questions,
            "percent_complete": round(attempted_count / session.total_questions * 100, 1) if session.total_questions > 0 else 0
        },
        "timer": {
            "remaining_seconds": session.get_remaining_seconds(),
            "duration_minutes": session.duration_minutes,
            "started_at": session.started_at.isoformat(),
            "is_expired": session.is_expired()
        }
    }


async def save_answer(
    session_id: int,
    answer_id: int,
    answer_text: str,
    time_spent_seconds: int,
    db: AsyncSession,
    user_id: int
) -> Dict[str, Any]:
    """
    Save/update an answer during exam.
    
    Rules:
    - Only works if session is in_progress
    - Tracks time spent
    - Calculates word count
    - Auto-saves (no explicit submit per question)
    """
    session_stmt = select(ExamSession).where(
        and_(
            ExamSession.id == session_id,
            ExamSession.user_id == user_id
        )
    )
    session_result = await db.execute(session_stmt)
    session = session_result.scalar_one_or_none()
    
    if not session:
        return {"error": "Session not found"}
    
    if session.status != ExamSessionStatus.IN_PROGRESS:
        return {"error": "Exam already submitted - answers locked"}
    
    if session.is_expired():
        await auto_submit_session(session_id, db)
        return {"error": "Exam time expired - auto-submitted"}
    
    answer_stmt = select(ExamAnswer).where(
        and_(
            ExamAnswer.id == answer_id,
            ExamAnswer.exam_session_id == session_id
        )
    )
    answer_result = await db.execute(answer_stmt)
    answer = answer_result.scalar_one_or_none()
    
    if not answer:
        return {"error": "Answer not found"}
    
    word_count = len(answer_text.split()) if answer_text else 0
    
    if not answer.first_viewed_at:
        answer.first_viewed_at = datetime.utcnow()
    
    answer.answer_text = answer_text
    answer.time_taken_seconds = time_spent_seconds
    answer.word_count = word_count
    answer.last_updated_at = datetime.utcnow()
    
    await db.commit()
    
    answers_stmt = select(ExamAnswer).where(
        ExamAnswer.exam_session_id == session_id
    )
    all_answers = await db.execute(answers_stmt)
    attempted_count = sum(1 for a in all_answers.scalars().all() if a.is_attempted())
    
    session.questions_attempted = attempted_count
    await db.commit()
    
    return {
        "success": True,
        "answer_id": answer.id,
        "word_count": word_count,
        "is_attempted": answer.is_attempted(),
        "remaining_seconds": session.get_remaining_seconds()
    }


async def toggle_flag(
    session_id: int,
    answer_id: int,
    db: AsyncSession,
    user_id: int
) -> Dict[str, Any]:
    """Toggle flag status for a question."""
    session_stmt = select(ExamSession).where(
        and_(
            ExamSession.id == session_id,
            ExamSession.user_id == user_id,
            ExamSession.status == ExamSessionStatus.IN_PROGRESS
        )
    )
    session_result = await db.execute(session_stmt)
    session = session_result.scalar_one_or_none()
    
    if not session:
        return {"error": "Session not found or already submitted"}
    
    answer_stmt = select(ExamAnswer).where(
        and_(
            ExamAnswer.id == answer_id,
            ExamAnswer.exam_session_id == session_id
        )
    )
    answer_result = await db.execute(answer_stmt)
    answer = answer_result.scalar_one_or_none()
    
    if not answer:
        return {"error": "Answer not found"}
    
    answer.is_flagged = not answer.is_flagged
    await db.commit()
    
    return {
        "success": True,
        "is_flagged": answer.is_flagged
    }


async def submit_exam(
    session_id: int,
    db: AsyncSession,
    user_id: int
) -> Dict[str, Any]:
    """
    Submit exam manually (user clicks submit).
    
    Actions:
    1. Mark session as completed
    2. Calculate total time taken
    3. Lock all answers
    4. Return summary
    """
    session_stmt = select(ExamSession).where(
        and_(
            ExamSession.id == session_id,
            ExamSession.user_id == user_id
        )
    )
    session_result = await db.execute(session_stmt)
    session = session_result.scalar_one_or_none()
    
    if not session:
        return {"error": "Session not found"}
    
    if session.status != ExamSessionStatus.IN_PROGRESS:
        return {"error": "Exam already submitted"}
    
    now = datetime.utcnow()
    total_time = int((now - session.started_at).total_seconds())
    
    answers_stmt = select(ExamAnswer).where(
        ExamAnswer.exam_session_id == session_id
    )
    answers_result = await db.execute(answers_stmt)
    answers = answers_result.scalars().all()
    
    attempted_count = sum(1 for a in answers if a.is_attempted())
    
    session.status = ExamSessionStatus.COMPLETED
    session.submitted_at = now
    session.total_time_taken_seconds = total_time
    session.questions_attempted = attempted_count
    
    await db.commit()
    
    logger.info(f"Exam session {session_id} submitted by user {user_id}")
    
    return await get_submission_summary(session_id, db)


async def auto_submit_session(
    session_id: int,
    db: AsyncSession
) -> None:
    """
    Auto-submit session when time expires.
    
    Called when:
    - Timer reaches zero
    - Session recovery finds expired session
    """
    session_stmt = select(ExamSession).where(ExamSession.id == session_id)
    session_result = await db.execute(session_stmt)
    session = session_result.scalar_one_or_none()
    
    if not session or session.status != ExamSessionStatus.IN_PROGRESS:
        return
    
    total_time = session.duration_minutes * 60
    
    answers_stmt = select(ExamAnswer).where(
        ExamAnswer.exam_session_id == session_id
    )
    answers_result = await db.execute(answers_stmt)
    answers = answers_result.scalars().all()
    attempted_count = sum(1 for a in answers if a.is_attempted())
    
    session.status = ExamSessionStatus.AUTO_SUBMITTED
    session.submitted_at = datetime.utcnow()
    session.total_time_taken_seconds = total_time
    session.questions_attempted = attempted_count
    
    await db.commit()
    
    logger.info(f"Exam session {session_id} auto-submitted due to time expiry")


async def get_submission_summary(
    session_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get summary after exam submission.
    
    Shows:
    - Total questions attempted
    - Time taken
    - Section-wise breakdown
    - Completion status
    """
    session_stmt = select(ExamSession).where(ExamSession.id == session_id)
    session_result = await db.execute(session_stmt)
    session = session_result.scalar_one_or_none()
    
    if not session:
        return {"error": "Session not found"}
    
    answers_stmt = select(ExamAnswer).where(
        ExamAnswer.exam_session_id == session_id
    ).order_by(ExamAnswer.question_number)
    answers_result = await db.execute(answers_stmt)
    answers = answers_result.scalars().all()
    
    section_stats = {}
    for answer in answers:
        section = answer.section_label or "General"
        if section not in section_stats:
            section_stats[section] = {
                "total": 0,
                "attempted": 0,
                "flagged": 0,
                "total_marks": 0,
                "time_spent_seconds": 0
            }
        
        section_stats[section]["total"] += 1
        section_stats[section]["total_marks"] += answer.marks_allocated
        section_stats[section]["time_spent_seconds"] += answer.time_taken_seconds or 0
        
        if answer.is_attempted():
            section_stats[section]["attempted"] += 1
        if answer.is_flagged:
            section_stats[section]["flagged"] += 1
    
    attempted_count = sum(1 for a in answers if a.is_attempted())
    total_word_count = sum(a.word_count or 0 for a in answers)
    
    return {
        "session_id": session.id,
        "exam_type": session.exam_type,
        "status": session.status.value,
        "total_questions": session.total_questions,
        "questions_attempted": attempted_count,
        "questions_unattempted": session.total_questions - attempted_count,
        "total_marks": session.total_marks,
        "time_allowed_seconds": session.duration_minutes * 60,
        "time_taken_seconds": session.total_time_taken_seconds,
        "time_remaining_seconds": max(0, (session.duration_minutes * 60) - (session.total_time_taken_seconds or 0)),
        "total_word_count": total_word_count,
        "section_stats": section_stats,
        "started_at": session.started_at.isoformat(),
        "submitted_at": session.submitted_at.isoformat() if session.submitted_at else None,
        "completion_percent": round(attempted_count / session.total_questions * 100, 1) if session.total_questions > 0 else 0
    }


async def get_user_exam_history(
    user_id: int,
    db: AsyncSession,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Get user's exam session history."""
    stmt = (
        select(ExamSession)
        .where(ExamSession.user_id == user_id)
        .order_by(ExamSession.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    
    return [
        {
            "id": s.id,
            "exam_type": s.exam_type,
            "subject_name": s.subject.title if s.subject else "General",
            "status": s.status.value,
            "total_marks": s.total_marks,
            "total_questions": s.total_questions,
            "questions_attempted": s.questions_attempted,
            "duration_minutes": s.duration_minutes,
            "time_taken_seconds": s.total_time_taken_seconds,
            "started_at": s.started_at.isoformat(),
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
        }
        for s in sessions
    ]
