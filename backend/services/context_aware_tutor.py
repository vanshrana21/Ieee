"""
backend/services/context_aware_tutor.py
Phase 6.1: Context-Aware AI Tutor for Indian Law Students

SYSTEM BEHAVIOR:
- Behaves like a disciplined law professor, NOT a chatbot
- Knows WHAT the student has studied
- Knows WHAT the student is weak at
- Knows WHAT syllabus the student belongs to
- Refuses out-of-syllabus queries
- Guides, not spoon-feeds

NO HARDCODED CONTENT - Everything is database-driven
DETERMINISTIC BEHAVIOR - Same inputs = Same outputs
"""

import os
import re
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from enum import Enum
import google.generativeai as genai
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from sqlalchemy.orm import joinedload

from backend.orm.user import User
from backend.orm.course import Course
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum
from backend.orm.content_module import ContentModule
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.topic_mastery import TopicMastery
from backend.orm.subject_progress import SubjectProgress
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_question import PracticeQuestion
from backend.orm.practice_evaluation import PracticeEvaluation
from backend.services.mistake_pattern_service import (
    get_patterns_for_topic,
    get_quick_diagnosis,
    PatternType,
    Severity,
    MistakePattern,
)

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    tutor_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    logger.error("GEMINI_API_KEY not found")
    tutor_model = None


class QueryIntent(str, Enum):
    EXPLAIN_CONCEPT = "explain_concept"
    CLARIFY_DOUBT = "clarify_doubt"
    WRITING_GUIDANCE = "writing_guidance"
    REVISION_HELP = "revision_help"
    GENERAL_QUESTION = "general_question"
    OUT_OF_SCOPE = "out_of_scope"


class MasteryLevel(str, Enum):
    WEAK = "weak"
    AVERAGE = "average"
    STRONG = "strong"
    UNKNOWN = "unknown"


WEAK_THRESHOLD = 50.0
STRONG_THRESHOLD = 75.0

INTENT_PATTERNS = {
    QueryIntent.EXPLAIN_CONCEPT: [
        r"explain\s+",
        r"what\s+is\s+",
        r"what\s+are\s+",
        r"define\s+",
        r"meaning\s+of\s+",
        r"tell\s+me\s+about\s+",
        r"concept\s+of\s+",
    ],
    QueryIntent.CLARIFY_DOUBT: [
        r"difference\s+between\s+",
        r"distinguish\s+",
        r"compare\s+",
        r"vs\s+",
        r"versus\s+",
        r"how\s+is\s+.+\s+different\s+",
        r"why\s+is\s+",
        r"clarify\s+",
    ],
    QueryIntent.WRITING_GUIDANCE: [
        r"how\s+to\s+write\s+",
        r"how\s+to\s+answer\s+",
        r"structure\s+of\s+",
        r"format\s+for\s+",
        r"approach\s+to\s+",
        r"tips\s+for\s+writing\s+",
        r"\d+\s*mark\s*answer",
        r"\d+\s*marks?\s*question",
    ],
    QueryIntent.REVISION_HELP: [
        r"revise\s+",
        r"revision\s+",
        r"summary\s+of\s+",
        r"quick\s+review\s+",
        r"key\s+points\s+",
        r"important\s+points\s+",
        r"recap\s+",
    ],
}

RESPONSE_TEMPLATES = {
    QueryIntent.EXPLAIN_CONCEPT: {
        MasteryLevel.WEAK: """
{definition}

**Foundational Points:**
{key_points}

**Relevant Cases (If Studied):**
{cases}

**Exam Tips:**
{exam_tips}

> You may want to revise the fundamentals of {topic} before attempting questions on this topic.
""",
        MasteryLevel.AVERAGE: """
{definition}

**Key Points:**
{key_points}

**Relevant Cases:**
{cases}

**Exam Tips:**
{exam_tips}

> Consider practicing more questions on {topic} to strengthen your understanding.
""",
        MasteryLevel.STRONG: """
{definition}

**Key Points:**
{key_points}

**Application Focus:**
{application}

**Exam Tips:**
{exam_tips}
""",
    },
    QueryIntent.CLARIFY_DOUBT: """
**Comparison:**

| Aspect | {term1} | {term2} |
|--------|---------|---------|
{comparison_rows}

**Exam Framing Tip:**
{exam_tip}
""",
    QueryIntent.WRITING_GUIDANCE: """
**Answer Structure for {marks} Marks:**

**Introduction Strategy:**
{introduction}

**Main Headings:**
{headings}

**Case Placement:**
{case_placement}

**Conclusion Style:**
{conclusion}

> Note: This is a structural guide only. Full answers must be written in your own words.
""",
}

