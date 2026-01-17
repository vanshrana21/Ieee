"""
backend/services/exam_evaluation_service.py
Phase 7.3: Explainable Exam Evaluation & Rubric Engine

SYSTEM PURPOSE:
Evaluate mock exam answers mirroring Indian law professors' assessment style.

EVALUATION PHILOSOPHY:
- Rubric-based, not subjective
- Explainable to the student
- Deterministic (same answer → same score)
- No hallucinated expectations

RUBRIC DIMENSIONS:
1. Issue Identification
2. Legal Principles / Authorities
3. Application to Facts
4. Structure & Clarity
5. Conclusion / Holding

MARKS ALLOCATION:
Dynamic based on question marks - NOT hardcoded ratios.
"""

import logging
import re
import json
import os
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.orm.exam_session import ExamSession, ExamSessionStatus
from backend.orm.exam_answer import ExamAnswer
from backend.orm.exam_evaluation import ExamAnswerEvaluation, ExamSessionEvaluation
from backend.orm.practice_question import PracticeQuestion, QuestionType

logger = logging.getLogger(__name__)


@dataclass
class RubricCriteria:
    """Single rubric criterion with weight and scoring rules."""
    name: str
    weight: float
    max_marks: float
    description: str
    scoring_guide: Dict[str, str]


@dataclass
class RubricTemplate:
    """Complete rubric template for a question type and marks."""
    question_type: str
    total_marks: int
    criteria: List[RubricCriteria]
    
    def get_marks_allocation(self) -> Dict[str, float]:
        return {c.name: c.max_marks for c in self.criteria}


RUBRIC_WEIGHTS = {
    "issue_identification": 0.20,
    "legal_principles": 0.30,
    "application": 0.30,
    "structure_clarity": 0.10,
    "conclusion": 0.10,
}

RUBRIC_WEIGHTS_BY_TYPE = {
    QuestionType.ESSAY: {
        "issue_identification": 0.15,
        "legal_principles": 0.30,
        "application": 0.30,
        "structure_clarity": 0.15,
        "conclusion": 0.10,
    },
    QuestionType.CASE_ANALYSIS: {
        "issue_identification": 0.25,
        "legal_principles": 0.25,
        "application": 0.35,
        "structure_clarity": 0.08,
        "conclusion": 0.07,
    },
    QuestionType.SHORT_ANSWER: {
        "issue_identification": 0.20,
        "legal_principles": 0.35,
        "application": 0.25,
        "structure_clarity": 0.10,
        "conclusion": 0.10,
    },
}

CRITERIA_DESCRIPTIONS = {
    "issue_identification": "Identification and framing of the legal issue(s)",
    "legal_principles": "Statement of relevant legal principles, provisions, and authorities",
    "application": "Application of law to the facts of the problem",
    "structure_clarity": "Organization, clarity of expression, and logical flow",
    "conclusion": "Clear conclusion or holding with reasoning",
}

SCORING_GUIDES = {
    "issue_identification": {
        "excellent": "Issue(s) clearly identified and precisely framed with legal terminology",
        "good": "Issue(s) identified but framing could be more precise",
        "average": "Partial identification of issues, some missing",
        "poor": "Issues not properly identified or misunderstood",
        "not_attempted": "No attempt to identify the issue",
    },
    "legal_principles": {
        "excellent": "Comprehensive citation of relevant provisions, case laws, and principles",
        "good": "Good coverage of main legal principles with some citations",
        "average": "Basic principles mentioned but limited citations",
        "poor": "Incomplete or incorrect statement of law",
        "not_attempted": "No legal principles stated",
    },
    "application": {
        "excellent": "Thorough application of law to facts with nuanced analysis",
        "good": "Good application with clear reasoning",
        "average": "Basic application but lacking depth",
        "poor": "Superficial or incorrect application",
        "not_attempted": "No application attempted",
    },
    "structure_clarity": {
        "excellent": "Well-organized with clear paragraphs and logical flow",
        "good": "Generally well-structured with minor improvements possible",
        "average": "Acceptable structure but could be clearer",
        "poor": "Disorganized or difficult to follow",
        "not_attempted": "No coherent structure",
    },
    "conclusion": {
        "excellent": "Clear, well-reasoned conclusion that follows from analysis",
        "good": "Conclusion present and generally supported by analysis",
        "average": "Conclusion present but weakly supported",
        "poor": "Conclusion missing or contradicts analysis",
        "not_attempted": "No conclusion provided",
    },
}

