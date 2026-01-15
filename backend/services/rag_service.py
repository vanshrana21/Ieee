"""
backend/services/rag_service.py
Phase 9A: RAG retrieval with curriculum filtering
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.orm.user import User
from backend.orm.semantic_embedding import SemanticEmbedding
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.smart_note import SmartNote
from backend.orm.content_module import ContentModule
from backend.orm.subject import Subject
from backend.orm.curriculum import CourseCurriculum
from backend.services.embedding_service import generate_embedding

logger = logging.getLogger(__name__)


async def rag_retrieve_for_tutor(
    query: str,
    user: User,
    db: AsyncSession,
    subject_id: Optional[int] = None,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant documents for tutor with strict curriculum filtering.
    
    Args:
        query: User's question
        user: Authenticated user
        db: Database session
        subject_id: Optional subject filter
        top_k: Max results
    
    Returns:
        List of {doc_id, doc_type, score, snippet, title, full_content}
    
    Filters:
        - Only user's course
        - Only current or past semesters
        - Only unlocked modules
        - User's own notes only
    """
    
    # 1. Generate query embedding
    query_embedding = await generate_embedding(query)
    
    if not query_embedding:
        logger.warning("Failed to generate query embedding")
        return []
    
    # 2. Get all embeddings
    embedding_query = select(SemanticEmbedding)
    
    result = await db.execute(embedding_query)
    embeddings = result.scalars().all()
    
    if not embeddings:
        logger.warning("No embeddings found in database")
        return []
    
    # 3. Compute similarities
    from backend.services.semantic_search_service import cosine_similarity
    
    similarities = []
    for emb in embeddings:
        try:
            similarity = cosine_similarity(query_embedding, emb.embedding)
            
            if similarity >= 0.3:  # Minimum threshold
                similarities.append({
                    "entity_type": emb.entity_type,
                    "entity_id": emb.entity_id,
                    "similarity": similarity
                })
        except Exception as e:
            logger.error(f"Similarity computation failed for {emb.entity_type}:{emb.entity_id}: {e}")
    
    # 4. Sort by similarity
    similarities.sort(key=lambda x: x['similarity'], reverse=True)
    
    # 5. Fetch full documents with access control
    results = []
    
    for item in similarities[:top_k * 3]:  # Fetch more to account for filtering
        doc = await _fetch_document_with_access_check(
            db=db,
            entity_type=item['entity_type'],
            entity_id=item['entity_id'],
            user=user,
            subject_id=subject_id
        )
        
        if doc:
            doc['score'] = round(item['similarity'], 3)
            results.append(doc)
        
        if len(results) >= top_k:
            break
    
    logger.info(f"RAG retrieved {len(results)} documents for query: {query[:50]}")
    
    return results


async def _fetch_document_with_access_check(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    user: User,
    subject_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    Fetch document with full access control validation.
    
    Returns document dict or None if access denied.
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
                    "doc_id": note.id,
                    "doc_type": "note",
                    "title": note.title,
                    "snippet": note.content[:300],
                    "full_content": f"{note.title}\n\n{note.content}"
                }
        
        elif entity_type == "learn":
            # Check curriculum access
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
                    "doc_id": learn.id,
                    "doc_type": "learn",
                    "title": f"{learn.title} ({subject.code})",
                    "snippet": learn.summary[:300] if learn.summary else learn.explanation[:300],
                    "full_content": f"{learn.title}\n\n{learn.summary}\n\n{learn.explanation}"
                }
        
        elif entity_type == "case":
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
                    "doc_id": case.id,
                    "doc_type": "case",
                    "title": f"{case.case_name} ({case.citation})",
                    "snippet": case.summary[:300],
                    "full_content": f"{case.case_name}\n{case.citation}\n\n{case.summary}\n\n{case.facts}\n\n{case.legal_principles}"
                }
    
    except Exception as e:
        logger.error(f"Document fetch failed for {entity_type}:{entity_id}: {e}")
    
    return None
