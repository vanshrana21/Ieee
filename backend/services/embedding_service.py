"""
backend/services/embedding_service.py
Phase 8: Embedding Generation with Gemini

CRITICAL RULES:
- Never blocks main user flows
- Graceful degradation if API fails
- Never regenerates if text unchanged
- SQLite-compatible vector storage
"""

import os
import logging
import google.generativeai as genai
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.orm.semantic_embedding import SemanticEmbedding

logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


async def generate_embedding(text: str, model: str = "models/embedding-001") -> Optional[List[float]]:
    """
    Generate embedding vector for text using Gemini.
    
    Args:
        text: Input text to embed
        model: Gemini embedding model name
    
    Returns:
        List of floats (embedding vector) or None if failed
    
    Raises:
        None - gracefully returns None on failure
    """
    
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not configured - embeddings disabled")
        return None
    
    if not text or len(text.strip()) == 0:
        logger.warning("Empty text provided for embedding")
        return None
    
    try:
        # Truncate text to reasonable length (Gemini has token limits)
        max_chars = 10000
        truncated_text = text[:max_chars]
        
        # Generate embedding
        result = genai.embed_content(
            model=model,
            content=truncated_text,
            task_type="retrieval_document"
        )
        
        embedding_vector = result['embedding']
        
        logger.info(f"Generated embedding: {len(embedding_vector)} dimensions")
        return embedding_vector
    
    except Exception as e:
        logger.error(f"Embedding generation failed: {str(e)}")
        return None


async def store_embedding(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    text: str,
    force_regenerate: bool = False
) -> bool:
    """
    Store or update embedding for an entity.
    
    Args:
        db: Database session
        entity_type: Type of entity (note, case, learn, practice)
        entity_id: ID of entity
        text: Text to embed
        force_regenerate: If True, regenerate even if embedding exists
    
    Returns:
        True if embedding stored/updated, False if failed
    
    Logic:
    1. Compute text hash
    2. Check if embedding exists with same hash → skip
    3. Generate new embedding
    4. Store or update in database
    """
    
    try:
        # Compute text hash
        text_hash = SemanticEmbedding.compute_text_hash(text)
        
        # Check if embedding exists
        result = await db.execute(
            select(SemanticEmbedding).where(
                and_(
                    SemanticEmbedding.entity_type == entity_type,
                    SemanticEmbedding.entity_id == entity_id
                )
            )
        )
        existing = result.scalar_one_or_none()
        
        # Skip if unchanged
        if existing and not force_regenerate:
            if existing.text_hash == text_hash:
                logger.info(f"Embedding unchanged for {entity_type}:{entity_id}")
                return True
        
        # Generate embedding
        embedding_vector = await generate_embedding(text)
        
        if not embedding_vector:
            logger.warning(f"Failed to generate embedding for {entity_type}:{entity_id}")
            return False
        
        # Store or update
        if existing:
            existing.embedding = embedding_vector
            existing.text_hash = text_hash
            existing.dimension = len(embedding_vector)
            logger.info(f"Updated embedding for {entity_type}:{entity_id}")
        else:
            new_embedding = SemanticEmbedding(
                entity_type=entity_type,
                entity_id=entity_id,
                embedding=embedding_vector,
                text_hash=text_hash,
                embedding_model="gemini-embedding-001",
                dimension=len(embedding_vector)
            )
            db.add(new_embedding)
            logger.info(f"Created new embedding for {entity_type}:{entity_id}")
        
        await db.commit()
        return True
    
    except Exception as e:
        logger.error(f"Failed to store embedding: {str(e)}")
        await db.rollback()
        return False


async def delete_embedding(
    db: AsyncSession,
    entity_type: str,
    entity_id: int
) -> bool:
    """
    Delete embedding for an entity (e.g., when entity is deleted).
    
    Args:
        db: Database session
        entity_type: Type of entity
        entity_id: ID of entity
    
    Returns:
        True if deleted, False if not found or error
    """
    
    try:
        result = await db.execute(
            select(SemanticEmbedding).where(
                and_(
                    SemanticEmbedding.entity_type == entity_type,
                    SemanticEmbedding.entity_id == entity_id
                )
            )
        )
        embedding = result.scalar_one_or_none()
        
        if embedding:
            await db.delete(embedding)
            await db.commit()
            logger.info(f"Deleted embedding for {entity_type}:{entity_id}")
            return True
        
        return False
    
    except Exception as e:
        logger.error(f"Failed to delete embedding: {str(e)}")
        await db.rollback()
        return False


async def batch_generate_embeddings(
    db: AsyncSession,
    entity_type: str,
    entities: List[tuple]  # [(id, text), ...]
) -> int:
    """
    Generate embeddings for multiple entities in batch.
    
    Args:
        db: Database session
        entity_type: Type of all entities
        entities: List of (entity_id, text) tuples
    
    Returns:
        Number of embeddings successfully generated
    
    Usage:
        entities = [(1, "text1"), (2, "text2"), ...]
        count = await batch_generate_embeddings(db, "note", entities)
    """
    
    success_count = 0
    
    for entity_id, text in entities:
        success = await store_embedding(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            text=text
        )
        if success:
            success_count += 1
    
    logger.info(f"Batch generated {success_count}/{len(entities)} embeddings for {entity_type}")
    return success_count
