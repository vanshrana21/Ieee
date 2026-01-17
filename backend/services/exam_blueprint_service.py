"""
backend/services/exam_blueprint_service.py
Phase 7.1: Exam Blueprint Engine for Indian Law Universities

SYSTEM PURPOSE:
Create a deterministic, exam-accurate blueprint generator that models how Indian law
university exams are structured.

The blueprint defines:
- How many questions
- Of what type
- Of what marks
- From which subjects/topics
- In what pattern

EXAM STRUCTURE INFERENCE:
========================
The system dynamically infers exam structure from available data:
- Question type distribution from practice_questions
- Marks distribution patterns
- Topic importance from question frequency

QUESTION SELECTION RULES:
========================
1. Priority Order:
   - Weak topics > Medium topics > Strong topics
   - Current semester > Previous semester (revision)

2. Diversity Rules:
   - No two questions from same topic_tag consecutively
   - Mix theory + application questions

3. Fairness Rules:
   - No identical questions repeated
   - Similar topics only if mastery is low

NO AI CALLS - ALL LOGIC IS DETERMINISTIC
Same inputs → Same blueprint
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc, or_

from backend.orm.user import User
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum
from backend.orm.content_module import ContentModule, ModuleType
from backend.orm.practice_question import PracticeQuestion, QuestionType, Difficulty
from backend.orm.topic_mastery import TopicMastery
from backend.orm.subject_progress import SubjectProgress
from backend.orm.practice_attempt import PracticeAttempt
from backend.services.study_priority_engine import (
    compute_topic_priority,
    WEAK_MASTERY,
    STRONG_MASTERY,
)

logger = logging.getLogger(__name__)


class ExamType(str, Enum):
    INTERNAL_ASSESSMENT = "internal_assessment"
    END_SEMESTER = "end_semester"
    UNIT_TEST = "unit_test"
    MOCK_EXAM = "mock_exam"


EXAM_CONFIG = {
    ExamType.INTERNAL_ASSESSMENT: {
        "total_marks": 30,
        "duration_minutes": 60,
        "section_count": 2,
        "marks_distribution": [5, 10],
    },
    ExamType.END_SEMESTER: {
        "total_marks": 80,
        "duration_minutes": 180,
        "section_count": 3,
        "marks_distribution": [5, 10, 15],
    },
    ExamType.UNIT_TEST: {
        "total_marks": 20,
        "duration_minutes": 45,
        "section_count": 2,
        "marks_distribution": [5, 10],
    },
    ExamType.MOCK_EXAM: {
        "total_marks": 80,
        "duration_minutes": 180,
        "section_count": 3,
        "marks_distribution": [5, 10, 15],
    },
}

QUESTION_TYPE_FOR_MARKS = {
    5: [QuestionType.SHORT_ANSWER, QuestionType.MCQ],
    10: [QuestionType.SHORT_ANSWER, QuestionType.ESSAY],
    15: [QuestionType.ESSAY, QuestionType.CASE_ANALYSIS],
}

MASTERY_WEIGHT = 0.40
FREQUENCY_WEIGHT = 0.30
STALENESS_WEIGHT = 0.20
DIFFICULTY_WEIGHT = 0.10


@dataclass
class BlueprintQuestion:
    """A question selected for the exam blueprint."""
    question_id: int
    question_text: str
    marks: int
    question_type: str
    topic_tag: str
    subject_id: int
    subject_name: str
    difficulty: str
    why_selected: str
    mastery_reference: float
    syllabus_reference: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question_text": self.question_text[:200] + "..." if len(self.question_text) > 200 else self.question_text,
            "marks": self.marks,
            "type": self.question_type,
            "topic_tag": self.topic_tag,
            "subject_id": self.subject_id,
            "subject_name": self.subject_name,
            "difficulty": self.difficulty,
            "why_selected": self.why_selected,
            "mastery_reference": round(self.mastery_reference, 2),
            "syllabus_reference": self.syllabus_reference,
        }


@dataclass
class BlueprintSection:
    """A section within the exam blueprint."""
    section: str
    instructions: str
    marks_per_question: int
    total_marks: int
    questions: List[BlueprintQuestion]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "section": self.section,
            "instructions": self.instructions,
            "marks_per_question": self.marks_per_question,
            "total_marks": self.total_marks,
            "question_count": len(self.questions),
            "questions": [q.to_dict() for q in self.questions],
        }


@dataclass
class ExamBlueprint:
    """Complete exam blueprint with all sections and metadata."""
    exam_type: ExamType
    subject_id: Optional[int]
    subject_name: Optional[str]
    total_marks: int
    duration_minutes: int
    sections: List[BlueprintSection]
    generated_at: str
    user_id: int
    coverage_summary: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "exam_type": self.exam_type.value,
            "subject_id": self.subject_id,
            "subject_name": self.subject_name,
            "total_marks": self.total_marks,
            "duration_minutes": self.duration_minutes,
            "sections": [s.to_dict() for s in self.sections],
            "generated_at": self.generated_at,
            "user_id": self.user_id,
            "coverage_summary": self.coverage_summary,
            "total_questions": sum(len(s.questions) for s in self.sections),
        }


def calculate_question_score(
    question: PracticeQuestion,
    topic_mastery: float,
    days_since_practice: int,
    question_frequency: int,
    max_frequency: int
) -> Tuple[float, str]:
    """
    Calculate priority score for a question.
    
    Score = (Mastery Deficit × 0.40) + (Frequency × 0.30) + (Staleness × 0.20) + (Difficulty × 0.10)
    
    Returns:
        (score, explanation)
    """
    mastery_deficit = (100 - topic_mastery) / 100
    mastery_component = mastery_deficit * MASTERY_WEIGHT
    
    frequency_ratio = question_frequency / max(max_frequency, 1)
    frequency_component = frequency_ratio * FREQUENCY_WEIGHT
    
    staleness = min(days_since_practice / 30, 1.0)
    staleness_component = staleness * STALENESS_WEIGHT
    
    difficulty_map = {
        Difficulty.EASY: 0.3,
        Difficulty.MEDIUM: 0.6,
        Difficulty.HARD: 0.9,
    }
    difficulty_value = difficulty_map.get(question.difficulty, 0.5)
    
    if topic_mastery < WEAK_MASTERY:
        difficulty_value = 1 - (difficulty_value * 0.5)
    
    difficulty_component = difficulty_value * DIFFICULTY_WEIGHT
    
    total_score = mastery_component + frequency_component + staleness_component + difficulty_component
    
    explanations = []
    if topic_mastery < WEAK_MASTERY:
        explanations.append(f"Weak mastery ({topic_mastery:.0f}%)")
    elif topic_mastery < STRONG_MASTERY:
        explanations.append(f"Moderate mastery ({topic_mastery:.0f}%)")
    
    if days_since_practice > 14:
        explanations.append(f"not practiced in {days_since_practice} days")
    
    if frequency_ratio > 0.5:
        explanations.append("high exam frequency")
    
    explanation = " and ".join(explanations) if explanations else "balanced selection"
    
    return total_score, explanation


async def get_user_subject_ids(
    user_id: int,
    db: AsyncSession,
    specific_subject_id: Optional[int] = None
) -> List[int]:
    """Get subject IDs accessible to the user based on their course and semester."""
    
    if specific_subject_id:
        return [specific_subject_id]
    
    user_stmt = select(User).where(User.id == user_id)
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()
    
    if not user:
        return []
    
    subject_ids = []
    
    if user.course_id:
        curriculum_stmt = (
            select(CourseCurriculum.subject_id)
            .where(
                CourseCurriculum.course_id == user.course_id,
                CourseCurriculum.semester_number <= (user.current_semester or 1),
                CourseCurriculum.is_active == True
            )
        )
        curriculum_result = await db.execute(curriculum_stmt)
        subject_ids = [row[0] for row in curriculum_result.fetchall()]
    
    if not subject_ids:
        progress_stmt = select(SubjectProgress.subject_id).where(
            SubjectProgress.user_id == user_id
        )
        progress_result = await db.execute(progress_stmt)
        subject_ids = [row[0] for row in progress_result.fetchall()]
    
    if not subject_ids:
        subject_stmt = select(Subject.id).limit(3)
        subject_result = await db.execute(subject_stmt)
        subject_ids = [row[0] for row in subject_result.fetchall()]
    
    return subject_ids


async def fetch_topic_mastery_map(
    user_id: int,
    subject_ids: List[int],
    db: AsyncSession
) -> Dict[str, Dict[str, Any]]:
    """Fetch topic mastery data for all subjects."""
    
    mastery_stmt = select(TopicMastery).where(
        and_(
            TopicMastery.user_id == user_id,
            TopicMastery.subject_id.in_(subject_ids)
        )
    )
    mastery_result = await db.execute(mastery_stmt)
    masteries = mastery_result.scalars().all()
    
    now = datetime.utcnow()
    mastery_map = {}
    
    for m in masteries:
        days_since = 999
        if m.last_practiced_at:
            days_since = (now - m.last_practiced_at).days
        
        mastery_map[m.topic_tag] = {
            "mastery_score": m.mastery_score * 100 if m.mastery_score else 0,
            "subject_id": m.subject_id,
            "days_since_practice": days_since,
        }
    
    return mastery_map


async def fetch_question_frequency(
    subject_ids: List[int],
    db: AsyncSession
) -> Dict[str, int]:
    """Calculate question frequency per topic tag (proxy for exam importance)."""
    
    frequency_stmt = (
        select(PracticeQuestion.tags, func.count(PracticeQuestion.id).label("count"))
        .join(ContentModule, PracticeQuestion.module_id == ContentModule.id)
        .where(ContentModule.subject_id.in_(subject_ids))
        .group_by(PracticeQuestion.tags)
    )
    
    result = await db.execute(frequency_stmt)
    frequency_map = defaultdict(int)
    
    for row in result.fetchall():
        if row.tags:
            tags = row.tags.split(",") if isinstance(row.tags, str) else []
            for tag in tags:
                tag = tag.strip()
                if tag:
                    frequency_map[tag] += row.count
    
    return dict(frequency_map)


async def fetch_available_questions(
    subject_ids: List[int],
    marks_filter: Optional[int],
    question_types: Optional[List[QuestionType]],
    db: AsyncSession,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Fetch available questions matching criteria."""
    
    stmt = (
        select(PracticeQuestion, ContentModule, Subject)
        .join(ContentModule, PracticeQuestion.module_id == ContentModule.id)
        .join(Subject, ContentModule.subject_id == Subject.id)
        .where(ContentModule.subject_id.in_(subject_ids))
    )
    
    if marks_filter:
        stmt = stmt.where(PracticeQuestion.marks == marks_filter)
    
    if question_types:
        stmt = stmt.where(PracticeQuestion.question_type.in_(question_types))
    
    stmt = stmt.order_by(PracticeQuestion.id).limit(limit)
    
    result = await db.execute(stmt)
    questions = []
    
    for question, module, subject in result.fetchall():
        tags = question.tags.split(",") if question.tags else []
        tags = [t.strip() for t in tags if t.strip()]
        
        questions.append({
            "question": question,
            "module": module,
            "subject": subject,
            "tags": tags,
            "primary_tag": tags[0] if tags else "general",
        })
    
    return questions