GRADE_BANDS = [
    {"min": 75, "max": 100, "grade": "Distinction", "description": "Outstanding performance"},
    {"min": 60, "max": 74.99, "grade": "First Class", "description": "Very good performance"},
    {"min": 50, "max": 59.99, "grade": "Second Class", "description": "Good performance"},
    {"min": 40, "max": 49.99, "grade": "Pass", "description": "Satisfactory performance"},
    {"min": 0, "max": 39.99, "grade": "Fail", "description": "Below passing standard"},
]


def generate_rubric_template(
    question_type: QuestionType,
    total_marks: int
) -> RubricTemplate:
    """
    Generate a rubric template with dynamic marks allocation.
    
    Marks are distributed based on question type weights.
    """
    weights = RUBRIC_WEIGHTS_BY_TYPE.get(question_type, RUBRIC_WEIGHTS)
    
    criteria = []
    for criterion_key, weight in weights.items():
        max_marks = round(total_marks * weight, 1)
        
        criteria.append(RubricCriteria(
            name=criterion_key,
            weight=weight,
            max_marks=max_marks,
            description=CRITERIA_DESCRIPTIONS.get(criterion_key, ""),
            scoring_guide=SCORING_GUIDES.get(criterion_key, {}),
        ))
    
    return RubricTemplate(
        question_type=question_type.value if question_type else "short_answer",
        total_marks=total_marks,
        criteria=criteria,
    )


def calculate_criterion_score(
    criterion: RubricCriteria,
    answer_text: str,
    question: PracticeQuestion,
    word_count: int
) -> Tuple[float, str, str]:
    """
    Calculate score for a single rubric criterion.
    
    Uses deterministic keyword-based analysis + structural checks.
    Returns: (score, performance_level, feedback)
    """
    if not answer_text or not answer_text.strip():
        return 0, "not_attempted", "No answer provided for this criterion"
    
    text_lower = answer_text.lower()
    max_marks = criterion.max_marks
    
    expected_keywords = extract_expected_keywords(question)
    
    if criterion.name == "issue_identification":
        score, level, feedback = evaluate_issue_identification(
            text_lower, expected_keywords, max_marks, question
        )
    elif criterion.name == "legal_principles":
        score, level, feedback = evaluate_legal_principles(
            text_lower, expected_keywords, max_marks, question
        )
    elif criterion.name == "application":
        score, level, feedback = evaluate_application(
            text_lower, expected_keywords, max_marks, question
        )
    elif criterion.name == "structure_clarity":
        score, level, feedback = evaluate_structure(
            answer_text, word_count, max_marks
        )
    elif criterion.name == "conclusion":
        score, level, feedback = evaluate_conclusion(
            text_lower, max_marks
        )
    else:
        score = max_marks * 0.5
        level = "average"
        feedback = "Standard evaluation applied"
    
    return round(score, 2), level, feedback


def extract_expected_keywords(question: PracticeQuestion) -> List[str]:
    """Extract expected keywords from question guidelines and correct answer."""
    keywords = []
    
    if question.tags:
        keywords.extend([t.strip().lower() for t in question.tags.split(",")])
    
    if question.correct_answer:
        answer_lower = question.correct_answer.lower()
        legal_terms = re.findall(r'\b[a-z]{4,}\b', answer_lower)
        keywords.extend(legal_terms[:20])
    
    legal_keywords = [
        "section", "article", "act", "provision", "statute", "precedent",
        "plaintiff", "defendant", "appellant", "respondent", "petitioner",
        "court", "judgment", "held", "ratio", "obiter", "dictum",
        "contract", "tort", "crime", "negligence", "liability",
        "consideration", "offer", "acceptance", "breach", "damages",
        "fundamental rights", "constitutional", "amendment", "jurisdiction"
    ]
    keywords.extend(legal_keywords)
    
    return list(set(keywords))