REFUSAL_RESPONSES = {
    "out_of_syllabus": "This topic ({topic}) is not part of your current syllabus ({course}, Semester {semester}). Please focus on topics within your curriculum.",
    "insufficient_data": "Based on available data, here is a general explanation. For more specific guidance, practice some questions on this topic first.",
    "no_attempts": "You haven't attempted any practice questions yet. Start practicing to get personalized feedback and improvement suggestions.",
    "legal_advice": "This appears to be a request for legal advice. As an educational tutor, I can only explain legal concepts, not advise on specific situations.",
    "political": "I cannot comment on political matters. Let me help you with the legal/constitutional principles instead.",
}


class StudentContext:
    """Assembled student context for tutor decision-making."""
    
    def __init__(
        self,
        user_id: int,
        course_name: str,
        semester: int,
        allowed_subjects: List[Dict[str, Any]],
        topic_mastery: Dict[str, Dict[str, Any]],
        weak_topics: List[str],
        strong_topics: List[str],
        recent_mistakes: List[Dict[str, Any]],
        total_attempts: int,
        study_priorities: List[Dict[str, Any]],
        diagnostic_patterns: List[Dict[str, Any]] = None
    ):
        self.user_id = user_id
        self.course_name = course_name
        self.semester = semester
        self.allowed_subjects = allowed_subjects
        self.topic_mastery = topic_mastery
        self.weak_topics = weak_topics
        self.strong_topics = strong_topics
        self.recent_mistakes = recent_mistakes
        self.total_attempts = total_attempts
        self.study_priorities = study_priorities
        self.diagnostic_patterns = diagnostic_patterns or []
    
    def get_mastery_level(self, topic_tag: str) -> MasteryLevel:
        """Get mastery level for a topic."""
        if topic_tag in self.topic_mastery:
            score = self.topic_mastery[topic_tag].get("score", 50)
            if score < WEAK_THRESHOLD:
                return MasteryLevel.WEAK
            elif score >= STRONG_THRESHOLD:
                return MasteryLevel.STRONG
            else:
                return MasteryLevel.AVERAGE
        return MasteryLevel.UNKNOWN
    
    def is_topic_in_syllabus(self, topic_tag: str) -> bool:
        """Check if topic is in student's syllabus."""
        topic_lower = topic_tag.lower().replace("-", " ").replace("_", " ")
        
        for subject in self.allowed_subjects:
            if topic_lower in subject.get("title", "").lower():
                return True
            for module in subject.get("modules", []):
                if topic_lower in module.lower():
                    return True
        
        if topic_tag in self.topic_mastery:
            return True
        
        return False
    
    def to_prompt_context(self) -> str:
        """Convert context to prompt-friendly format."""
        lines = [
            f"Course: {self.course_name}",
            f"Semester: {self.semester}",
            f"Total Practice Attempts: {self.total_attempts}",
            "",
            "Allowed Subjects:",
        ]
        
        for subject in self.allowed_subjects:
            lines.append(f"- {subject['title']}")
        
        if self.weak_topics:
            lines.append("")
            lines.append("Weak Topics (needs focus):")
            for topic in self.weak_topics[:5]:
                lines.append(f"- {topic}")
        
        if self.strong_topics:
            lines.append("")
            lines.append("Strong Topics:")
            for topic in self.strong_topics[:5]:
                lines.append(f"- {topic}")
        
        if self.recent_mistakes:
            lines.append("")
            lines.append("Recent Mistakes:")
            for mistake in self.recent_mistakes[:3]:
                lines.append(f"- {mistake.get('topic', 'Unknown')}: {mistake.get('feedback', '')[:100]}")
        
        if self.diagnostic_patterns:
            lines.append("")
            lines.append("Detected Learning Patterns (from diagnostic analysis):")
            for pattern in self.diagnostic_patterns[:3]:
                pattern_type = pattern.get("pattern_type", "").replace("_", " ").title()
                severity = pattern.get("severity", "")
                lines.append(f"- [{severity.upper()}] {pattern_type}: {pattern.get('explanation', '')[:150]}")
        
        return "\n".join(lines)