def select_questions_for_section(
    available_questions: List[Dict[str, Any]],
    mastery_map: Dict[str, Dict[str, Any]],
    frequency_map: Dict[str, int],
    target_count: int,
    already_selected_ids: set,
    previous_topic: Optional[str]
) -> List[BlueprintQuestion]:
    """
    Select questions for a section using priority scoring.
    
    Rules:
    1. Weak topics prioritized
    2. No consecutive same topic_tag
    3. No duplicate questions
    4. Mix of theory and application
    """
    
    scored_questions = []
    max_frequency = max(frequency_map.values()) if frequency_map else 1
    
    for q_data in available_questions:
        question = q_data["question"]
        subject = q_data["subject"]
        primary_tag = q_data["primary_tag"]
        
        if question.id in already_selected_ids:
            continue
        
        mastery_data = mastery_map.get(primary_tag, {})
        topic_mastery = mastery_data.get("mastery_score", 50)
        days_since = mastery_data.get("days_since_practice", 30)
        
        frequency = frequency_map.get(primary_tag, 1)
        
        score, explanation = calculate_question_score(
            question, topic_mastery, days_since, frequency, max_frequency
        )
        
        scored_questions.append({
            "data": q_data,
            "score": score,
            "explanation": explanation,
            "topic_mastery": topic_mastery,
        })
    
    scored_questions.sort(key=lambda x: x["score"], reverse=True)
    
    selected = []
    last_topic = previous_topic
    
    for sq in scored_questions:
        if len(selected) >= target_count:
            break
        
        q_data = sq["data"]
        question = q_data["question"]
        subject = q_data["subject"]
        primary_tag = q_data["primary_tag"]
        
        if primary_tag == last_topic and len(selected) > 0:
            continue
        
        syllabus_ref = f"{subject.title}"
        if q_data["module"]:
            syllabus_ref += f" > {q_data['module'].title}"
        
        blueprint_q = BlueprintQuestion(
            question_id=question.id,
            question_text=question.question,
            marks=question.marks,
            question_type=question.question_type.value if question.question_type else "short_answer",
            topic_tag=primary_tag,
            subject_id=subject.id,
            subject_name=subject.title,
            difficulty=question.difficulty.value if question.difficulty else "medium",
            why_selected=sq["explanation"],
            mastery_reference=sq["topic_mastery"],
            syllabus_reference=syllabus_ref,
        )
        
        selected.append(blueprint_q)
        already_selected_ids.add(question.id)
        last_topic = primary_tag
    
    return selected