def evaluate_issue_identification(
    text: str,
    keywords: List[str],
    max_marks: float,
    question: PracticeQuestion
) -> Tuple[float, str, str]:
    """Evaluate issue identification criterion."""
    
    issue_indicators = [
        "issue", "question", "matter", "whether", "problem",
        "arises", "concerns", "relates to", "pertains to"
    ]
    
    indicator_count = sum(1 for ind in issue_indicators if ind in text)
    keyword_matches = sum(1 for kw in keywords[:10] if kw in text)
    
    question_lower = question.question.lower() if question.question else ""
    question_keywords = re.findall(r'\b[a-z]{4,}\b', question_lower)[:5]
    question_keyword_matches = sum(1 for kw in question_keywords if kw in text)
    
    if indicator_count >= 2 and keyword_matches >= 3 and question_keyword_matches >= 2:
        return max_marks * 0.9, "excellent", "Issue clearly identified and well-framed"
    elif indicator_count >= 1 and keyword_matches >= 2:
        return max_marks * 0.75, "good", "Issue identified but framing could be more precise"
    elif indicator_count >= 1 or keyword_matches >= 1:
        return max_marks * 0.5, "average", "Partial identification of the issue"
    else:
        return max_marks * 0.25, "poor", "Issue not properly identified"


def evaluate_legal_principles(
    text: str,
    keywords: List[str],
    max_marks: float,
    question: PracticeQuestion
) -> Tuple[float, str, str]:
    """Evaluate legal principles and authorities criterion."""
    
    section_refs = len(re.findall(r'section\s+\d+', text, re.IGNORECASE))
    article_refs = len(re.findall(r'article\s+\d+', text, re.IGNORECASE))
    case_refs = len(re.findall(r'v\.\s|versus|v\s', text, re.IGNORECASE))
    act_refs = len(re.findall(r'\bact\s*(,|\s|of|19|20)', text, re.IGNORECASE))
    
    legal_terms = [
        "provision", "statute", "principle", "doctrine", "rule",
        "held", "established", "precedent", "ratio decidendi", "binding"
    ]
    term_matches = sum(1 for term in legal_terms if term in text)
    
    keyword_matches = sum(1 for kw in keywords if kw in text)
    
    total_citations = section_refs + article_refs + case_refs + act_refs
    
    if total_citations >= 3 and term_matches >= 3 and keyword_matches >= 5:
        return max_marks * 0.9, "excellent", "Comprehensive citation of relevant legal authorities"
    elif total_citations >= 2 and term_matches >= 2:
        return max_marks * 0.75, "good", "Good coverage of legal principles with some citations"
    elif total_citations >= 1 or term_matches >= 2:
        return max_marks * 0.5, "average", "Basic principles mentioned but limited citations"
    else:
        return max_marks * 0.3, "poor", "Incomplete statement of legal principles"


def evaluate_application(
    text: str,
    keywords: List[str],
    max_marks: float,
    question: PracticeQuestion
) -> Tuple[float, str, str]:
    """Evaluate application to facts criterion."""
    
    application_indicators = [
        "in this case", "in the present", "applying", "therefore",
        "hence", "thus", "accordingly", "here", "given facts",
        "on the facts", "based on", "considering"
    ]
    
    reasoning_indicators = [
        "because", "since", "as", "due to", "reason",
        "consequently", "result", "follows", "leads to"
    ]
    
    app_count = sum(1 for ind in application_indicators if ind in text)
    reason_count = sum(1 for ind in reasoning_indicators if ind in text)
    keyword_matches = sum(1 for kw in keywords if kw in text)
    
    if app_count >= 3 and reason_count >= 3 and keyword_matches >= 4:
        return max_marks * 0.9, "excellent", "Thorough application with nuanced analysis"
    elif app_count >= 2 and reason_count >= 2:
        return max_marks * 0.75, "good", "Good application with clear reasoning"
    elif app_count >= 1 or reason_count >= 1:
        return max_marks * 0.5, "average", "Basic application but lacking depth"
    else:
        return max_marks * 0.25, "poor", "Superficial application of law to facts"


