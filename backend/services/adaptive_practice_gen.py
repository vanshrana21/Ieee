"""
backend/services/adaptive_practice_gen.py
Phase 9B: Generate adaptive practice questions using AI
"""

import os
import logging
import uuid
from typing import List, Dict, Any, Literal
from sqlalchemy.ext.asyncio import AsyncSession

import google.generativeai as genai

from backend.orm.user import User
from backend.schemas.practice_schemas import GeneratedQuestion, QuestionRubric
from backend.services.mastery_calculator import get_weak_topics
from backend.services.rag_service import rag_retrieve_for_tutor

logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


async def generate_adaptive_questions(
    user: User,
    subject_id: int,
    count: int,
    difficulty: Literal["adaptive", "easy", "medium", "hard"],
    db: AsyncSession
) -> List[GeneratedQuestion]:
    """
    Generate practice questions adapted to user's mastery level.
    
    Process:
    1. If adaptive: Get weak topics from mastery calculator
    2. Retrieve relevant content via RAG
    3. Generate questions using Gemini with strict constraints
    4. Parse and structure questions
    
    Args:
        user: Authenticated user
        subject_id: Subject ID
        count: Number of questions
        difficulty: Difficulty level or 'adaptive'
        db: Database session
    
    Returns:
        List of GeneratedQuestion objects
    """
    
    logger.info(f"Generating {count} questions: subject={subject_id}, difficulty={difficulty}")
    
    # 1. Determine topics and difficulty distribution
    if difficulty == "adaptive":
        # Get weak topics
        weak_topics = await get_weak_topics(user.id, subject_id, db, limit=3)
        
        if not weak_topics:
            # Fallback to general topics
            weak_topics = ["general"]
        
        # Adaptive difficulty distribution
        difficulty_dist = _calculate_adaptive_distribution(count)
        target_topics = weak_topics
    else:
        # Use specified difficulty
        difficulty_dist = {difficulty: count}
        target_topics = []  # Will retrieve broadly
    
    logger.info(f"Target topics: {target_topics}, distribution: {difficulty_dist}")
    
    # 2. Retrieve relevant content
    query = " ".join(target_topics) if target_topics else f"subject {subject_id} practice"
    
    retrieved_docs = await rag_retrieve_for_tutor(
        query=query,
        user=user,
        db=db,
        subject_id=subject_id,
        top_k=10
    )
    
    if not retrieved_docs:
        logger.warning(f"No documents retrieved for subject {subject_id}")
        raise ValueError("No course materials found for this subject")
    
    # 3. Generate questions using Gemini
    questions = await _generate_questions_with_llm(
        retrieved_docs=retrieved_docs,
        difficulty_dist=difficulty_dist,
        target_topics=target_topics
    )
    
    logger.info(f"Generated {len(questions)} questions")
    
    return questions


def _calculate_adaptive_distribution(count: int) -> Dict[str, int]:
    """
    Calculate difficulty distribution for adaptive questions.
    
    Distribution:
    - Easy: 20%
    - Medium: 60%
    - Hard: 20%
    """
    
    easy_count = max(1, int(count * 0.2))
    hard_count = max(1, int(count * 0.2))
    medium_count = count - easy_count - hard_count
    
    return {
        "easy": easy_count,
        "medium": medium_count,
        "hard": hard_count
    }


async def _generate_questions_with_llm(
    retrieved_docs: List[Dict[str, Any]],
    difficulty_dist: Dict[str, int],
    target_topics: List[str]
) -> List[GeneratedQuestion]:
    """
    Generate questions using Gemini with retrieved documents.
    
    CRITICAL: Use ONLY provided documents - no hallucination.
    """
    
    # Build prompt
    system_prompt = _build_generation_prompt(retrieved_docs, difficulty_dist, target_topics)
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    try:
        response = model.generate_content(
            system_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.6,
                max_output_tokens=2000
            )
        )
        
        # Parse response
        questions = _parse_llm_response(response.text, retrieved_docs, difficulty_dist)
        
        return questions
    
    except Exception as e:
        logger.error(f"Question generation failed: {e}")
        raise ValueError(f"Failed to generate questions: {str(e)}")