async def assemble_student_context(user_id: int, db: AsyncSession) -> StudentContext:
    """
    Assemble complete student context from database.
    NO AI calls - pure data assembly.
    """
    logger.info(f"Assembling student context: user_id={user_id}")
    
    user_stmt = (
        select(User)
        .options(joinedload(User.course))
        .where(User.id == user_id)
    )
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()
    
    if not user:
        return StudentContext(
            user_id=user_id,
            course_name="Unknown",
            semester=1,
            allowed_subjects=[],
            topic_mastery={},
            weak_topics=[],
            strong_topics=[],
            recent_mistakes=[],
            total_attempts=0,
            study_priorities=[]
        )
    
    course_name = user.course.name if user.course else "Not Enrolled"
    semester = user.current_semester or 1
    
    allowed_subjects = []
    if user.course_id:
        subjects_stmt = (
            select(Subject, CourseCurriculum.semester_number)
            .join(CourseCurriculum, CourseCurriculum.subject_id == Subject.id)
            .where(
                CourseCurriculum.course_id == user.course_id,
                CourseCurriculum.semester_number <= semester,
                CourseCurriculum.is_active == True
            )
            .order_by(CourseCurriculum.semester_number)
        )
        subjects_result = await db.execute(subjects_stmt)
        
        for subject, sem_num in subjects_result.fetchall():
            modules_stmt = select(ContentModule.title).where(
                ContentModule.subject_id == subject.id
            )
            modules_result = await db.execute(modules_stmt)
            module_titles = [r[0] for r in modules_result.fetchall()]
            
            allowed_subjects.append({
                "id": subject.id,
                "title": subject.title,
                "semester": sem_num,
                "modules": module_titles
            })
    
    mastery_stmt = select(TopicMastery).where(TopicMastery.user_id == user_id)
    mastery_result = await db.execute(mastery_stmt)
    masteries = mastery_result.scalars().all()
    
    topic_mastery = {}
    weak_topics = []
    strong_topics = []
    
    for m in masteries:
        score = m.mastery_score if m.mastery_score else 0
        topic_mastery[m.topic_tag] = {
            "score": score,
            "subject_id": m.subject_id,
            "last_practiced": m.last_practiced_at.isoformat() if m.last_practiced_at else None
        }
        
        if score < WEAK_THRESHOLD:
            weak_topics.append(m.topic_tag)
        elif score >= STRONG_THRESHOLD:
            strong_topics.append(m.topic_tag)
    
    recent_mistakes = []
    mistakes_stmt = (
        select(PracticeAttempt, PracticeEvaluation)
        .outerjoin(PracticeEvaluation, PracticeEvaluation.practice_attempt_id == PracticeAttempt.id)
        .where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.is_correct == False
        )
        .order_by(desc(PracticeAttempt.attempted_at))
        .limit(5)
    )
    mistakes_result = await db.execute(mistakes_stmt)
    
    for attempt, evaluation in mistakes_result.fetchall():
        mistake_data = {
            "question_id": attempt.practice_question_id,
            "attempted_at": attempt.attempted_at.isoformat() if attempt.attempted_at else None
        }
        
        if evaluation and evaluation.rubric_breakdown:
            rubric = evaluation.rubric_breakdown
            if isinstance(rubric, str):
                try:
                    rubric = json.loads(rubric)
                except:
                    rubric = {}
            
            mistake_data["feedback"] = rubric.get("overall_feedback", "")
            mistake_data["topic"] = rubric.get("topic", "Unknown")
            missing = rubric.get("missing_points", [])
            if missing:
                mistake_data["missing_points"] = missing[:3]
        
        recent_mistakes.append(mistake_data)
    
    count_stmt = select(func.count(PracticeAttempt.id)).where(
        PracticeAttempt.user_id == user_id
    )
    count_result = await db.execute(count_stmt)
    total_attempts = count_result.scalar() or 0
    
    study_priorities = []
    for subject in allowed_subjects:
        progress_stmt = select(SubjectProgress).where(
            SubjectProgress.user_id == user_id,
            SubjectProgress.subject_id == subject["id"]
        )
        progress_result = await db.execute(progress_stmt)
        progress = progress_result.scalar_one_or_none()
        
        if progress:
            completion = progress.completion_percentage or 0
            if completion < 30:
                priority = "High"
            elif completion < 70:
                priority = "Medium"
            else:
                priority = "Low"
            
            study_priorities.append({
                "subject_id": subject["id"],
                "subject_title": subject["title"],
                "completion": completion,
                "priority": priority
            })
    
    study_priorities.sort(key=lambda x: {"High": 0, "Medium": 1, "Low": 2}.get(x["priority"], 3))
    
    diagnostic_patterns = []
    try:
        quick_diag = await get_quick_diagnosis(user_id, db)
        if quick_diag and quick_diag.get("pattern_types"):
            for pt in quick_diag.get("pattern_types", [])[:3]:
                diagnostic_patterns.append({
                    "pattern_type": pt,
                    "severity": "high" if quick_diag.get("critical_patterns", 0) > 0 else "medium",
                    "explanation": quick_diag.get("top_recommendation", ""),
                })
    except Exception as e:
        logger.warning(f"Failed to fetch diagnostic patterns: {e}")
    
    return StudentContext(
        user_id=user_id,
        course_name=course_name,
        semester=semester,
        allowed_subjects=allowed_subjects,
        topic_mastery=topic_mastery,
        weak_topics=weak_topics,
        strong_topics=strong_topics,
        recent_mistakes=recent_mistakes,
        total_attempts=total_attempts,
        study_priorities=study_priorities[:5],
        diagnostic_patterns=diagnostic_patterns
    )