def evaluate_structure(
    text: str,
    word_count: int,
    max_marks: float
) -> Tuple[float, str, str]:
    """Evaluate structure and clarity criterion."""
    
    paragraphs = text.split('\n\n')
    paragraph_count = len([p for p in paragraphs if p.strip()])
    
    sentences = re.split(r'[.!?]+', text)
    sentence_count = len([s for s in sentences if s.strip()])
    
    avg_sentence_length = word_count / max(sentence_count, 1)
    
    structure_indicators = [
        "firstly", "secondly", "thirdly", "finally", "moreover",
        "furthermore", "in addition", "however", "nevertheless",
        "on the other hand", "in conclusion", "to summarize"
    ]
    structure_count = sum(1 for ind in structure_indicators if ind.lower() in text.lower())
    
    score = 0
    
    if paragraph_count >= 3:
        score += max_marks * 0.3
    elif paragraph_count >= 2:
        score += max_marks * 0.2
    
    if 15 <= avg_sentence_length <= 30:
        score += max_marks * 0.3
    elif 10 <= avg_sentence_length <= 40:
        score += max_marks * 0.2
    
    if structure_count >= 3:
        score += max_marks * 0.4
    elif structure_count >= 1:
        score += max_marks * 0.25
    
    if score >= max_marks * 0.8:
        return score, "excellent", "Well-organized with clear logical flow"
    elif score >= max_marks * 0.6:
        return score, "good", "Generally well-structured"
    elif score >= max_marks * 0.4:
        return score, "average", "Acceptable structure but could be clearer"
    else:
        return max(score, max_marks * 0.2), "poor", "Organization needs improvement"


def evaluate_conclusion(
    text: str,
    max_marks: float
) -> Tuple[float, str, str]:
    """Evaluate conclusion criterion."""
    
    conclusion_indicators = [
        "conclusion", "conclude", "therefore", "thus", "hence",
        "accordingly", "in summary", "to summarize", "finally",
        "in light of", "it is submitted", "it follows"
    ]
    
    conclusive_statements = [
        "liable", "not liable", "valid", "invalid", "entitled",
        "not entitled", "succeed", "fail", "guilty", "not guilty",
        "binding", "void", "voidable", "enforceable"
    ]
    
    conclusion_count = sum(1 for ind in conclusion_indicators if ind in text)
    statement_count = sum(1 for stmt in conclusive_statements if stmt in text)
    
    last_portion = text[-500:] if len(text) > 500 else text
    conclusion_in_end = any(ind in last_portion for ind in conclusion_indicators)
    
    if conclusion_count >= 2 and statement_count >= 1 and conclusion_in_end:
        return max_marks * 0.9, "excellent", "Clear, well-reasoned conclusion"
    elif conclusion_count >= 1 and statement_count >= 1:
        return max_marks * 0.75, "good", "Conclusion present and supported"
    elif conclusion_count >= 1 or statement_count >= 1:
        return max_marks * 0.5, "average", "Conclusion present but weakly supported"
    else:
        return max_marks * 0.2, "poor", "Conclusion missing or unclear"


