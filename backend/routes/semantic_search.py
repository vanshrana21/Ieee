"""
backend/routes/semantic_search.py
Phase 8: Semantic Search REST API
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.orm.user import User
from backend.routes.auth import get_current_user
from backend.services.semantic_search_service import semantic_search
from backend.services.embedding_service import store_embedding

router = APIRouter(prefix="/api/search", tags=["semantic-search"])


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class SemanticSearchResult(BaseModel):
    """Single search result"""
    entity_type: str
    entity_id: int
    title: str
    snippet: str
    similarity_score: float
    metadata: dict


class SemanticSearchResponse(BaseModel):
    """Semantic search response"""
    query: str
    results: List[SemanticSearchResult]
    total_count: int
    
    class Config:
        from_attributes = True


class EmbeddingGenerateRequest(BaseModel):
    """Request to generate embedding for an entity"""
    entity_type: str = Field(..., pattern="^(note|case|learn|practice)$")
    entity_id: int = Field(..., gt=0)
    text: str = Field(..., min_length=1)



# ============================================================================
# SEMANTIC SEARCH ENDPOINT
# ============================================================================

@router.get("/semantic", response_model=SemanticSearchResponse)
async def search_semantic(
    q: str = Query(..., min_length=2, max_length=500, description="Search query"),
    entity_types: Optional[str] = Query(None, description="Comma-separated: note,case,learn,practice"),
    subject_id: Optional[int] = Query(None, description="Filter by subject ID"),
    top_k: int = Query(20, ge=1, le=100, description="Max results"),
    min_similarity: float = Query(0.3, ge=0.0, le=1.0, description="Minimum similarity threshold"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Semantic search across notes, cases, learn content, and practice questions.
    
    Uses embeddings and cosine similarity for intelligent search.
    
    Examples:
        - `/api/search/semantic?q=basic structure doctrine`
          → Finds Kesavananda Bharati, notes, learn modules
        
        - `/api/search/semantic?q=contract offer&entity_types=case,learn`
          → Searches only cases and learn content
        
        - `/api/search/semantic?q=article 21&subject_id=5`
          → Searches within a specific subject
    
    Security:
        - Only searches content accessible to user (by course/semester)
        - User's own notes only
        - Respects locked modules
    """
    
    # Parse entity types
    entity_type_list = None
    if entity_types:
        entity_type_list = [t.strip() for t in entity_types.split(",") if t.strip()]
    
    # Perform semantic search
    results = await semantic_search(
        query=q,
        db=db,
        current_user=current_user,
        entity_types=entity_type_list,
        subject_id=subject_id,
        top_k=top_k,
        min_similarity=min_similarity
    )
    
    # Convert to response model
    search_results = [
        SemanticSearchResult(**result) for result in results
    ]
    
    return SemanticSearchResponse(
        query=q,
        results=search_results,
        total_count=len(search_results)
    )


# ============================================================================
# EMBEDDING MANAGEMENT (ADMIN/BACKGROUND)
# ============================================================================

@router.post("/embeddings/generate", status_code=201)
async def generate_embedding_for_entity(
    request: EmbeddingGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate embedding for a specific entity.
    
    This is typically called:
    - Automatically when notes are created/updated
    - By background jobs for bulk generation
    - Manually by admins for reindexing
    
    Security:
        - Users can only generate embeddings for their own notes
        - Admins can generate for all content
    """
    
    # For notes, verify ownership
    if request.entity_type == "note":
        from backend.orm.smart_note import SmartNote
        from sqlalchemy import select, and_
        
        result = await db.execute(
            select(SmartNote).where(
                and_(
                    SmartNote.id == request.entity_id,
                    SmartNote.user_id == current_user.id
                )
            )
        )
        note = result.scalar_one_or_none()
        
        if not note:
            raise HTTPException(
                status_code=404,
                detail="Note not found or not owned by user"
            )
    
    # Generate and store embedding
    success = await store_embedding(
        db=db,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        text=request.text,
        force_regenerate=True
    )
    
    if success:
        return {
            "success": True,
            "message": f"Embedding generated for {request.entity_type}:{request.entity_id}"
        }
    else:
        raise HTTPException(
            status_code=503,
            detail="Embedding generation failed (check API configuration)"
        )
