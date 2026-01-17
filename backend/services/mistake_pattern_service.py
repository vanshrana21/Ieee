"""
backend/services/mistake_pattern_service.py
Phase 6.2: Mistake Pattern Detection & Diagnostic Intelligence

SYSTEM GOAL:
Detect WHY a student is underperforming — not just WHERE.

This module uses PURE LOGIC (no AI calls) to identify recurring academic weaknesses:
- Conceptual Weakness
- Structure Errors  
- Application Deficiency
- Time Management Issues
- Improvement Failure

NO HARDCODED RULES per subject - patterns emerge from data.
DETERMINISTIC - Same inputs = Same outputs.
EXPLAINABLE - Every pattern has evidence and explanation.
"""

import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum
from dataclasses import dataclass, field, asdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from sqlalchemy.orm import joinedload

from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_evaluation import PracticeEvaluation
from backend.orm.practice_question import PracticeQuestion, QuestionType
from backend.orm.topic_mastery import TopicMastery
from backend.orm.subject_progress import SubjectProgress

logger = logging.getLogger(__name__)


class PatternType(str, Enum):
    CONCEPTUAL_WEAKNESS = "CONCEPTUAL_WEAKNESS"
    STRUCTURE_ERROR = "STRUCTURE_ERROR"
    APPLICATION_DEFICIENCY = "APPLICATION_DEFICIENCY"
    TIME_MANAGEMENT_ISSUE = "TIME_MANAGEMENT_ISSUE"
    IMPROVEMENT_FAILURE = "IMPROVEMENT_FAILURE"
    CASE_INTEGRATION_GAP = "CASE_INTEGRATION_GAP"
    INCOMPLETE_COVERAGE = "INCOMPLETE_COVERAGE"
    REPEATED_MISTAKE = "REPEATED_MISTAKE"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SCORE_THRESHOLD_LOW = 40.0
SCORE_THRESHOLD_MEDIUM = 60.0
SCORE_THRESHOLD_PASS = 70.0

MIN_ATTEMPTS_FOR_PATTERN = 2
REATTEMPT_WINDOW_HOURS = 72
TIME_PER_MARK_SECONDS = 60
MINIMUM_TIME_RATIO = 0.3
IMPROVEMENT_THRESHOLD = 10.0

STRUCTURE_KEYWORDS = {
    "introduction": ["intro", "introduction", "opening", "preamble"],
    "conclusion": ["conclusion", "concluding", "summary", "final"],
    "issue_framing": ["issue", "framing", "problem", "question at hand"],
    "case_citation": ["case", "citation", "precedent", "ratio", "judgment"],
    "legal_principle": ["principle", "doctrine", "rule", "maxim"],
    "application": ["apply", "application", "facts", "circumstance", "scenario"],
}


@dataclass
class MistakePattern:
    """Data class for detected mistake pattern."""
    pattern_type: PatternType
    severity: Severity
    evidence: List[Dict[str, Any]]
    explanation: str
    recommended_fix: List[str]
    topic_tags: List[str] = field(default_factory=list)
    frequency: int = 1
    first_detected: Optional[str] = None
    last_detected: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_type": self.pattern_type.value,
            "severity": self.severity.value,
            "evidence": self.evidence,
            "explanation": self.explanation,
            "recommended_fix": self.recommended_fix,
            "topic_tags": self.topic_tags,
            "frequency": self.frequency,
            "first_detected": self.first_detected,
            "last_detected": self.last_detected,
        }


@dataclass
class DiagnosticReport:
    """Complete diagnostic report for a student."""
    user_id: int
    generated_at: str
    total_attempts_analyzed: int
    patterns: List[MistakePattern]
    summary: Dict[str, Any]
    topic_breakdown: Dict[str, Dict[str, Any]]
    recommendations: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "generated_at": self.generated_at,
            "total_attempts_analyzed": self.total_attempts_analyzed,
            "patterns": [p.to_dict() for p in self.patterns],
            "summary": self.summary,
            "topic_breakdown": self.topic_breakdown,
            "recommendations": self.recommendations,
        }