def evaluate_answer_with_rubric(
    answer: ExamAnswer,
    question: PracticeQuestion
) -> Dict[str, Any]:
    """
    Evaluate a single answer using the rubric engine.
    
    Returns complete evaluation with rubric breakdown.
    """
    question_type = question.question_type or QuestionType.SHORT_ANSWER
    max_marks = answer.marks_allocated or question.marks
    
    rubric = generate_rubric_template(question_type, max_marks)
    
    answer_text = answer.answer_text or ""
    word_count = answer.word_count or len(answer_text.split())
    
    if not answer_text.strip():
        return {
            "marks_awarded": 0,
            "max_marks": max_marks,
            "rubric_breakdown": [
                {
                    "criteria": c.name.replace("_", " ").title(),
                    "score": 0,
                    "max": c.max_marks,
                    "feedback": "No answer provided",
                    "performance_level": "not_attempted"
                }
                for c in rubric.criteria
            ],
            "overall_feedback": "No answer was provided for this question.",
            "strengths": [],
            "improvements": ["Attempt all questions even if unsure"],
            "examiner_tone": "neutral-academic"
        }
    
    rubric_breakdown = []
    total_score = 0
    strengths = []
    improvements = []
    
    for criterion in rubric.criteria:
        score, level, feedback = calculate_criterion_score(
            criterion, answer_text, question, word_count
        )
        
        total_score += score
        
        rubric_breakdown.append({
            "criteria": criterion.name.replace("_", " ").title(),
            "score": score,
            "max": criterion.max_marks,
            "feedback": feedback,
            "performance_level": level
        })
        
        if level in ["excellent", "good"]:
            strengths.append(f"{criterion.name.replace('_', ' ').title()}: {feedback}")
        elif level in ["poor", "not_attempted"]:
            improvements.append(f"{criterion.name.replace('_', ' ').title()}: {criterion.scoring_guide.get('good', 'Improve this area')}")
    
    percentage = (total_score / max_marks) * 100 if max_marks > 0 else 0
    
    if percentage >= 75:
        overall_tone = "Strong answer demonstrating good legal understanding"
    elif percentage >= 60:
        overall_tone = "Good attempt with room for improvement in specific areas"
    elif percentage >= 40:
        overall_tone = "Average response - focus on strengthening legal analysis"
    else:
        overall_tone = "Needs significant improvement - review fundamentals"
    
    return {
        "marks_awarded": round(total_score, 2),
        "max_marks": max_marks,
        "rubric_breakdown": rubric_breakdown,
        "overall_feedback": overall_tone,
        "strengths": strengths[:3],
        "improvements": improvements[:3],
        "examiner_tone": "neutral-academic"
    }


def determine_grade_band(percentage: float) -> Dict[str, str]:
    """Determine grade band based on percentage."""
    for band in GRADE_BANDS:
        if band["min"] <= percentage <= band["max"]:
            return {"grade": band["grade"], "description": band["description"]}
    return {"grade": "Ungraded", "description": "Score outside normal range"}


