"""
backend/services/exam_readiness_service.py
Phase 7.4: Exam Readiness Index (ERI) & Performance Diagnostics Engine

SYSTEM PURPOSE:
Translate all learning, practice, and exam data into a single readiness score
that answers: "Am I ready for the exam?"

ERI FORMULA:
============
ERI = (Knowledge × 0.35) + (Application × 0.30) + (Strategy × 0.20) + (Consistency × 0.15)

COMPONENTS:
1. KNOWLEDGE READINESS (35% weight):
   - Subject mastery from topic_mastery table
   - Topic coverage percentage
   - Weighted by question importance

2. APPLICATION READINESS (30% weight):
   - Case analysis performance from exam evaluations
   - Essay application quality from rubric scores
   - Application criterion scores

3. EXAM STRATEGY READINESS (20% weight):
   - Time management from exam sessions
   - Question completion rate
   - Time distribution efficiency

4. CONSISTENCY & CONFIDENCE (15% weight):
   - Attempt frequency (study streak)
   - Performance stability (score variance)
   - Trend direction (improving/declining)

ERI BANDS:
- 80-100: Exam Ready
- 60-79: Almost Ready
- 40-59: Needs Revision
- < 40: High Risk

ALL LOGIC IS DETERMINISTIC - NO ML BLACK BOXES
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import statistics
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from backend.orm.topic_mastery import TopicMastery
from backend.orm.subject_progress import SubjectProgress
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_evaluation import PracticeEvaluation
from backend.orm.practice_question import PracticeQuestion, QuestionType
from backend.orm.exam_session import ExamSession, ExamSessionStatus
from backend.orm.exam_answer import ExamAnswer
from backend.orm.exam_evaluation import ExamAnswerEvaluation, ExamSessionEvaluation
from backend.orm.content_module import ContentModule
from backend.orm.subject import Subject

logger = logging.getLogger(__name__)

KNOWLEDGE_WEIGHT = 0.35
APPLICATION_WEIGHT = 0.30
STRATEGY_WEIGHT = 0.20
CONSISTENCY_WEIGHT = 0.15

ERI_BANDS = [
    {"min": 80, "max": 100, "band": "Exam Ready", "color": "green", "message": "You are well prepared for the exam."},
    {"min": 60, "max": 79.99, "band": "Almost Ready", "color": "blue", "message": "Good progress, focus on weak areas."},
    {"min": 40, "max": 59.99, "band": "Needs Revision", "color": "orange", "message": "Increase practice intensity."},
    {"min": 0, "max": 39.99, "band": "High Risk", "color": "red", "message": "Significant preparation needed."},
]

RECENCY_DECAY = 0.95
DAYS_LOOKBACK = 30
MIN_ATTEMPTS_FOR_CONFIDENCE = 5
OPTIMAL_TIME_RATIO = 0.85


def get_eri_band(score: float) -> Dict[str, Any]:
    """Determine ERI band based on score."""
    for band in ERI_BANDS:
        if band["min"] <= score <= band["max"]:
            return {
                "band": band["band"],
                "color": band["color"],
                "message": band["message"]
            }
    return {"band": "Unknown", "color": "gray", "message": "Unable to determine readiness"}


async def calculate_knowledge_readiness(
    user_id: int,
    db: AsyncSession,
    subject_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Calculate Knowledge Readiness component (35% of ERI).
    
    Formula:
    Knowledge = (Subject Mastery × 0.60) + (Topic Coverage × 0.40)
    
    Subject Mastery: Weighted average of topic mastery scores
    Topic Coverage: % of topics with at least 1 attempt
    
    Data Sources:
    - topic_mastery table
    - subject_progress table
    - practice_questions (for total topic count)
    """
    
    mastery_stmt = select(TopicMastery).where(TopicMastery.user_id == user_id)
    if subject_id:
        mastery_stmt = mastery_stmt.where(TopicMastery.subject_id == subject_id)
    
    mastery_result = await db.execute(mastery_stmt)
    masteries = mastery_result.scalars().all()
    
    if not masteries:
        return {
            "score": 0,
            "subject_mastery": 0,
            "topic_coverage": 0,
            "topics_practiced": 0,
            "total_topics": 0,
            "weak_topics": [],
            "strong_topics": [],
            "explanation": "No practice data available yet",
            "data_source": "topic_mastery"
        }
    
    total_weighted_mastery = 0
    total_weight = 0
    weak_topics = []
    strong_topics = []
    
    for m in masteries:
        weight = max(m.attempt_count, 1)
        mastery_pct = m.mastery_score * 100
        total_weighted_mastery += mastery_pct * weight
        total_weight += weight
        
        if mastery_pct < 40:
            weak_topics.append({
                "topic": m.topic_tag,
                "mastery": round(mastery_pct, 1),
                "attempts": m.attempt_count
            })
        elif mastery_pct >= 70:
            strong_topics.append({
                "topic": m.topic_tag,
                "mastery": round(mastery_pct, 1),
                "attempts": m.attempt_count
            })
    
    subject_mastery = total_weighted_mastery / total_weight if total_weight > 0 else 0
    
    all_topics_stmt = select(func.count(func.distinct(PracticeQuestion.tags))).join(
        ContentModule, PracticeQuestion.module_id == ContentModule.id
    )
    if subject_id:
        all_topics_stmt = all_topics_stmt.where(ContentModule.subject_id == subject_id)
    
    topics_result = await db.execute(all_topics_stmt)
    total_topics_raw = topics_result.scalar() or 0
    
    total_topics = max(total_topics_raw, len(masteries))
    topics_practiced = len(masteries)
    
    topic_coverage = (topics_practiced / total_topics * 100) if total_topics > 0 else 0
    
    knowledge_score = (subject_mastery * 0.60) + (topic_coverage * 0.40)
    
    weak_topics.sort(key=lambda x: x["mastery"])
    strong_topics.sort(key=lambda x: x["mastery"], reverse=True)
    
    explanation_parts = []
    if subject_mastery < 50:
        explanation_parts.append(f"Average mastery is {subject_mastery:.1f}% (below 50%)")
    if topic_coverage < 70:
        explanation_parts.append(f"Only {topic_coverage:.1f}% of topics practiced")
    if not explanation_parts:
        explanation_parts.append(f"Good knowledge base with {subject_mastery:.1f}% mastery")
    
    return {
        "score": round(knowledge_score, 2),
        "subject_mastery": round(subject_mastery, 2),
        "topic_coverage": round(topic_coverage, 2),
        "topics_practiced": topics_practiced,
        "total_topics": total_topics,
        "weak_topics": weak_topics[:5],
        "strong_topics": strong_topics[:5],
        "explanation": "; ".join(explanation_parts),
        "data_source": "topic_mastery, subject_progress"
    }