def calculate_severity(
    score: float,
    frequency: int,
    is_recurring: bool
) -> Severity:
    """
    Calculate severity based on score, frequency, and recurrence.
    
    Thresholds:
    - CRITICAL: score < 40 AND frequency >= 3 AND recurring
    - HIGH: score < 50 OR (frequency >= 3) OR recurring
    - MEDIUM: score < 60 OR frequency >= 2
    - LOW: otherwise
    """
    if score < SCORE_THRESHOLD_LOW and frequency >= 3 and is_recurring:
        return Severity.CRITICAL
    elif score < 50 or frequency >= 3 or is_recurring:
        return Severity.HIGH
    elif score < SCORE_THRESHOLD_MEDIUM or frequency >= 2:
        return Severity.MEDIUM
    return Severity.LOW


def extract_rubric_issues(rubric_breakdown: Dict) -> Dict[str, List[str]]:
    """
    Extract specific issues from rubric breakdown.
    Returns categorized issues.
    """
    issues = {
        "structure": [],
        "application": [],
        "concept": [],
        "case": [],
        "other": [],
    }
    
    if not rubric_breakdown:
        return issues
    
    missing_points = rubric_breakdown.get("missing_points", [])
    if isinstance(missing_points, str):
        try:
            missing_points = json.loads(missing_points)
        except:
            missing_points = [missing_points]
    
    for point in missing_points:
        point_lower = point.lower() if isinstance(point, str) else ""
        
        for kw in STRUCTURE_KEYWORDS["introduction"] + STRUCTURE_KEYWORDS["conclusion"]:
            if kw in point_lower:
                issues["structure"].append(point)
                break
        else:
            for kw in STRUCTURE_KEYWORDS["application"]:
                if kw in point_lower:
                    issues["application"].append(point)
                    break
            else:
                for kw in STRUCTURE_KEYWORDS["case_citation"]:
                    if kw in point_lower:
                        issues["case"].append(point)
                        break
                else:
                    issues["concept"].append(point)
    
    improvements = rubric_breakdown.get("improvements", [])
    if isinstance(improvements, str):
        try:
            improvements = json.loads(improvements)
        except:
            improvements = [improvements]
    
    for imp in improvements:
        imp_lower = imp.lower() if isinstance(imp, str) else ""
        
        if any(kw in imp_lower for kw in ["structure", "organize", "format"]):
            issues["structure"].append(imp)
        elif any(kw in imp_lower for kw in ["apply", "fact", "scenario"]):
            issues["application"].append(imp)
        elif any(kw in imp_lower for kw in ["case", "cite", "precedent"]):
            issues["case"].append(imp)
        else:
            issues["other"].append(imp)
    
    return issues