async def evaluate_exam_session(
    session_id: int,
    db: AsyncSession,
    force_reevaluate: bool = False
) -> Dict[str, Any]:
    """
    Evaluate an entire exam session.
    
    Process:
    1. Check session is submitted
    2. Evaluate each answer with rubric
    3. Calculate aggregate scores
    4. Generate session-level feedback
    5. Store evaluations
    
    Returns complete evaluation results.
    """
    session_stmt = select(ExamSession).where(ExamSession.id == session_id)
    session_result = await db.execute(session_stmt)
    session = session_result.scalar_one_or_none()
    
    if not session:
        return {"error": "Session not found"}
    
    if session.status == ExamSessionStatus.IN_PROGRESS:
        return {"error": "Cannot evaluate an in-progress exam"}
    
    existing_stmt = select(ExamSessionEvaluation).where(
        ExamSessionEvaluation.exam_session_id == session_id
    )
    existing_result = await db.execute(existing_stmt)
    existing_eval = existing_result.scalar_one_or_none()
    
    if existing_eval and existing_eval.status == "evaluated" and not force_reevaluate:
        return await get_evaluation_results(session_id, db)
    
    answers_stmt = select(ExamAnswer).where(
        ExamAnswer.exam_session_id == session_id
    ).order_by(ExamAnswer.question_number)
    answers_result = await db.execute(answers_stmt)
    answers = answers_result.scalars().all()
    
    answer_evaluations = []
    section_scores = defaultdict(lambda: {"marks": 0, "max": 0, "count": 0})
    topic_scores = defaultdict(lambda: {"marks": 0, "max": 0})
    total_marks_awarded = 0
    total_marks_possible = 0
    
    for answer in answers:
        question = answer.question
        if not question:
            continue
        
        eval_result = evaluate_answer_with_rubric(answer, question)
        
        answer_eval_stmt = select(ExamAnswerEvaluation).where(
            ExamAnswerEvaluation.exam_answer_id == answer.id
        )
        answer_eval_result = await db.execute(answer_eval_stmt)
        answer_eval = answer_eval_result.scalar_one_or_none()
        
        if not answer_eval:
            answer_eval = ExamAnswerEvaluation(
                exam_answer_id=answer.id,
                exam_session_id=session_id,
                question_id=question.id,
                max_marks=eval_result["max_marks"]
            )
            db.add(answer_eval)
        
        answer_eval.marks_awarded = eval_result["marks_awarded"]
        answer_eval.rubric_breakdown = eval_result["rubric_breakdown"]
        answer_eval.overall_feedback = eval_result["overall_feedback"]
        answer_eval.strengths = eval_result["strengths"]
        answer_eval.improvements = eval_result["improvements"]
        answer_eval.examiner_tone = eval_result["examiner_tone"]
        answer_eval.status = "evaluated"
        answer_eval.evaluated_at = datetime.utcnow()
        answer_eval.evaluation_method = "rubric_fallback"
        answer_eval.confidence_score = 0.85
        
        answer_evaluations.append({
            "question_number": answer.question_number,
            "section": answer.section_label,
            **eval_result
        })
        
        total_marks_awarded += eval_result["marks_awarded"]
        total_marks_possible += eval_result["max_marks"]
        
        section = answer.section_label or "General"
        section_scores[section]["marks"] += eval_result["marks_awarded"]
        section_scores[section]["max"] += eval_result["max_marks"]
        section_scores[section]["count"] += 1
        
        if question.tags:
            for tag in question.tags.split(","):
                tag = tag.strip()
                topic_scores[tag]["marks"] += eval_result["marks_awarded"]
                topic_scores[tag]["max"] += eval_result["max_marks"]
    
    percentage = (total_marks_awarded / total_marks_possible * 100) if total_marks_possible > 0 else 0
    grade_info = determine_grade_band(percentage)
    
    section_breakdown = []
    for section, scores in section_scores.items():
        section_pct = (scores["marks"] / scores["max"] * 100) if scores["max"] > 0 else 0
        section_breakdown.append({
            "section": section,
            "marks_awarded": round(scores["marks"], 2),
            "max_marks": scores["max"],
            "percentage": round(section_pct, 1),
            "question_count": scores["count"]
        })
    
    strength_areas = []
    weak_areas = []
    for topic, scores in topic_scores.items():
        topic_pct = (scores["marks"] / scores["max"] * 100) if scores["max"] > 0 else 0
        if topic_pct >= 70:
            strength_areas.append(topic)
        elif topic_pct < 50:
            weak_areas.append(topic)
    
    if not existing_eval:
        session_eval = ExamSessionEvaluation(
            exam_session_id=session_id,
            total_marks_possible=total_marks_possible
        )
        db.add(session_eval)
    else:
        session_eval = existing_eval
    
    session_eval.total_marks_awarded = round(total_marks_awarded, 2)
    session_eval.total_marks_possible = total_marks_possible
    session_eval.percentage = round(percentage, 2)
    session_eval.grade_band = grade_info["grade"]
    session_eval.section_breakdown = section_breakdown
    session_eval.strength_areas = strength_areas[:5]
    session_eval.weak_areas = weak_areas[:5]
    session_eval.overall_feedback = generate_overall_feedback(percentage, grade_info["grade"])
    session_eval.performance_summary = {
        "questions_attempted": sum(1 for a in answers if a.is_attempted()),
        "total_questions": len(answers),
        "average_per_question": round(total_marks_awarded / len(answers), 2) if answers else 0,
        "time_taken_seconds": session.total_time_taken_seconds,
    }
    session_eval.status = "evaluated"
    session_eval.evaluated_at = datetime.utcnow()
    session_eval.evaluation_method = "rubric_fallback"
    
    await db.commit()
    
    logger.info(f"Evaluated exam session {session_id}: {percentage:.1f}% ({grade_info['grade']})")
    
    return await get_evaluation_results(session_id, db)


