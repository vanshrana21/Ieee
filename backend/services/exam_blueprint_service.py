"""
backend/services/exam_blueprint_service.py
Phase 7.1: Exam Blueprint Engine for Indian Law Universities

SYSTEM GOAL:
Create a deterministic, exam-accurate blueprint generator that models how 
Indian law university exams are structured.

NO AI CALLS - ALL LOGIC IS DETERMINISTIC
NO HARDCODED SYLLABUS LOGIC
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from dataclasses import dataclass

from backend.orm.user import User
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum
from backend.orm.content_module import ContentModule
from backend.orm.practice_question import PracticeQuestion, QuestionType
from backend.orm.topic_mastery import TopicMastery
from backend.services.study_priority_engine import compute_topic_priority, WEAK_MASTERY

logger = logging.getLogger(__name__)

class ExamType(str, Enum):
    INTERNAL = "internal_assessment"
    END_SEM = "end_semester"
    UNIT_TEST = "unit_test"
    MOCK = "mock_exam"

@dataclass
class ExamSection:
    section_label: str
    instructions: str
    marks_per_question: int
    question_count: int
    question_type: Optional[QuestionType] = None

# Exam Structure Definitions
EXAM_STRUCTURES = {
    ExamType.INTERNAL: {
        "total_marks": 25,
        "duration_minutes": 60,
        "sections": [
            ExamSection("A", "Answer all short notes (5 marks each)", 5, 2),
            ExamSection("B", "Answer one long question (15 marks)", 15, 1)
        ]
    },
    ExamType.END_SEM: {
        "total_marks": 80,
        "duration_minutes": 180,
        "sections": [
            ExamSection("A", "Answer 4 short notes (5 marks each)", 5, 4),
            ExamSection("B", "Answer 3 analytical questions (10 marks each)", 10, 3),
            ExamSection("C", "Answer 2 essay questions (15 marks each)", 15, 2)
        ]
    },
    ExamType.UNIT_TEST: {
        "total_marks": 15,
        "duration_minutes": 45,
        "sections": [
            ExamSection("A", "Answer 3 short questions (5 marks each)", 5, 3)
        ]
    },
    ExamType.MOCK: {
        "total_marks": 80,
        "duration_minutes": 180,
        "sections": [
            ExamSection("A", "Short Notes - Answer 4 (5 marks each)", 5, 4),
            ExamSection("B", "Analytical Questions - Answer 3 (10 marks each)", 10, 3),
            ExamSection("C", "Essay/Case Analysis - Answer 2 (15 marks each)", 15, 2)
        ]
    }
}

async def generate_exam_blueprint(
    user_id: int,
    exam_type: ExamType,
    subject_id: Optional[int],
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Generate a deterministic exam blueprint.
    
    Logic:
    1. Identify target subjects (specific or all current semester).
    2. Rank topics using Priority Engine.
    3. Match questions to exam structure sections.
    4. Generate explanations for each selection.
    """
    logger.info(f"Generating blueprint: user={user_id}, type={exam_type}, subject={subject_id}")
    
    # 1. Fetch user and semester context
    user_stmt = select(User).where(User.id == user_id)
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    semester = user.current_semester or 1
    
    # 2. Identify subjects
    target_subjects = []
    if subject_id:
        target_subjects = [subject_id]
    elif user.course_id:
        curriculum_stmt = select(CourseCurriculum.subject_id).where(
            and_(
                CourseCurriculum.course_id == user.course_id,
                CourseCurriculum.semester_number == semester,
                CourseCurriculum.is_active == True
            )
        )
        curr_result = await db.execute(curriculum_stmt)
        target_subjects = [row[0] for row in curr_result.fetchall()]
    
    if not target_subjects:
        # Fallback to any subjects the user has progress in
        from backend.orm.subject_progress import SubjectProgress
        sp_stmt = select(SubjectProgress.subject_id).where(SubjectProgress.user_id == user_id)
        sp_result = await db.execute(sp_stmt)
        target_subjects = [row[0] for row in sp_result.fetchall()]
    
    if not target_subjects:
        # Final fallback
        subj_stmt = select(Subject.id).limit(3)
        subj_result = await db.execute(subj_stmt)
        target_subjects = [row[0] for row in subj_result.fetchall()]

    # 3. Get Topic Priorities
    all_topic_priorities = []
    for sid in target_subjects:
        priorities = await compute_topic_priority(user_id, sid, db, semester)
        all_topic_priorities.extend(priorities)
    
    # Sort by priority score (highest first = weakest topics)
    all_topic_priorities.sort(key=lambda x: x["priority_score"], reverse=True)
    
    # 4. Fetch available questions for target subjects
    questions_stmt = select(PracticeQuestion).where(
        PracticeQuestion.subject_id.in_(target_subjects)
    )
    q_result = await db.execute(questions_stmt)
    available_questions = q_result.scalars().all()
    
    # Organize questions by marks
    questions_by_marks = {5: [], 10: [], 15: [], "other": []}
    for q in available_questions:
        marks = q.marks or 5
        if marks in questions_by_marks:
            questions_by_marks[marks].append(q)
        else:
            questions_by_marks["other"].append(q)
            
    # 5. Build Blueprint Sections
    structure = EXAM_STRUCTURES.get(exam_type, EXAM_STRUCTURES[ExamType.MOCK])
    blueprint_sections = []
    used_question_ids = set()
    used_topic_tags = set()
    
    for sec_def in structure["sections"]:
        section_questions = []
        target_marks = sec_def.marks_per_question
        candidates = questions_by_marks.get(target_marks, [])
        
        # Priority Selection: Iterate through ranked topics
        for priority_item in all_topic_priorities:
            if len(section_questions) >= sec_def.question_count:
                break
            
            topic_tag = priority_item["topic_tag"]
            # No consecutive same topics in different sections if possible, 
            # but here we just avoid same topic in same section
            if topic_tag in used_topic_tags:
                continue
                
            # Find a question for this topic with correct marks
            topic_q = next((q for q in candidates 
                           if q.id not in used_question_ids 
                           and (q.tags and topic_tag in q.tags)), None)
            
            if topic_q:
                section_questions.append({
                    "question_id": topic_q.id,
                    "text_preview": topic_q.question_text[:150] + "...",
                    "marks": target_marks,
                    "type": topic_q.question_type.value if topic_q.question_type else "unknown",
                    "topic_tag": topic_tag,
                    "why_selected": f"{priority_item['priority']} priority topic: {priority_item['mastery_percent']}% mastery. {priority_item['explanation']}",
                    "mastery_reference": f"{priority_item['mastery_percent']}%",
                    "syllabus_reference": f"Subject ID: {topic_q.subject_id}"
                })
                used_question_ids.add(topic_q.id)
                used_topic_tags.add(topic_tag)

        # Fill remaining slots with any questions of that marks
        if len(section_questions) < sec_def.question_count:
            for q in candidates:
                if len(section_questions) >= sec_def.question_count:
                    break
                if q.id not in used_question_ids:
                    section_questions.append({
                        "question_id": q.id,
                        "text_preview": q.question_text[:150] + "...",
                        "marks": target_marks,
                        "type": q.question_type.value if q.question_type else "unknown",
                        "topic_tag": q.tags.split(',')[0] if q.tags else "General",
                        "why_selected": "Syllabus coverage requirement",
                        "mastery_reference": "N/A",
                        "syllabus_reference": f"Subject ID: {q.subject_id}"
                    })
                    used_question_ids.add(q.id)

        blueprint_sections.append({
            "section": sec_def.section_label,
            "instructions": sec_def.instructions,
            "questions": section_questions
        })

    # Summary
    total_assigned_marks = sum(
        len(sec["questions"]) * structure["sections"][i].marks_per_question
        for i, sec in enumerate(blueprint_sections)
    )

    return {
        "exam_type": exam_type.value,
        "total_marks": structure["total_marks"],
        "assigned_marks": total_assigned_marks,
        "duration_minutes": structure["duration_minutes"],
        "sections": blueprint_sections,
        "metadata": {
            "generated_at": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "semester": semester,
            "subjects_covered": target_subjects,
            "topic_rank_count": len(all_topic_priorities)
        }
    }