def detect_query_intent(query: str) -> QueryIntent:
    """
    Detect the intent of student's query.
    Rule-based, no AI.
    """
    query_lower = query.lower().strip()
    
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, query_lower):
                return intent
    
    return QueryIntent.GENERAL_QUESTION


def extract_topic_from_query(query: str) -> Optional[str]:
    """Extract the main topic from the query."""
    query_clean = re.sub(r'^(explain|what is|define|tell me about|describe)\s+', '', query.lower())
    query_clean = re.sub(r'\?$', '', query_clean).strip()
    
    article_match = re.search(r'article\s*(\d+[a-z]?)', query_clean, re.IGNORECASE)
    if article_match:
        return f"article-{article_match.group(1)}"
    
    section_match = re.search(r'section\s*(\d+)', query_clean, re.IGNORECASE)
    if section_match:
        return f"section-{section_match.group(1)}"
    
    query_clean = re.sub(r'\b(the|a|an|of|in|for|to|and|or)\b', '', query_clean)
    words = [w.strip() for w in query_clean.split() if len(w.strip()) > 2]
    
    if words:
        return "-".join(words[:4])
    
    return None


def validate_query_against_syllabus(
    query: str,
    topic: Optional[str],
    context: StudentContext
) -> Tuple[bool, Optional[str]]:
    """
    Validate if query is within student's syllabus.
    
    Returns:
        (is_valid, refusal_message)
    """
    query_lower = query.lower()
    
    legal_advice_patterns = [
        r"should\s+i\s+(file|sue|hire)",
        r"can\s+i\s+(sue|file\s+case)",
        r"my\s+(case|situation|problem)",
        r"advise\s+me",
        r"help\s+me\s+(with\s+my|file)",
    ]
    
    for pattern in legal_advice_patterns:
        if re.search(pattern, query_lower):
            return False, REFUSAL_RESPONSES["legal_advice"]
    
    political_keywords = ["modi", "bjp", "congress", "rahul gandhi", "government is wrong", "ruling party"]
    for keyword in political_keywords:
        if keyword in query_lower:
            return False, REFUSAL_RESPONSES["political"]
    
    core_law_topics = [
        "constitution", "article", "fundamental right", "directive principle",
        "ipc", "crpc", "evidence act", "contract", "tort", "property",
        "jurisprudence", "basic structure", "judicial review", "writ"
    ]
    
    for core_topic in core_law_topics:
        if core_topic in query_lower:
            if context.allowed_subjects:
                return True, None
    
    if topic:
        if context.is_topic_in_syllabus(topic):
            return True, None
    
    for subject in context.allowed_subjects:
        if subject["title"].lower() in query_lower:
            return True, None
        for module in subject.get("modules", []):
            if module.lower() in query_lower:
                return True, None
    
    if not topic and not context.allowed_subjects:
        return True, None
    
    if topic and not context.is_topic_in_syllabus(topic):
        return False, REFUSAL_RESPONSES["out_of_syllabus"].format(
            topic=topic,
            course=context.course_name,
            semester=context.semester
        )
    
    return True, None