def generate_overall_feedback(percentage: float, grade: str) -> str:
    """Generate overall exam feedback based on performance."""
    
    if grade == "Distinction":
        return ("Excellent performance demonstrating strong command of legal principles. "
                "Your answers show clear issue identification, thorough application of law, "
                "and well-structured arguments. Continue developing your analytical skills.")
    elif grade == "First Class":
        return ("Very good performance with solid legal understanding. "
                "Your analysis is generally strong with good citation of authorities. "
                "Focus on strengthening your application and conclusion sections.")
    elif grade == "Second Class":
        return ("Good effort showing reasonable understanding of the subject matter. "
                "Work on citing more legal authorities and improving the depth of your analysis. "
                "Practice structuring answers with clear issue-rule-application-conclusion format.")
    elif grade == "Pass":
        return ("Satisfactory performance meeting minimum requirements. "
                "Significant improvement needed in legal reasoning and citation of authorities. "
                "Review fundamental concepts and practice answer writing with proper structure.")
    else:
        return ("Performance below passing standard. "
                "Focus on understanding core legal principles and their application. "
                "Practice identifying issues and structuring answers systematically. "
                "Consider seeking additional guidance on answer writing techniques.")


async def get_evaluation_results(
    session_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get complete evaluation results for a session.
    
    Returns structured data for frontend display.
    """
    session_eval_stmt = select(ExamSessionEvaluation).where(
        ExamSessionEvaluation.exam_session_id == session_id
    )
    session_eval_result = await db.execute(session_eval_stmt)
    session_eval = session_eval_result.scalar_one_or_none()
    
    if not session_eval:
        return {"error": "Evaluation not found", "status": "pending"}
    
    answer_evals_stmt = select(ExamAnswerEvaluation).where(
        ExamAnswerEvaluation.exam_session_id == session_id
    )
    answer_evals_result = await db.execute(answer_evals_stmt)
    answer_evals = answer_evals_result.scalars().all()
    
    session_stmt = select(ExamSession).where(ExamSession.id == session_id)
    session_result = await db.execute(session_stmt)
    session = session_result.scalar_one_or_none()
    
    return {
        "session_id": session_id,
        "exam_type": session.exam_type if session else None,
        "subject_name": session.subject.title if session and session.subject else None,
        "evaluation": session_eval.to_dict(),
        "answer_evaluations": [
            {
                **ae.to_dict(),
                "question_number": ae.exam_answer.question_number if ae.exam_answer else None,
                "section_label": ae.exam_answer.section_label if ae.exam_answer else None,
                "question_text": ae.exam_answer.question.question[:200] if ae.exam_answer and ae.exam_answer.question else None,
            }
            for ae in sorted(answer_evals, key=lambda x: x.exam_answer.question_number if x.exam_answer else 0)
        ],
        "grade_info": {
            "grade": session_eval.grade_band,
            "percentage": session_eval.percentage,
            "marks": f"{session_eval.total_marks_awarded}/{session_eval.total_marks_possible}"
        }
    }


async def get_rubric_template(
    question_type: str,
    marks: int
) -> Dict[str, Any]:
    """Get rubric template for a question type and marks allocation."""
    
    try:
        q_type = QuestionType(question_type)
    except ValueError:
        q_type = QuestionType.SHORT_ANSWER
    
    rubric = generate_rubric_template(q_type, marks)
    
    return {
        "question_type": rubric.question_type,
        "total_marks": rubric.total_marks,
        "criteria": [
            {
                "name": c.name.replace("_", " ").title(),
                "weight": c.weight,
                "max_marks": c.max_marks,
                "description": c.description,
                "scoring_guide": c.scoring_guide
            }
            for c in rubric.criteria
        ]
    }