async def calculate_application_readiness(
    user_id: int,
    db: AsyncSession,
    subject_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Calculate Application Readiness component (30% of ERI).
    
    Formula:
    Application = (Case Analysis Score × 0.50) + (Essay Quality × 0.50)
    
    Case Analysis: Average score on case_analysis questions
    Essay Quality: Average "application" rubric criterion score
    
    Data Sources:
    - exam_answer_evaluations (rubric_breakdown)
    - practice_evaluations (rubric_breakdown)
    """
    
    eval_stmt = select(ExamAnswerEvaluation).join(
        ExamSession, ExamAnswerEvaluation.exam_session_id == ExamSession.id
    ).where(
        and_(
            ExamSession.user_id == user_id,
            ExamAnswerEvaluation.status == "evaluated"
        )
    )
    
    if subject_id:
        eval_stmt = eval_stmt.where(ExamSession.subject_id == subject_id)
    
    eval_stmt = eval_stmt.order_by(desc(ExamAnswerEvaluation.evaluated_at)).limit(50)
    
    eval_result = await db.execute(eval_stmt)
    evaluations = eval_result.scalars().all()
    
    case_scores = []
    application_scores = []
    total_marks = []
    
    for ev in evaluations:
        if ev.marks_awarded is not None and ev.max_marks:
            total_marks.append((ev.marks_awarded / ev.max_marks) * 100)
        
        if ev.rubric_breakdown:
            for criterion in ev.rubric_breakdown:
                criteria_name = criterion.get("criteria", "").lower()
                if "application" in criteria_name:
                    max_score = criterion.get("max", 1)
                    score = criterion.get("score", 0)
                    if max_score > 0:
                        application_scores.append((score / max_score) * 100)
    
    practice_eval_stmt = select(PracticeEvaluation, PracticeAttempt).join(
        PracticeAttempt, PracticeEvaluation.practice_attempt_id == PracticeAttempt.id
    ).join(
        PracticeQuestion, PracticeAttempt.practice_question_id == PracticeQuestion.id
    ).where(
        and_(
            PracticeAttempt.user_id == user_id,
            PracticeEvaluation.status.in_(["completed", "evaluated"])
        )
    )
    
    practice_result = await db.execute(practice_eval_stmt)
    practice_evals = practice_result.all()
    
    for pe, pa in practice_evals:
        if pe.rubric_breakdown:
            for criterion in pe.rubric_breakdown:
                criteria_name = criterion.get("criteria", "").lower()
                if "application" in criteria_name:
                    max_score = criterion.get("max", 1)
                    score = criterion.get("score", 0)
                    if max_score > 0:
                        application_scores.append((score / max_score) * 100)
    
    if not total_marks and not application_scores:
        return {
            "score": 0,
            "case_analysis_score": 0,
            "essay_quality_score": 0,
            "evaluations_analyzed": 0,
            "explanation": "No evaluated answers found - complete mock exams to get application score",
            "data_source": "exam_answer_evaluations, practice_evaluations"
        }
    
    case_analysis_score = statistics.mean(total_marks) if total_marks else 0
    essay_quality_score = statistics.mean(application_scores) if application_scores else case_analysis_score
    
    application_score = (case_analysis_score * 0.50) + (essay_quality_score * 0.50)
    
    explanation_parts = []
    if case_analysis_score < 50:
        explanation_parts.append(f"Case analysis average is {case_analysis_score:.1f}%")
    if essay_quality_score < 50:
        explanation_parts.append(f"Application in answers needs improvement ({essay_quality_score:.1f}%)")
    if not explanation_parts:
        explanation_parts.append(f"Good application skills with {application_score:.1f}% average")
    
    return {
        "score": round(application_score, 2),
        "case_analysis_score": round(case_analysis_score, 2),
        "essay_quality_score": round(essay_quality_score, 2),
        "evaluations_analyzed": len(evaluations) + len(practice_evals),
        "explanation": "; ".join(explanation_parts),
        "data_source": "exam_answer_evaluations, practice_evaluations"
    }


async def calculate_strategy_readiness(
    user_id: int,
    db: AsyncSession,
    subject_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Calculate Exam Strategy Readiness component (20% of ERI).
    
    Formula:
    Strategy = (Time Management × 0.50) + (Completion Rate × 0.30) + (Distribution × 0.20)
    
    Time Management: % of exams completed within allotted time
    Completion Rate: % of questions attempted
    Distribution: Balance of time across questions
    
    Data Sources:
    - exam_sessions
    - exam_answers
    """
    
    session_stmt = select(ExamSession).where(
        and_(
            ExamSession.user_id == user_id,
            ExamSession.status.in_([ExamSessionStatus.COMPLETED, ExamSessionStatus.AUTO_SUBMITTED])
        )
    )
    
    if subject_id:
        session_stmt = session_stmt.where(ExamSession.subject_id == subject_id)
    
    session_stmt = session_stmt.order_by(desc(ExamSession.submitted_at)).limit(10)
    
    session_result = await db.execute(session_stmt)
    sessions = session_result.scalars().all()
    
    if not sessions:
        return {
            "score": 0,
            "time_management": 0,
            "completion_rate": 0,
            "time_distribution": 0,
            "exams_analyzed": 0,
            "time_issues": [],
            "explanation": "No completed exams - take mock exams to assess strategy",
            "data_source": "exam_sessions"
        }
    
    time_management_scores = []
    completion_rates = []
    distribution_scores = []
    time_issues = []
    
    for session in sessions:
        time_allowed = session.duration_minutes * 60
        time_taken = session.total_time_taken_seconds or time_allowed
        
        if time_taken <= time_allowed * OPTIMAL_TIME_RATIO:
            time_score = 100
        elif time_taken <= time_allowed:
            overshoot = (time_taken - (time_allowed * OPTIMAL_TIME_RATIO)) / (time_allowed * (1 - OPTIMAL_TIME_RATIO))
            time_score = max(70, 100 - (overshoot * 30))
        else:
            time_score = 50
            time_issues.append({
                "exam_id": session.id,
                "issue": "Time exceeded",
                "severity": "high"
            })
        
        if session.status == ExamSessionStatus.AUTO_SUBMITTED:
            time_score = max(time_score - 20, 0)
            time_issues.append({
                "exam_id": session.id,
                "issue": "Auto-submitted (time ran out)",
                "severity": "high"
            })
        
        time_management_scores.append(time_score)
        
        completion = (session.questions_attempted / session.total_questions * 100) if session.total_questions > 0 else 0
        completion_rates.append(completion)
        
        answers_stmt = select(ExamAnswer).where(ExamAnswer.exam_session_id == session.id)
        answers_result = await db.execute(answers_stmt)
        answers = answers_result.scalars().all()
        
        if answers and len(answers) > 1:
            time_per_question = [a.time_taken_seconds or 0 for a in answers]
            if any(t > 0 for t in time_per_question):
                avg_time = statistics.mean([t for t in time_per_question if t > 0])
                variance = statistics.variance(time_per_question) if len(time_per_question) > 1 else 0
                cv = (variance ** 0.5 / avg_time) if avg_time > 0 else 0
                dist_score = max(0, 100 - (cv * 50))
                distribution_scores.append(dist_score)
    
    time_management = statistics.mean(time_management_scores) if time_management_scores else 0
    completion_rate = statistics.mean(completion_rates) if completion_rates else 0
    time_distribution = statistics.mean(distribution_scores) if distribution_scores else 50
    
    strategy_score = (
        time_management * 0.50 +
        completion_rate * 0.30 +
        time_distribution * 0.20
    )
    
    explanation_parts = []
    if time_management < 70:
        explanation_parts.append(f"Time management needs work ({time_management:.1f}%)")
    if completion_rate < 80:
        explanation_parts.append(f"Only {completion_rate:.1f}% questions attempted on average")
    if not explanation_parts:
        explanation_parts.append(f"Good exam strategy with {strategy_score:.1f}% effectiveness")
    
    return {
        "score": round(strategy_score, 2),
        "time_management": round(time_management, 2),
        "completion_rate": round(completion_rate, 2),
        "time_distribution": round(time_distribution, 2),
        "exams_analyzed": len(sessions),
        "time_issues": time_issues[:3],
        "explanation": "; ".join(explanation_parts),
        "data_source": "exam_sessions, exam_answers"
    }


async def calculate_consistency_readiness(
    user_id: int,
    db: AsyncSession,
    subject_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Calculate Consistency & Confidence component (15% of ERI).
    
    Formula:
    Consistency = (Frequency × 0.40) + (Stability × 0.35) + (Trend × 0.25)
    
    Frequency: Study streak and practice regularity
    Stability: Score variance (lower variance = higher score)
    Trend: Are scores improving over time?
    
    Data Sources:
    - practice_attempts (frequency)
    - exam_session_evaluations (stability)
    """
    
    now = datetime.utcnow()
    lookback = now - timedelta(days=DAYS_LOOKBACK)
    
    attempt_stmt = select(
        func.date(PracticeAttempt.attempted_at).label("attempt_date"),
        func.count(PracticeAttempt.id).label("count")
    ).where(
        and_(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.attempted_at >= lookback
        )
    ).group_by(func.date(PracticeAttempt.attempted_at))
    
    attempt_result = await db.execute(attempt_stmt)
    daily_attempts = {str(row.attempt_date): row.count for row in attempt_result.fetchall()}
    
    practice_days = len(daily_attempts)
    total_days = DAYS_LOOKBACK
    
    frequency_score = min((practice_days / (total_days * 0.5)) * 100, 100)
    
    streak = 0
    current_date = now.date()
    while str(current_date) in daily_attempts or str(current_date - timedelta(days=1)) in daily_attempts:
        if str(current_date) in daily_attempts:
            streak += 1
        current_date -= timedelta(days=1)
        if streak > 30:
            break
    
    eval_stmt = select(ExamSessionEvaluation).join(
        ExamSession, ExamSessionEvaluation.exam_session_id == ExamSession.id
    ).where(
        and_(
            ExamSession.user_id == user_id,
            ExamSessionEvaluation.status == "evaluated"
        )
    ).order_by(desc(ExamSessionEvaluation.evaluated_at)).limit(10)
    
    eval_result = await db.execute(eval_stmt)
    evaluations = eval_result.scalars().all()
    
    if len(evaluations) >= 2:
        percentages = [e.percentage for e in evaluations if e.percentage is not None]
        if len(percentages) >= 2:
            variance = statistics.variance(percentages)
            stability_score = max(0, 100 - (variance / 2))
            
            first_half = percentages[len(percentages)//2:]
            second_half = percentages[:len(percentages)//2]
            
            first_avg = statistics.mean(first_half) if first_half else 0
            second_avg = statistics.mean(second_half) if second_half else 0
            
            if second_avg > first_avg + 5:
                trend_score = 100
                trend_direction = "improving"
            elif second_avg >= first_avg - 5:
                trend_score = 70
                trend_direction = "stable"
            else:
                trend_score = 40
                trend_direction = "declining"
        else:
            stability_score = 50
            trend_score = 50
            trend_direction = "insufficient_data"
    else:
        stability_score = 50
        trend_score = 50
        trend_direction = "insufficient_data"
    
    consistency_score = (
        frequency_score * 0.40 +
        stability_score * 0.35 +
        trend_score * 0.25
    )
    
    explanation_parts = []
    if frequency_score < 50:
        explanation_parts.append(f"Only practiced {practice_days} days in last month")
    if stability_score < 60:
        explanation_parts.append("Performance varies significantly between exams")
    if trend_direction == "declining":
        explanation_parts.append("Recent performance shows decline - review weak areas")
    if not explanation_parts:
        explanation_parts.append(f"Consistent practice with {streak}-day streak")
    
    return {
        "score": round(consistency_score, 2),
        "frequency_score": round(frequency_score, 2),
        "stability_score": round(stability_score, 2),
        "trend_score": round(trend_score, 2),
        "trend_direction": trend_direction,
        "study_streak": streak,
        "practice_days": practice_days,
        "exams_analyzed": len(evaluations),
        "explanation": "; ".join(explanation_parts),
        "data_source": "practice_attempts, exam_session_evaluations"
    }


async def calculate_eri(
    user_id: int,
    db: AsyncSession,
    subject_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Calculate complete Exam Readiness Index (ERI).
    
    ERI = (Knowledge × 0.35) + (Application × 0.30) + (Strategy × 0.20) + (Consistency × 0.15)
    
    Returns fully explainable score with component breakdown.
    """
    
    logger.info(f"Calculating ERI for user={user_id}, subject={subject_id}")
    
    knowledge = await calculate_knowledge_readiness(user_id, db, subject_id)
    application = await calculate_application_readiness(user_id, db, subject_id)
    strategy = await calculate_strategy_readiness(user_id, db, subject_id)
    consistency = await calculate_consistency_readiness(user_id, db, subject_id)
    
    eri_score = (
        knowledge["score"] * KNOWLEDGE_WEIGHT +
        application["score"] * APPLICATION_WEIGHT +
        strategy["score"] * STRATEGY_WEIGHT +
        consistency["score"] * CONSISTENCY_WEIGHT
    )
    
    band_info = get_eri_band(eri_score)
    
    impact_analysis = []
    
    impact_analysis.append({
        "component": "Knowledge",
        "score": knowledge["score"],
        "weight": KNOWLEDGE_WEIGHT,
        "contribution": round(knowledge["score"] * KNOWLEDGE_WEIGHT, 2),
        "max_contribution": round(100 * KNOWLEDGE_WEIGHT, 2),
        "impact_percent": round(knowledge["score"] * KNOWLEDGE_WEIGHT / max(eri_score, 1) * 100, 1) if eri_score > 0 else 0
    })
    
    impact_analysis.append({
        "component": "Application",
        "score": application["score"],
        "weight": APPLICATION_WEIGHT,
        "contribution": round(application["score"] * APPLICATION_WEIGHT, 2),
        "max_contribution": round(100 * APPLICATION_WEIGHT, 2),
        "impact_percent": round(application["score"] * APPLICATION_WEIGHT / max(eri_score, 1) * 100, 1) if eri_score > 0 else 0
    })
    
    impact_analysis.append({
        "component": "Strategy",
        "score": strategy["score"],
        "weight": STRATEGY_WEIGHT,
        "contribution": round(strategy["score"] * STRATEGY_WEIGHT, 2),
        "max_contribution": round(100 * STRATEGY_WEIGHT, 2),
        "impact_percent": round(strategy["score"] * STRATEGY_WEIGHT / max(eri_score, 1) * 100, 1) if eri_score > 0 else 0
    })
    
    impact_analysis.append({
        "component": "Consistency",
        "score": consistency["score"],
        "weight": CONSISTENCY_WEIGHT,
        "contribution": round(consistency["score"] * CONSISTENCY_WEIGHT, 2),
        "max_contribution": round(100 * CONSISTENCY_WEIGHT, 2),
        "impact_percent": round(consistency["score"] * CONSISTENCY_WEIGHT / max(eri_score, 1) * 100, 1) if eri_score > 0 else 0
    })
    
    return {
        "eri_score": round(eri_score, 2),
        "band": band_info["band"],
        "band_color": band_info["color"],
        "band_message": band_info["message"],
        "components": {
            "knowledge": knowledge,
            "application": application,
            "strategy": strategy,
            "consistency": consistency
        },
        "impact_analysis": impact_analysis,
        "subject_id": subject_id,
        "calculated_at": datetime.utcnow().isoformat()
    }


async def generate_diagnostics(
    user_id: int,
    db: AsyncSession,
    subject_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Generate comprehensive diagnostic report.
    
    Includes:
    - Strength summary
    - Weak topic list
    - Time management issues
    - Marks leakage analysis
    - Priority fixes (Top 5)
    """
    
    eri_data = await calculate_eri(user_id, db, subject_id)
    
    strength_summary = []
    weak_topics = []
    time_issues = []
    marks_leakage = []
    priority_fixes = []
    
    knowledge = eri_data["components"]["knowledge"]
    if knowledge["strong_topics"]:
        strength_summary.extend([
            f"Strong in {t['topic']} ({t['mastery']}% mastery)"
            for t in knowledge["strong_topics"][:3]
        ])
    
    if knowledge["weak_topics"]:
        weak_topics = knowledge["weak_topics"]
        for t in weak_topics[:3]:
            priority_fixes.append({
                "action": f"Focus on {t['topic']}",
                "reason": f"Only {t['mastery']}% mastery with {t['attempts']} attempts",
                "impact": "high",
                "category": "knowledge"
            })
    
    strategy = eri_data["components"]["strategy"]
    if strategy["time_issues"]:
        time_issues = strategy["time_issues"]
        if any(i["severity"] == "high" for i in time_issues):
            priority_fixes.append({
                "action": "Practice time management",
                "reason": "Time issues detected in recent exams",
                "impact": "high",
                "category": "strategy"
            })
    
    if strategy["completion_rate"] < 90:
        marks_leakage.append({
            "issue": "Incomplete attempts",
            "impact_percent": round(100 - strategy["completion_rate"], 1),
            "recommendation": "Attempt all questions even if unsure"
        })
    
    application = eri_data["components"]["application"]
    if application["essay_quality_score"] < 60:
        marks_leakage.append({
            "issue": "Weak application in answers",
            "impact_percent": round(60 - application["essay_quality_score"], 1),
            "recommendation": "Practice applying law to facts explicitly"
        })
        priority_fixes.append({
            "action": "Improve legal application skills",
            "reason": f"Application score is {application['essay_quality_score']:.1f}%",
            "impact": "high",
            "category": "application"
        })
    
    consistency = eri_data["components"]["consistency"]
    if consistency["trend_direction"] == "declining":
        priority_fixes.append({
            "action": "Review recent weak areas",
            "reason": "Performance trend is declining",
            "impact": "medium",
            "category": "consistency"
        })
    
    if consistency["study_streak"] < 3:
        priority_fixes.append({
            "action": "Establish daily practice routine",
            "reason": f"Current streak is only {consistency['study_streak']} days",
            "impact": "medium",
            "category": "consistency"
        })
    
    priority_fixes = sorted(
        priority_fixes,
        key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["impact"], 2)
    )[:5]
    
    return {
        "eri": eri_data,
        "diagnostics": {
            "strength_summary": strength_summary,
            "weak_topics": weak_topics,
            "time_management_issues": time_issues,
            "marks_leakage": marks_leakage,
            "priority_fixes": priority_fixes
        },
        "recommendations": [fix["action"] for fix in priority_fixes],
        "generated_at": datetime.utcnow().isoformat()
    }


async def get_eri_trend(
    user_id: int,
    db: AsyncSession,
    days: int = 30
) -> List[Dict[str, Any]]:
    """
    Get ERI trend data for visualization.
    
    Returns daily/weekly ERI approximations based on exam results.
    """
    
    lookback = datetime.utcnow() - timedelta(days=days)
    
    eval_stmt = select(ExamSessionEvaluation, ExamSession).join(
        ExamSession, ExamSessionEvaluation.exam_session_id == ExamSession.id
    ).where(
        and_(
            ExamSession.user_id == user_id,
            ExamSession.submitted_at >= lookback,
            ExamSessionEvaluation.status == "evaluated"
        )
    ).order_by(ExamSession.submitted_at)
    
    eval_result = await db.execute(eval_stmt)
    results = eval_result.all()
    
    trend_data = []
    for se, s in results:
        if se.percentage is not None:
            trend_data.append({
                "date": s.submitted_at.strftime("%Y-%m-%d"),
                "exam_percentage": se.percentage,
                "exam_id": s.id,
                "grade": se.grade_band
            })
    
    return trend_data


async def compare_readiness_by_subject(
    user_id: int,
    db: AsyncSession
) -> List[Dict[str, Any]]:
    """
    Compare ERI across all subjects for the user.
    
    Returns list of subjects with their respective ERI scores.
    """
    
    progress_stmt = select(SubjectProgress).where(
        SubjectProgress.user_id == user_id
    )
    progress_result = await db.execute(progress_stmt)
    progresses = progress_result.scalars().all()
    
    subject_ids = [p.subject_id for p in progresses]
    
    comparisons = []
    for subject_id in subject_ids:
        subject_stmt = select(Subject).where(Subject.id == subject_id)
        subject_result = await db.execute(subject_stmt)
        subject = subject_result.scalar_one_or_none()
        
        if subject:
            eri_data = await calculate_eri(user_id, db, subject_id)
            comparisons.append({
                "subject_id": subject_id,
                "subject_name": subject.title,
                "eri_score": eri_data["eri_score"],
                "band": eri_data["band"],
                "knowledge_score": eri_data["components"]["knowledge"]["score"],
                "application_score": eri_data["components"]["application"]["score"]
            })
    
    comparisons.sort(key=lambda x: x["eri_score"], reverse=True)
    
    return comparisons