def get_section_instructions(marks: int, section_label: str) -> str:
    """Generate section instructions based on marks allocation."""
    
    if marks == 5:
        return f"Section {section_label}: Answer the following short notes. Each question carries 5 marks."
    elif marks == 10:
        return f"Section {section_label}: Answer any questions from this section. Each question carries 10 marks. Write comprehensive answers with relevant case laws."
    elif marks == 15:
        return f"Section {section_label}: Answer the following essay/case analysis questions. Each question carries 15 marks. Provide detailed analysis with case citations."
    else:
        return f"Section {section_label}: Answer the following questions. Each question carries {marks} marks."


async def infer_exam_structure(
    subject_ids: List[int],
    exam_type: ExamType,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Dynamically infer exam structure from available questions.
    
    Falls back to default config if insufficient data.
    """
    
    default_config = EXAM_CONFIG[exam_type]
    
    marks_stmt = (
        select(PracticeQuestion.marks, func.count(PracticeQuestion.id).label("count"))
        .join(ContentModule, PracticeQuestion.module_id == ContentModule.id)
        .where(ContentModule.subject_id.in_(subject_ids))
        .group_by(PracticeQuestion.marks)
        .order_by(desc("count"))
    )
    
    result = await db.execute(marks_stmt)
    marks_distribution = {row.marks: row.count for row in result.fetchall()}
    
    if not marks_distribution:
        return default_config
    
    available_marks = sorted(marks_distribution.keys())
    
    if len(available_marks) < 2:
        return default_config
    
    section_marks = []
    for m in default_config["marks_distribution"]:
        closest = min(available_marks, key=lambda x: abs(x - m))
        if closest not in section_marks or len(section_marks) < default_config["section_count"]:
            section_marks.append(closest)
    
    section_marks = sorted(set(section_marks))[:default_config["section_count"]]
    
    return {
        "total_marks": default_config["total_marks"],
        "duration_minutes": default_config["duration_minutes"],
        "section_count": len(section_marks),
        "marks_distribution": section_marks,
        "inferred": True,
    }


async def generate_exam_blueprint(
    user_id: int,
    db: AsyncSession,
    exam_type: ExamType = ExamType.MOCK_EXAM,
    subject_id: Optional[int] = None
) -> ExamBlueprint:
    """
    Generate a complete exam blueprint.
    
    Algorithm:
    1. Get user's accessible subjects
    2. Fetch topic mastery data
    3. Calculate question frequencies
    4. Infer exam structure
    5. Select questions per section
    6. Build blueprint with explanations
    
    Returns:
        ExamBlueprint with all sections and metadata
    """
    
    logger.info(f"Generating {exam_type.value} blueprint for user_id={user_id}")
    
    subject_ids = await get_user_subject_ids(user_id, db, subject_id)
    
    if not subject_ids:
        return ExamBlueprint(
            exam_type=exam_type,
            subject_id=subject_id,
            subject_name=None,
            total_marks=0,
            duration_minutes=0,
            sections=[],
            generated_at=datetime.utcnow().isoformat(),
            user_id=user_id,
            coverage_summary={
                "error": "No subjects available for exam generation",
                "message": "Enroll in subjects or start learning to generate exams"
            },
        )
    
    subject_name = None
    if subject_id:
        subject_stmt = select(Subject).where(Subject.id == subject_id)
        subject_result = await db.execute(subject_stmt)
        subject_obj = subject_result.scalar_one_or_none()
        if subject_obj:
            subject_name = subject_obj.title
    
    mastery_map = await fetch_topic_mastery_map(user_id, subject_ids, db)
    frequency_map = await fetch_question_frequency(subject_ids, db)
    
    exam_structure = await infer_exam_structure(subject_ids, exam_type, db)
    
    sections = []
    already_selected_ids = set()
    previous_topic = None
    section_labels = ["A", "B", "C", "D", "E"]
    
    topic_coverage = defaultdict(int)
    type_coverage = defaultdict(int)
    
    for idx, marks in enumerate(exam_structure["marks_distribution"]):
        section_label = section_labels[idx] if idx < len(section_labels) else str(idx + 1)
        
        preferred_types = QUESTION_TYPE_FOR_MARKS.get(marks, [QuestionType.SHORT_ANSWER])
        
        available = await fetch_available_questions(
            subject_ids, marks, preferred_types, db, limit=50
        )
        
        if not available:
            available = await fetch_available_questions(
                subject_ids, None, None, db, limit=50
            )
        
        questions_needed = exam_structure["total_marks"] // (marks * len(exam_structure["marks_distribution"]))
        questions_needed = max(2, min(questions_needed, 8))
        
        selected_questions = select_questions_for_section(
            available,
            mastery_map,
            frequency_map,
            questions_needed,
            already_selected_ids,
            previous_topic
        )
        
        if selected_questions:
            previous_topic = selected_questions[-1].topic_tag
        
        for q in selected_questions:
            topic_coverage[q.topic_tag] += 1
            type_coverage[q.question_type] += 1
        
        section = BlueprintSection(
            section=section_label,
            instructions=get_section_instructions(marks, section_label),
            marks_per_question=marks,
            total_marks=len(selected_questions) * marks,
            questions=selected_questions,
        )
        sections.append(section)
    
    actual_total_marks = sum(s.total_marks for s in sections)
    
    coverage_summary = {
        "topics_covered": len(topic_coverage),
        "topic_distribution": dict(topic_coverage),
        "question_types": dict(type_coverage),
        "subjects_covered": len(set(q.subject_id for s in sections for q in s.questions)),
        "weak_topics_targeted": sum(
            1 for tag in topic_coverage
            if mastery_map.get(tag, {}).get("mastery_score", 50) < WEAK_MASTERY
        ),
        "total_questions": sum(len(s.questions) for s in sections),
    }
    
    logger.info(f"Generated blueprint with {coverage_summary['total_questions']} questions")
    
    return ExamBlueprint(
        exam_type=exam_type,
        subject_id=subject_id,
        subject_name=subject_name,
        total_marks=actual_total_marks,
        duration_minutes=exam_structure["duration_minutes"],
        sections=sections,
        generated_at=datetime.utcnow().isoformat(),
        user_id=user_id,
        coverage_summary=coverage_summary,
    )


async def get_available_exam_types() -> List[Dict[str, Any]]:
    """Get all available exam types with their configurations."""
    
    return [
        {
            "type": exam_type.value,
            "display_name": exam_type.value.replace("_", " ").title(),
            "total_marks": config["total_marks"],
            "duration_minutes": config["duration_minutes"],
            "description": _get_exam_description(exam_type),
        }
        for exam_type, config in EXAM_CONFIG.items()
    ]


def _get_exam_description(exam_type: ExamType) -> str:
    """Get human-readable description for exam type."""
    
    descriptions = {
        ExamType.INTERNAL_ASSESSMENT: "30-mark internal assessment with short and medium questions",
        ExamType.END_SEMESTER: "80-mark comprehensive exam covering full syllabus",
        ExamType.UNIT_TEST: "20-mark unit test for quick assessment",
        ExamType.MOCK_EXAM: "Full mock exam simulating end-semester pattern",
    }
    return descriptions.get(exam_type, "Exam assessment")


async def validate_blueprint(blueprint: ExamBlueprint) -> Dict[str, Any]:
    """
    Validate a generated blueprint for completeness and balance.
    
    Returns validation report with warnings/issues.
    """
    
    issues = []
    warnings = []
    
    if not blueprint.sections:
        issues.append("No sections generated - insufficient questions available")
    
    total_questions = sum(len(s.questions) for s in blueprint.sections)
    if total_questions < 3:
        issues.append(f"Only {total_questions} questions available - exam may be too short")
    
    if blueprint.coverage_summary.get("topics_covered", 0) < 2:
        warnings.append("Limited topic diversity - consider adding more practice content")
    
    weak_targeted = blueprint.coverage_summary.get("weak_topics_targeted", 0)
    if weak_targeted == 0 and total_questions > 0:
        warnings.append("No weak topics targeted - exam may not focus on improvement areas")
    
    topic_dist = blueprint.coverage_summary.get("topic_distribution", {})
    if topic_dist:
        max_count = max(topic_dist.values())
        if max_count > total_questions * 0.5:
            warnings.append("Topic concentration too high - some topics overrepresented")
    
    return {
        "is_valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "question_count": total_questions,
        "sections_count": len(blueprint.sections),
    }