def detect_conceptual_weakness(
    attempts_data: List[Dict],
    topic_scores: Dict[str, List[float]]
) -> List[MistakePattern]:
    """
    Detect repeated low scores in the same topic_tag.
    
    Pattern triggers when:
    - Average score for topic < 50%
    - At least 2 attempts in topic
    - Same concept misunderstood across attempts
    """
    patterns = []
    
    for topic_tag, scores in topic_scores.items():
        if len(scores) < MIN_ATTEMPTS_FOR_PATTERN:
            continue
        
        avg_score = sum(scores) / len(scores)
        
        if avg_score < 50:
            topic_attempts = [a for a in attempts_data if topic_tag in a.get("tags", [])]
            
            evidence = []
            feedback_themes = defaultdict(int)
            
            for attempt in topic_attempts[:5]:
                evidence.append({
                    "attempt_id": attempt["id"],
                    "score": attempt.get("score"),
                    "date": attempt.get("attempted_at"),
                })
                
                rubric = attempt.get("rubric_breakdown", {})
                if rubric:
                    issues = extract_rubric_issues(rubric)
                    for issue_type, issue_list in issues.items():
                        for issue in issue_list:
                            feedback_themes[issue] += 1
            
            repeated_issues = [issue for issue, count in feedback_themes.items() if count >= 2]
            
            is_recurring = len(repeated_issues) > 0
            severity = calculate_severity(avg_score, len(scores), is_recurring)
            
            explanation = f"You scored an average of {avg_score:.1f}% across {len(scores)} attempts on '{topic_tag.replace('-', ' ').title()}'."
            if repeated_issues:
                explanation += f" Repeated issues: {', '.join(repeated_issues[:3])}."
            
            patterns.append(MistakePattern(
                pattern_type=PatternType.CONCEPTUAL_WEAKNESS,
                severity=severity,
                evidence=evidence,
                explanation=explanation,
                recommended_fix=[
                    f"Revise the fundamentals of {topic_tag.replace('-', ' ').title()}",
                    "Focus on understanding the core legal principles before attempting questions",
                    "Review model answers for this topic",
                ],
                topic_tags=[topic_tag],
                frequency=len(scores),
                first_detected=topic_attempts[-1].get("attempted_at") if topic_attempts else None,
                last_detected=topic_attempts[0].get("attempted_at") if topic_attempts else None,
            ))
    
    return patterns


def detect_structure_errors(
    attempts_data: List[Dict]
) -> List[MistakePattern]:
    """
    Detect poor introduction, missing conclusion, no issue framing.
    
    Pattern triggers when:
    - Rubric feedback mentions structure issues repeatedly
    - Missing key structural elements in multiple answers
    """
    structure_issues = defaultdict(list)
    
    for attempt in attempts_data:
        rubric = attempt.get("rubric_breakdown", {})
        if not rubric:
            continue
        
        issues = extract_rubric_issues(rubric)
        
        for issue in issues["structure"]:
            issue_lower = issue.lower()
            
            if any(kw in issue_lower for kw in STRUCTURE_KEYWORDS["introduction"]):
                structure_issues["introduction"].append({
                    "attempt_id": attempt["id"],
                    "feedback": issue,
                    "date": attempt.get("attempted_at"),
                })
            elif any(kw in issue_lower for kw in STRUCTURE_KEYWORDS["conclusion"]):
                structure_issues["conclusion"].append({
                    "attempt_id": attempt["id"],
                    "feedback": issue,
                    "date": attempt.get("attempted_at"),
                })
            elif any(kw in issue_lower for kw in STRUCTURE_KEYWORDS["issue_framing"]):
                structure_issues["issue_framing"].append({
                    "attempt_id": attempt["id"],
                    "feedback": issue,
                    "date": attempt.get("attempted_at"),
                })
    
    patterns = []
    
    for issue_type, occurrences in structure_issues.items():
        if len(occurrences) >= MIN_ATTEMPTS_FOR_PATTERN:
            severity = calculate_severity(
                score=50,
                frequency=len(occurrences),
                is_recurring=True
            )
            
            fix_map = {
                "introduction": [
                    "Always start with a clear problem statement",
                    "Define key terms in your opening paragraph",
                    "State what you will discuss in 1-2 sentences",
                ],
                "conclusion": [
                    "Reserve 2-3 minutes at the end to write conclusion",
                    "Summarize your main points in the final paragraph",
                    "Provide a definitive answer or opinion",
                ],
                "issue_framing": [
                    "Identify the legal issue explicitly before analyzing",
                    "Use phrases like 'The issue here is...'",
                    "Frame the question as a legal problem to solve",
                ],
            }
            
            patterns.append(MistakePattern(
                pattern_type=PatternType.STRUCTURE_ERROR,
                severity=severity,
                evidence=occurrences[:5],
                explanation=f"Your answers frequently lack proper {issue_type.replace('_', ' ')}. This was noted in {len(occurrences)} attempts.",
                recommended_fix=fix_map.get(issue_type, [
                    "Review answer writing structure guidelines",
                    "Practice outlining before writing",
                ]),
                frequency=len(occurrences),
                first_detected=occurrences[-1].get("date") if occurrences else None,
                last_detected=occurrences[0].get("date") if occurrences else None,
            ))
    
    return patterns


