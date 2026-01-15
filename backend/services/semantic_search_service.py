"""
backend/services/semantic_search_service.py
Phase 8: Semantic Search with Cosine Similarity

ARCHITECTURE:
- Pure Python cosine similarity (no external dependencies)
- Works with SQLite (JSON vectors)
- Extensible to Postgres + pgvector
- Access-control aware (respects user permissions)
"""

import logging
import math
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from backend.orm.semantic_embedding import SemanticEmbedding
from backend.orm.smart_note import SmartNote
from backend.orm.case_content import CaseContent
from backend.orm.learn_content import LearnContent
from backend.orm.practice_question import PracticeQuestion
from backend.orm.subject import Subject
from backend.orm.content_module import ContentModule
from backend.orm.curriculum import CourseCurriculum
from backend.orm.user import User
from backend.services.embedding_service import generate_embedding

logger = logging.getLogger(__name__)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Compute cosine similarity between two vectors.
    
    Formula: cos(θ) = (A · B) / (||A|| × ||B||)
    
    Args:
        vec1: First vector
        vec2: Second vector
    
    Returns:
        Similarity score between -1 and 1 (typically 0 to 1 for embeddings)
    
    Example:
        >>> v1 = [1.0, 0.0, 0.0]
        >>> v2 = [1.0, 0.0, 0.0]
        >>> cosine_similarity(v1, v2)
        1.0
    """
    
    if len(vec1) != len(vec2):
        raise ValueError(f"Vector dimensions must match: {len(vec1)} vs {len(vec2)}")
    
    # Dot product
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    
    # Magnitudes
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))
    
    # Avoid division by zero
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)


async def semantic_search(
    query: str,
    db: AsyncSession,
    current_user: User,
    entity_types: Optional[List[str]] = None,
    subject_id: Optional[int] = None,
    top_k: int = 20,
    min_similarity: float = 0.3
) -> List[Dict[str, Any]]:
    """
    Perform semantic search across entities.
    
    Args:
        query: Search query text
        db: Database session
        current_user: Authenticated user
        entity_types: Filter by entity types (note, case, learn, practice)
        subject_id: Filter by subject
        top_k: Maximum results to return
        min_similarity: Minimum similarity threshold (0-1)
    
    Returns:
        List of search results with metadata and similarity scores
    
    Algorithm:
    1. Generate query embedding
    2. Fetch all embeddings (filtered by entity type)
    3. Compute cosine similarity for each
    4. Sort by similarity (descending)
    5. Apply access control filters
    6. Enrich with entity metadata
    7. Return top K results
    """
    
    # Generate query embedding
    query_embedding = await generate_embedding(query)
    
    if not query_embedding:
        logger.warning("Failed to generate query embedding - falling back to empty results")
        return []
    
    # Build embedding query
    embedding_query = select(SemanticEmbedding)
    
    if entity_types:
        embedding_query = embedding_query.where(
            SemanticEmbedding.entity_type.in_(entity_types)
        )
    
    # Fetch embeddings
    result = await db.execute(embedding_query)
    embeddings = result.scalars().all()
    
    # Compute similarities
    similarities = []
    
    for emb in embeddings:
        try:
            similarity = cosine_similarity(query_embedding, emb.embedding)
            
            if similarity >= min_similarity:
                similarities.append({
                    "entity_type": emb.entity_type,
                    "entity_id": emb.entity_id,
                    "similarity": similarity
                })
        except Exception as e:
            logger.error(f"Similarity computation failed for {emb.entity_type}:{emb.entity_id}: {e}")
    
    # Sort by similarity (descending)
    similarities.sort(key=lambda x: x['similarity'], reverse=True)
    
    # Take top K
    top_results = similarities[:top_k]
    
    # Enrich with entity metadata and apply access control
    enriched_results = []
    
    for item in top_results:
        entity_data = await _get_entity_with_access_check(
            db=db,
            entity_type=item['entity_type'],
            entity_id=item['entity_id'],
            user=current_user,
            subject_id=subject_id
        )
        
        if entity_data:
            entity_data['similarity_score'] = round(item['similarity'], 4)
            enriched_results.append(entity_data)
    
    logger.info(f"Semantic search: {len(enriched_results)} results for query '{query[:50]}'")
    
    return enriched_results


async def _get_entity_with_access_check(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    user: User,
    subject_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    Fetch entity with access control validation.
    
    Returns entity metadata if user has access, None otherwise.
    """
    
    try:
        if entity_type == "note":
            # User's own notes only
            result = await db.execute(
                select(SmartNote).where(
                    and_(
                        SmartNote.id == entity_id,
                        SmartNote.user_id == user.id
                    )
                )
            )
            note = result.scalar_one_or_none()
            
            if note:
                return {
                    "entity_type": "note",
                    "entity_id": note.id,
                    "title": note.title,
                    "snippet": note.content[:200] + "..." if len(note.content) > 200 else note.content,
                    "metadata": {
                        "tags": note.tags or [],
                        "importance": note.importance,
                        "is_pinned": bool(note.is_pinned),
                        "linked_entity_type": note.linked_entity_type,
                        "linked_entity_id": note.linked_entity_id
                    }
                }
        
        elif entity_type == "case":
            # Check access via curriculum
            stmt = select(CaseContent, Subject).join(
                ContentModule, CaseContent.module_id == ContentModule.id
            ).join(
                Subject, ContentModule.subject_id == Subject.id
            ).join(
                CourseCurriculum, Subject.id == CourseCurriculum.subject_id
            ).where(
                and_(
                    CaseContent.id == entity_id,
                    CourseCurriculum.course_id == user.course_id,
                    CourseCurriculum.semester <= user.current_semester,
                    ContentModule.is_locked == False
                )
            )
            
            if subject_id:
                stmt = stmt.where(Subject.id == subject_id)
            
            result = await db.execute(stmt)
            row = result.first()
            
            if row:
                case, subject = row
                return {
                    "entity_type": "case",
                    "entity_id": case.id,
                    "title": case.case_name,
                    "snippet": case.summary[:200] + "..." if len(case.summary) > 200 else case.summary,
                    "metadata": {
                        "citation": case.citation,
                        "year": case.year,
                        "subject_code": subject.code,
                        "subject_name": subject.title,
                        "exam_importance": case.exam_importance,
                        "tags": case.tags or []
                    }
                }
        
        elif entity_type == "learn":
            stmt = select(LearnContent, Subject).join(
                ContentModule, LearnContent.module_id == ContentModule.id
            ).join(
                Subject, ContentModule.subject_id == Subject.id
            ).join(
                CourseCurriculum, Subject.id == CourseCurriculum.subject_id
            ).where(
                and_(
                    LearnContent.id == entity_id,
                    CourseCurriculum.course_id == user.course_id,
                    CourseCurriculum.semester <= user.current_semester,
                    ContentModule.is_locked == False
                )
            )
            
            if subject_id:
                stmt = stmt.where(Subject.id == subject_id)
            
            result = await db.execute(stmt)
            row = result.first()
            
            if row:
                learn, subject = row
                return {
                    "entity_type": "learn",
                    "entity_id": learn.id,
                    "title": learn.title,
                    "snippet": learn.summary[:200] + "..." if len(learn.summary) > 200 else learn.summary,
                    "metadata": {
                        "subject_code": subject.code,
                        "subject_name": subject.title,
                        "content_type": learn.content_type,
                        "tags": learn.tags or []
                    }
                }
        
        elif entity_type == "practice":
            stmt = select(PracticeQuestion, Subject).join(
                ContentModule, PracticeQuestion.module_id == ContentModule.id
            ).join(
                Subject, ContentModule.subject_id == Subject.id
            ).join(
                CourseCurriculum, Subject.id == CourseCurriculum.subject_id
            ).where(
                and_(
                    PracticeQuestion.id == entity_id,
                    CourseCurriculum.course_id == user.course_id,
                    CourseCurriculum.semester <= user.current_semester,
                    ContentModule.is_locked == False
                )
            )
            
            if subject_id:
                stmt = stmt.where(Subject.id == subject_id)
            
            result = await db.execute(stmt)
            row = result.first()
            
            if row:
                question, subject = row
                return {
                    "entity_type": "practice",
                    "entity_id": question.id,
                    "title": f"Question: {question.question[:80]}...",
                    "snippet": question.question[:200] + "..." if len(question.question) > 200 else question.question,
                    "metadata": {
                        "subject_code": subject.code,
                        "subject_name": subject.title,
                        "question_type": question.question_type,
                        "difficulty": question.difficulty,
                        "marks": question.marks,
                        "tags": question.tags or []
                    }
                }
    
    except Exception as e:
        logger.error(f"Entity fetch failed for {entity_type}:{entity_id}: {e}")
    
    return None