def _build_generation_prompt(
    retrieved_docs: List[Dict[str, Any]],
    difficulty_dist: Dict[str, int],
    target_topics: List[str]
) -> str:
    """Build prompt for question generation"""
    
    # Format documents
    docs_section = "\n\n".join([
        f"[{i+1}] {doc['doc_type'].upper()}:{doc['doc_id']} - {doc['title']}\n{doc['snippet']}"
        for i, doc in enumerate(retrieved_docs)
    ])
    
    # Format difficulty requirements
    diff_requirements = "\n".join([
        f"- {diff.capitalize()}: {count} question(s)"
        for diff, count in difficulty_dist.items()
    ])
    
    topics_section = f"Focus topics: {', '.join(target_topics)}" if target_topics else "General topics from materials"
    
    return f"""You are an Indian law exam question generator.

TASK: Generate practice questions for law students based ONLY on the provided course materials.

REQUIREMENTS:
{diff_requirements}

{topics_section}

DIFFICULTY GUIDELINES:
- Easy: Recall/define concepts (100-150 words)
- Medium: Apply concepts/compare (200-300 words)
- Hard: Analyze/synthesize cases (400-500 words)

COURSE MATERIALS (use ONLY these):
{docs_section}

OUTPUT FORMAT (JSON):
Generate an array of question objects. Each question must have:
{{
  "question": "Question text",
  "difficulty": "easy|medium|hard",
  "marks": 2-10 (based on difficulty),
  "topic_tags": ["tag1", "tag2"],
  "model_answer": "Complete answer using materials",
  "rubric": {{
    "required_keywords": ["keyword1", "keyword2"],
    "optional_keywords": ["bonus1"],
    "keyword_score": points_per_keyword,
    "max_score": total_marks
  }},
  "source_doc_ids": [1, 3]
}}

CRITICAL RULES:
1. Use ONLY the provided materials
2. Do NOT invent facts or cases
3. Every question must cite source_doc_ids
4. Model answers must be exam-quality
5. Rubrics must have 3-5 required keywords

Generate the questions now as a JSON array."""


def _parse_llm_response(
    response_text: str,
    retrieved_docs: List[Dict[str, Any]],
    difficulty_dist: Dict[str, int]
) -> List[GeneratedQuestion]:
    """
    Parse LLM response into structured questions.
    
    Handles JSON parsing and validation.
    """
    
    import json
    import re
    
    # Extract JSON array from response
    # Look for JSON array pattern
    json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
    
    if not json_match:
        logger.error(f"No JSON array found in response: {response_text[:200]}")
        raise ValueError("Failed to parse question response")
    
    try:
        questions_data = json.loads(json_match.group(0))
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing failed: {e}")
        raise ValueError("Invalid JSON in response")
    
    # Convert to GeneratedQuestion objects
    questions = []
    
    for q_data in questions_data:
        try:
            # Generate unique ID
            question_id = f"gen-{uuid.uuid4().hex[:8]}"
            
            # Build rubric
            rubric_data = q_data.get("rubric", {})
            rubric = QuestionRubric(
                required_keywords=rubric_data.get("required_keywords", []),
                optional_keywords=rubric_data.get("optional_keywords", []),
                keyword_score=rubric_data.get("keyword_score", 1.0),
                max_score=rubric_data.get("max_score", q_data.get("marks", 5.0))
            )
            
            # Build question
            question = GeneratedQuestion(
                question_id=question_id,
                question=q_data.get("question", ""),
                question_type="short_answer" if q_data.get("marks", 5) <= 5 else "long_answer",
                marks=q_data.get("marks", 5.0),
                difficulty=q_data.get("difficulty", "medium"),
                topic_tags=q_data.get("topic_tags", []),
                model_answer=q_data.get("model_answer", ""),
                rubric=rubric,
                source_doc_ids=q_data.get("source_doc_ids", [])
            )
            
            questions.append(question)
        
        except Exception as e:
            logger.warning(f"Failed to parse question: {e}")
            continue
    
    logger.info(f"Parsed {len(questions)} questions from LLM response")
    
    return questions