def detect_application_deficiency(
    attempts_data: List[Dict]
) -> List[MistakePattern]:
    """
    Detect theory present but application missing.
    
    Pattern triggers when:
    - Rubric shows good concept understanding but poor application
    - Facts not linked to law
    """
    application_issues = []
    
    for attempt in attempts_data:
        rubric = attempt.get("rubric_breakdown", {})
        if not rubric:
            continue
        
        issues = extract_rubric_issues(rubric)
        
        if issues["application"]:
            application_issues.append({
                "attempt_id": attempt["id"],
                "score": attempt.get("score"),
                "feedback": issues["application"][0] if issues["application"] else "",
                "date": attempt.get("attempted_at"),
                "tags": attempt.get("tags", []),
            })
        
        feedback = rubric.get("feedback_text", "") or ""
        feedback_lower = feedback.lower()
        
        application_phrases = [
            "apply to facts",
            "link to scenario",
            "factual application",
            "theoretical but",
            "lacks application",
            "not applied",
        ]
        
        if any(phrase in feedback_lower for phrase in application_phrases):
            if attempt["id"] not in [a["attempt_id"] for a in application_issues]:
                application_issues.append({
                    "attempt_id": attempt["id"],
                    "score": attempt.get("score"),
                    "feedback": feedback[:200],
                    "date": attempt.get("attempted_at"),
                    "tags": attempt.get("tags", []),
                })
    
    if len(application_issues) >= MIN_ATTEMPTS_FOR_PATTERN:
        avg_score = sum(a["score"] for a in application_issues if a["score"]) / len(application_issues) if application_issues else 50
        
        affected_topics = list(set(
            tag for a in application_issues for tag in a.get("tags", [])
        ))
        
        return [MistakePattern(
            pattern_type=PatternType.APPLICATION_DEFICIENCY,
            severity=calculate_severity(avg_score, len(application_issues), True),
            evidence=application_issues[:5],
            explanation=f"You understand legal concepts but struggle to apply them to facts. Detected in {len(application_issues)} answers.",
            recommended_fix=[
                "Use IRAC structure explicitly (Issue, Rule, Application, Conclusion)",
                "Practice fact-based problem questions",
                "After stating the law, explicitly connect it to the scenario",
                "Use phrases like 'Applying this to the present case...'",
            ],
            topic_tags=affected_topics[:5],
            frequency=len(application_issues),
            first_detected=application_issues[-1].get("date") if application_issues else None,
            last_detected=application_issues[0].get("date") if application_issues else None,
        )]
    
    return []