def build_tutor_system_prompt(context: StudentContext, intent: QueryIntent) -> str:
    """Build the system prompt for the AI tutor."""
    
    system_prompt = f"""You are an AI law professor for Indian law students. You are NOT a chatbot.

STUDENT CONTEXT:
{context.to_prompt_context()}

YOUR BEHAVIOR RULES:
1. Exam-oriented responses only
2. Structured answers (headings, bullet points)
3. No conversational fluff or emojis
4. No AI self-reference ("As an AI...", "I think...")
5. Guide, do not spoon-feed
6. No full model answers - provide structure and key points only
7. Use Indian law only - no foreign jurisdiction examples unless directly relevant

TONE:
- Academic and neutral
- Direct and concise
- Focus on exam requirements
- Cite cases by name and year only if student has studied them

RESPONSE FORMAT:
- Use markdown formatting
- Headings for sections
- Bullet points for lists
- Bold for key terms
- Tables for comparisons

PROHIBITED:
- Legal advice
- Political commentary
- Speculative language ("I think", "probably", "maybe")
- Full paragraph answers to exam questions
- Emojis or casual language

"""
    
    if intent == QueryIntent.WRITING_GUIDANCE:
        system_prompt += """
SPECIAL INSTRUCTION FOR WRITING GUIDANCE:
Provide ONLY:
- Introduction strategy (1-2 sentences)
- Main headings to cover
- Where to place cases
- Conclusion approach

Do NOT provide:
- Full paragraphs
- Complete answers
- Sample text to copy
"""
    
    if context.weak_topics:
        system_prompt += f"""
NOTE: Student is weak in: {', '.join(context.weak_topics[:3])}
If query relates to these topics, add a revision suggestion at the end.
"""
    
    if context.total_attempts == 0:
        system_prompt += """
NOTE: Student has no practice attempts yet.
Encourage them to start practicing after your explanation.
"""
    
    return system_prompt


def build_user_prompt(
    query: str,
    intent: QueryIntent,
    topic: Optional[str],
    context: StudentContext
) -> str:
    """Build the user prompt with context injection."""
    
    mastery_info = ""
    if topic:
        mastery_level = context.get_mastery_level(topic)
        if mastery_level != MasteryLevel.UNKNOWN:
            mastery_info = f"\n[Student mastery on this topic: {mastery_level.value}]"
    
    prompt = f"""Student Query: {query}
{mastery_info}
Intent Detected: {intent.value}

Respond according to the system instructions."""
    
    return prompt


async def search_relevant_content(
    query: str,
    topic: Optional[str],
    context: StudentContext,
    db: AsyncSession
) -> Dict[str, List[Dict]]:
    """Search for relevant database content to inject into prompt."""
    
    result = {
        "learn_content": [],
        "cases": []
    }
    
    keywords = query.lower().split()
    keywords = [k for k in keywords if len(k) > 3]
    
    if not keywords and topic:
        keywords = topic.replace("-", " ").replace("_", " ").split()
    
    if not keywords:
        return result
    
    subject_ids = [s["id"] for s in context.allowed_subjects]
    
    if subject_ids:
        learn_conditions = []
        for kw in keywords[:5]:
            learn_conditions.append(LearnContent.title.ilike(f"%{kw}%"))
        
        if learn_conditions:
            learn_stmt = (
                select(LearnContent)
                .join(ContentModule, LearnContent.module_id == ContentModule.id)
                .where(
                    ContentModule.subject_id.in_(subject_ids),
                    *learn_conditions[:1]
                )
                .limit(3)
            )
            
            learn_result = await db.execute(learn_stmt)
            for item in learn_result.scalars().all():
                result["learn_content"].append({
                    "id": item.id,
                    "title": item.title,
                    "summary": item.summary[:200] if item.summary else ""
                })
        
        case_conditions = []
        for kw in keywords[:5]:
            case_conditions.append(CaseContent.case_name.ilike(f"%{kw}%"))
        
        if case_conditions:
            case_stmt = (
                select(CaseContent)
                .join(ContentModule, CaseContent.module_id == ContentModule.id)
                .where(
                    ContentModule.subject_id.in_(subject_ids),
                    *case_conditions[:1]
                )
                .limit(3)
            )
            
            case_result = await db.execute(case_stmt)
            for case in case_result.scalars().all():
                result["cases"].append({
                    "id": case.id,
                    "case_name": case.case_name,
                    "year": case.year,
                    "ratio": case.ratio[:150] if case.ratio else ""
                })
    
    return result