def detect_time_management_issues(
    attempts_data: List[Dict]
) -> List[MistakePattern]:
    """
    Detect time management problems.
    
    Pattern triggers when:
    - Very short answers for high-mark questions
    - Time taken < 30% of expected time
    - Repeated under-time submissions
    """
    time_issues = []
    
    for attempt in attempts_data:
        time_taken = attempt.get("time_taken_seconds")
        marks = attempt.get("marks", 5)
        answer_length = len(attempt.get("selected_option", "") or "")
        
        expected_time = marks * TIME_PER_MARK_SECONDS
        min_answer_length = marks * 50
        
        issue_reasons = []
        
        if time_taken and time_taken < expected_time * MINIMUM_TIME_RATIO:
            issue_reasons.append(f"Time taken ({time_taken}s) was very short for {marks} marks")
        
        if answer_length < min_answer_length and marks >= 5:
            issue_reasons.append(f"Answer length ({answer_length} chars) is short for {marks} marks")
        
        if issue_reasons:
            time_issues.append({
                "attempt_id": attempt["id"],
                "time_taken": time_taken,
                "marks": marks,
                "answer_length": answer_length,
                "reasons": issue_reasons,
                "date": attempt.get("attempted_at"),
            })
    
    if len(time_issues) >= MIN_ATTEMPTS_FOR_PATTERN:
        return [MistakePattern(
            pattern_type=PatternType.TIME_MANAGEMENT_ISSUE,
            severity=calculate_severity(50, len(time_issues), len(time_issues) >= 3),
            evidence=time_issues[:5],
            explanation=f"You may be rushing answers. {len(time_issues)} attempts showed signs of insufficient time allocation.",
            recommended_fix=[
                f"Allocate approximately {TIME_PER_MARK_SECONDS} seconds per mark",
                "Outline your answer before writing",
                "For essay questions, aim for 100-150 words per mark",
                "Practice timed writing to build stamina",
            ],
            frequency=len(time_issues),
            first_detected=time_issues[-1].get("date") if time_issues else None,
            last_detected=time_issues[0].get("date") if time_issues else None,
        )]
    
    return []


def detect_improvement_failure(
    attempts_data: List[Dict],
    question_attempts: Dict[int, List[Dict]]
) -> List[MistakePattern]:
    """
    Detect reattempts without meaningful improvement.
    
    Pattern triggers when:
    - Same question attempted multiple times
    - Score improvement < threshold
    - Same feedback repeated
    """
    improvement_failures = []
    
    for question_id, attempts in question_attempts.items():
        if len(attempts) < 2:
            continue
        
        attempts_sorted = sorted(attempts, key=lambda x: x.get("attempted_at", ""))
        
        first_score = attempts_sorted[0].get("score")
        last_score = attempts_sorted[-1].get("score")
        
        if first_score is None or last_score is None:
            continue
        
        improvement = last_score - first_score
        
        first_feedback = attempts_sorted[0].get("rubric_breakdown", {}).get("missing_points", [])
        last_feedback = attempts_sorted[-1].get("rubric_breakdown", {}).get("missing_points", [])
        
        if isinstance(first_feedback, str):
            first_feedback = [first_feedback]
        if isinstance(last_feedback, str):
            last_feedback = [last_feedback]
        
        repeated_issues = set(first_feedback) & set(last_feedback) if first_feedback and last_feedback else set()
        
        if improvement < IMPROVEMENT_THRESHOLD and len(attempts) >= 2:
            improvement_failures.append({
                "question_id": question_id,
                "attempts": len(attempts),
                "first_score": first_score,
                "last_score": last_score,
                "improvement": improvement,
                "repeated_issues": list(repeated_issues)[:3],
                "attempt_ids": [a["id"] for a in attempts_sorted],
            })
    
    if improvement_failures:
        return [MistakePattern(
            pattern_type=PatternType.IMPROVEMENT_FAILURE,
            severity=Severity.HIGH if len(improvement_failures) >= 2 else Severity.MEDIUM,
            evidence=improvement_failures[:5],
            explanation=f"You reattempted {len(improvement_failures)} questions without meaningful improvement (< {IMPROVEMENT_THRESHOLD}% gain).",
            recommended_fix=[
                "Review the feedback carefully before reattempting",
                "Identify specific areas mentioned for improvement",
                "Study the topic again before retrying",
                "Compare your answer with model answers",
            ],
            frequency=len(improvement_failures),
        )]
    
    return []


def detect_case_integration_gap(
    attempts_data: List[Dict]
) -> List[MistakePattern]:
    """
    Detect missing case citations and precedent integration.
    
    Pattern triggers when:
    - Rubric mentions missing cases repeatedly
    - Essays/case analysis lack case references
    """
    case_issues = []
    
    for attempt in attempts_data:
        question_type = attempt.get("question_type")
        if question_type not in ["essay", "case_analysis"]:
            continue
        
        rubric = attempt.get("rubric_breakdown", {})
        issues = extract_rubric_issues(rubric)
        
        if issues["case"]:
            case_issues.append({
                "attempt_id": attempt["id"],
                "feedback": issues["case"][0],
                "date": attempt.get("attempted_at"),
                "score": attempt.get("score"),
            })
    
    if len(case_issues) >= MIN_ATTEMPTS_FOR_PATTERN:
        return [MistakePattern(
            pattern_type=PatternType.CASE_INTEGRATION_GAP,
            severity=calculate_severity(50, len(case_issues), True),
            evidence=case_issues[:5],
            explanation=f"Your essay and case analysis answers often lack proper case citations. Noted in {len(case_issues)} attempts.",
            recommended_fix=[
                "Memorize 2-3 key cases per topic",
                "Practice integrating case names and ratios into answers",
                "Use format: 'In [Case Name] (Year), the court held that...'",
                "Link case principles to the question's facts",
            ],
            frequency=len(case_issues),
            first_detected=case_issues[-1].get("date") if case_issues else None,
            last_detected=case_issues[0].get("date") if case_issues else None,
        )]
    
    return []