async def generate_tutor_response(
    user_id: int,
    query: str,
    db: AsyncSession,
    session_history: Optional[List[Dict]] = None
) -> Dict[str, Any]:
    """
    Main entry point for tutor response generation.
    
    Flow:
    1. Assemble student context
    2. Detect query intent
    3. Extract topic
    4. Validate against syllabus
    5. Search relevant content
    6. Build prompts
    7. Call AI
    8. Format response
    
    Returns:
        {
            "response": str,
            "intent": str,
            "topic": str,
            "mastery_level": str,
            "suggestions": List[str],
            "related_content": List[Dict],
            "meta": Dict
        }
    """
    logger.info(f"Tutor request: user_id={user_id}, query='{query[:50]}...'")
    
    context = await assemble_student_context(user_id, db)
    
    intent = detect_query_intent(query)
    logger.info(f"Detected intent: {intent.value}")
    
    topic = extract_topic_from_query(query)
    logger.info(f"Extracted topic: {topic}")
    
    is_valid, refusal_message = validate_query_against_syllabus(query, topic, context)
    
    if not is_valid:
        logger.info(f"Query rejected: {refusal_message[:50]}...")
        return {
            "response": refusal_message,
            "intent": QueryIntent.OUT_OF_SCOPE.value,
            "topic": topic,
            "mastery_level": MasteryLevel.UNKNOWN.value,
            "suggestions": [],
            "related_content": [],
            "meta": {
                "rejected": True,
                "reason": "syllabus_validation_failed"
            }
        }
    
    if not tutor_model:
        return {
            "response": "AI service is currently unavailable. Please try again later.",
            "intent": intent.value,
            "topic": topic,
            "mastery_level": MasteryLevel.UNKNOWN.value,
            "suggestions": [],
            "related_content": [],
            "meta": {"error": "model_unavailable"}
        }
    
    relevant_content = await search_relevant_content(query, topic, context, db)
    
    system_prompt = build_tutor_system_prompt(context, intent)
    user_prompt = build_user_prompt(query, intent, topic, context)
    
    if relevant_content["learn_content"]:
        user_prompt += "\n\nRelevant Content from Student's Syllabus:\n"
        for item in relevant_content["learn_content"]:
            user_prompt += f"- {item['title']}: {item['summary']}\n"
    
    if relevant_content["cases"]:
        user_prompt += "\n\nRelevant Cases (Student has studied):\n"
        for case in relevant_content["cases"]:
            user_prompt += f"- {case['case_name']} ({case['year']}): {case['ratio']}\n"
    
    if session_history:
        history_text = "\n\nRecent Conversation:\n"
        for msg in session_history[-4:]:
            role = "Student" if msg.get("role") in ["user", "student"] else "Tutor"
            history_text += f"{role}: {msg.get('text', '')[:200]}\n"
        user_prompt = history_text + user_prompt
    
    try:
        response = await tutor_model.generate_content_async(
            [
                {"role": "user", "parts": [system_prompt + "\n\n" + user_prompt]}
            ],
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=1500,
            )
        )
        
        ai_response = response.text
        logger.info("AI response generated successfully")
        
    except Exception as e:
        logger.error(f"AI generation failed: {e}")
        return {
            "response": REFUSAL_RESPONSES["insufficient_data"],
            "intent": intent.value,
            "topic": topic,
            "mastery_level": MasteryLevel.UNKNOWN.value,
            "suggestions": [],
            "related_content": [],
            "meta": {"error": str(e)}
        }
    
    mastery_level = context.get_mastery_level(topic) if topic else MasteryLevel.UNKNOWN
    
    suggestions = []
    if mastery_level == MasteryLevel.WEAK and topic:
        suggestions.append(f"Revise fundamentals of {topic.replace('-', ' ')} before attempting questions")
    if context.total_attempts < 10:
        suggestions.append("Practice more questions to improve your understanding")
    if context.study_priorities:
        top_priority = context.study_priorities[0]
        if top_priority["priority"] == "High":
            suggestions.append(f"Focus on {top_priority['subject_title']} - marked high priority")
    
    related_content = []
    for item in relevant_content["learn_content"]:
        related_content.append({
            "type": "learn",
            "id": item["id"],
            "title": item["title"]
        })
    for case in relevant_content["cases"]:
        related_content.append({
            "type": "case",
            "id": case["id"],
            "title": case["case_name"]
        })
    
    return {
        "response": ai_response,
        "intent": intent.value,
        "topic": topic,
        "mastery_level": mastery_level.value,
        "suggestions": suggestions,
        "related_content": related_content,
        "meta": {
            "course": context.course_name,
            "semester": context.semester,
            "total_attempts": context.total_attempts,
            "weak_topics_count": len(context.weak_topics),
            "strong_topics_count": len(context.strong_topics)
        }
    }