async def fetch_user_attempts_data(
    user_id: int,
    db: AsyncSession,
    limit: int = 100
) -> Tuple[List[Dict], Dict[str, List[float]], Dict[int, List[Dict]]]:
    """
    Fetch and process user's practice attempts with evaluations.
    
    Returns:
        - attempts_data: List of attempt dictionaries with evaluation data
        - topic_scores: Dict mapping topic_tag to list of scores
        - question_attempts: Dict mapping question_id to list of attempts
    """
    stmt = (
        select(PracticeAttempt, PracticeEvaluation, PracticeQuestion)
        .outerjoin(PracticeEvaluation, PracticeEvaluation.practice_attempt_id == PracticeAttempt.id)
        .join(PracticeQuestion, PracticeQuestion.id == PracticeAttempt.practice_question_id)
        .where(PracticeAttempt.user_id == user_id)
        .order_by(desc(PracticeAttempt.attempted_at))
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    rows = result.fetchall()
    
    attempts_data = []
    topic_scores = defaultdict(list)
    question_attempts = defaultdict(list)
    
    for attempt, evaluation, question in rows:
        tags = question.tags.split(",") if question.tags else []
        tags = [t.strip() for t in tags if t.strip()]
        
        rubric_breakdown = {}
        score = None
        
        if evaluation:
            score = evaluation.score
            rubric_breakdown = evaluation.rubric_breakdown or {}
            if isinstance(rubric_breakdown, str):
                try:
                    rubric_breakdown = json.loads(rubric_breakdown)
                except:
                    rubric_breakdown = {}
        
        attempt_data = {
            "id": attempt.id,
            "question_id": question.id,
            "question_type": question.question_type.value if question.question_type else None,
            "marks": question.marks,
            "tags": tags,
            "selected_option": attempt.selected_option,
            "is_correct": attempt.is_correct,
            "attempt_number": attempt.attempt_number,
            "time_taken_seconds": attempt.time_taken_seconds,
            "attempted_at": attempt.attempted_at.isoformat() if attempt.attempted_at else None,
            "score": score,
            "rubric_breakdown": rubric_breakdown,
            "feedback_text": evaluation.feedback_text if evaluation else None,
            "strengths": evaluation.strengths if evaluation else [],
            "improvements": evaluation.improvements if evaluation else [],
        }
        
        attempts_data.append(attempt_data)
        
        if score is not None:
            for tag in tags:
                topic_scores[tag].append(score)
        
        question_attempts[question.id].append(attempt_data)
    
    return attempts_data, dict(topic_scores), dict(question_attempts)


def generate_summary(
    patterns: List[MistakePattern],
    attempts_data: List[Dict],
    topic_scores: Dict[str, List[float]]
) -> Dict[str, Any]:
    """Generate summary statistics from patterns and data."""
    
    pattern_counts = defaultdict(int)
    severity_counts = defaultdict(int)
    
    for pattern in patterns:
        pattern_counts[pattern.pattern_type.value] += 1
        severity_counts[pattern.severity.value] += 1
    
    total_score = 0
    scored_count = 0
    for attempt in attempts_data:
        if attempt.get("score") is not None:
            total_score += attempt["score"]
            scored_count += 1
    
    avg_score = total_score / scored_count if scored_count > 0 else None
    
    weak_topics = [
        tag for tag, scores in topic_scores.items()
        if len(scores) >= 2 and sum(scores) / len(scores) < 50
    ]
    
    strong_topics = [
        tag for tag, scores in topic_scores.items()
        if len(scores) >= 2 and sum(scores) / len(scores) >= 70
    ]
    
    return {
        "total_patterns_detected": len(patterns),
        "pattern_distribution": dict(pattern_counts),
        "severity_distribution": dict(severity_counts),
        "average_score": round(avg_score, 2) if avg_score else None,
        "weak_topics": weak_topics,
        "strong_topics": strong_topics,
        "total_topics_analyzed": len(topic_scores),
        "critical_issues": severity_counts.get("critical", 0) + severity_counts.get("high", 0),
    }


def generate_recommendations(
    patterns: List[MistakePattern],
    summary: Dict[str, Any]
) -> List[str]:
    """Generate prioritized recommendations based on detected patterns."""
    
    recommendations = []
    
    critical_patterns = [p for p in patterns if p.severity in [Severity.CRITICAL, Severity.HIGH]]
    critical_patterns.sort(key=lambda p: (
        0 if p.severity == Severity.CRITICAL else 1,
        -p.frequency
    ))
    
    for pattern in critical_patterns[:3]:
        if pattern.recommended_fix:
            recommendations.append(pattern.recommended_fix[0])
    
    if summary.get("weak_topics"):
        weak_topic = summary["weak_topics"][0]
        recommendations.append(f"Priority: Revise '{weak_topic.replace('-', ' ').title()}' - marked as weak topic")
    
    if summary.get("average_score") and summary["average_score"] < 50:
        recommendations.append("Focus on fundamentals before attempting advanced questions")
    
    pattern_types = set(p.pattern_type for p in patterns)
    
    if PatternType.STRUCTURE_ERROR in pattern_types and PatternType.APPLICATION_DEFICIENCY in pattern_types:
        recommendations.append("Practice IRAC method for both structure and application improvement")
    
    if PatternType.TIME_MANAGEMENT_ISSUE in pattern_types:
        recommendations.append("Schedule timed practice sessions to improve time management")
    
    if PatternType.IMPROVEMENT_FAILURE in pattern_types:
        recommendations.append("Before reattempting, review feedback and study the specific gaps identified")
    
    return list(dict.fromkeys(recommendations))[:7]


def generate_topic_breakdown(
    topic_scores: Dict[str, List[float]],
    attempts_data: List[Dict]
) -> Dict[str, Dict[str, Any]]:
    """Generate detailed breakdown by topic."""
    
    breakdown = {}
    
    for topic_tag, scores in topic_scores.items():
        if not scores:
            continue
        
        avg_score = sum(scores) / len(scores)
        
        if avg_score < SCORE_THRESHOLD_LOW:
            status = "weak"
        elif avg_score < SCORE_THRESHOLD_MEDIUM:
            status = "average"
        elif avg_score < SCORE_THRESHOLD_PASS:
            status = "good"
        else:
            status = "strong"
        
        topic_attempts = [a for a in attempts_data if topic_tag in a.get("tags", [])]
        recent_trend = "stable"
        
        if len(topic_attempts) >= 3:
            recent_scores = [a.get("score") for a in topic_attempts[:3] if a.get("score") is not None]
            older_scores = [a.get("score") for a in topic_attempts[3:6] if a.get("score") is not None]
            
            if recent_scores and older_scores:
                recent_avg = sum(recent_scores) / len(recent_scores)
                older_avg = sum(older_scores) / len(older_scores)
                
                if recent_avg > older_avg + 10:
                    recent_trend = "improving"
                elif recent_avg < older_avg - 10:
                    recent_trend = "declining"
        
        breakdown[topic_tag] = {
            "average_score": round(avg_score, 2),
            "attempt_count": len(scores),
            "status": status,
            "trend": recent_trend,
            "display_name": topic_tag.replace("-", " ").replace("_", " ").title(),
        }
    
    return breakdown


async def run_diagnostic_analysis(
    user_id: int,
    db: AsyncSession,
    limit: int = 100
) -> DiagnosticReport:
    """
    Run complete diagnostic analysis for a user.
    
    This is the main entry point for pattern detection.
    
    Flow:
    1. Fetch all user attempts with evaluations
    2. Run each pattern detector
    3. Aggregate results
    4. Generate recommendations
    
    Returns:
        DiagnosticReport with all patterns and insights
    """
    logger.info(f"Running diagnostic analysis for user_id={user_id}")
    
    attempts_data, topic_scores, question_attempts = await fetch_user_attempts_data(
        user_id, db, limit
    )
    
    if not attempts_data:
        return DiagnosticReport(
            user_id=user_id,
            generated_at=datetime.utcnow().isoformat(),
            total_attempts_analyzed=0,
            patterns=[],
            summary={
                "total_patterns_detected": 0,
                "message": "No practice attempts found. Start practicing to receive diagnostic insights."
            },
            topic_breakdown={},
            recommendations=["Start practicing to receive personalized recommendations"],
        )
    
    patterns = []
    
    patterns.extend(detect_conceptual_weakness(attempts_data, topic_scores))
    patterns.extend(detect_structure_errors(attempts_data))
    patterns.extend(detect_application_deficiency(attempts_data))
    patterns.extend(detect_time_management_issues(attempts_data))
    patterns.extend(detect_improvement_failure(attempts_data, question_attempts))
    patterns.extend(detect_case_integration_gap(attempts_data))
    
    patterns.sort(key=lambda p: (
        {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(p.severity.value, 4),
        -p.frequency
    ))
    
    summary = generate_summary(patterns, attempts_data, topic_scores)
    topic_breakdown = generate_topic_breakdown(topic_scores, attempts_data)
    recommendations = generate_recommendations(patterns, summary)
    
    logger.info(f"Diagnostic complete: {len(patterns)} patterns detected for user_id={user_id}")
    
    return DiagnosticReport(
        user_id=user_id,
        generated_at=datetime.utcnow().isoformat(),
        total_attempts_analyzed=len(attempts_data),
        patterns=patterns,
        summary=summary,
        topic_breakdown=topic_breakdown,
        recommendations=recommendations,
    )


async def get_patterns_for_topic(
    user_id: int,
    topic_tag: str,
    db: AsyncSession
) -> List[MistakePattern]:
    """Get patterns specific to a topic (for AI Tutor integration)."""
    
    report = await run_diagnostic_analysis(user_id, db, limit=50)
    
    return [
        p for p in report.patterns
        if topic_tag in p.topic_tags or not p.topic_tags
    ]


async def get_quick_diagnosis(
    user_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Quick diagnosis for dashboard display.
    Returns summary without full pattern details.
    """
    report = await run_diagnostic_analysis(user_id, db, limit=30)
    
    return {
        "user_id": user_id,
        "generated_at": report.generated_at,
        "critical_patterns": len([p for p in report.patterns if p.severity in [Severity.CRITICAL, Severity.HIGH]]),
        "weak_topics": report.summary.get("weak_topics", [])[:3],
        "top_recommendation": report.recommendations[0] if report.recommendations else None,
        "average_score": report.summary.get("average_score"),
        "pattern_types": list(set(p.pattern_type.value for p in report.patterns)),
    }
