"""
backend/routes/saved_searches.py
Phase 6.2: Saved Search Management API
Handles saving, editing, executing, and deleting search queries
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete, update
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

from backend.database import get_db
from backend.orm.user import User
from backend.orm.saved_search import SavedSearch
from backend.routes.auth import get_current_user

# Import search function from Phase 6.1
from backend.services.search_service import execute_search

router = APIRouter(prefix="/api/saved-searches", tags=["saved-searches"])

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class SavedSearchCreate(BaseModel):
    """Request to save a search"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    query: str = Field(..., min_length=2, max_length=500)
    filters: Optional[Dict[str, Any]] = None


class SavedSearchUpdate(BaseModel):
    """Request to update a saved search"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    query: Optional[str] = Field(None, min_length=2, max_length=500)
    filters: Optional[Dict[str, Any]] = None


class SavedSearchResponse(BaseModel):
    """Saved search response"""
    id: int
    name: str
    description: Optional[str]
    query: str
    filters: Dict[str, Any]
    created_at: str
    updated_at: str
    last_executed_at: Optional[str]

    class Config:
        from_attributes = True


class SavedSearchListResponse(BaseModel):
    """List of saved searches"""
    saved_searches: List[SavedSearchResponse]
    total_count: int


# ============================================================================
# SAVED SEARCH CRUD
# ============================================================================

@router.post("", response_model=SavedSearchResponse, status_code=201)
async def create_saved_search(
    search_data: SavedSearchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Save a search query for quick re-execution.
    
    Security:
    - User-specific (no sharing between users)
    - Filters validated at execution time
    """
    
    new_search = SavedSearch(
        user_id=current_user.id,
        name=search_data.name,
        description=search_data.description,
        query=search_data.query,
        filters=search_data.filters or {}
    )
    
    db.add(new_search)
    await db.commit()
    await db.refresh(new_search)
    
    return _to_response(new_search)


@router.get("", response_model=SavedSearchListResponse)
async def list_saved_searches(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all saved searches for current user.
    
    Security:
    - Only returns user's own searches
    """
    
    result = await db.execute(
        select(SavedSearch)
        .where(SavedSearch.user_id == current_user.id)
        .order_by(SavedSearch.updated_at.desc())
    )
    searches = result.scalars().all()
    
    return SavedSearchListResponse(
        saved_searches=[_to_response(s) for s in searches],
        total_count=len(searches)
    )


@router.get("/{search_id}", response_model=SavedSearchResponse)
async def get_saved_search(
    search_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific saved search by ID"""
    
    result = await db.execute(
        select(SavedSearch).where(
            and_(
                SavedSearch.id == search_id,
                SavedSearch.user_id == current_user.id
            )
        )
    )
    search = result.scalar_one_or_none()
    
    if not search:
        raise HTTPException(status_code=404, detail="Saved search not found")
    
    return _to_response(search)


@router.put("/{search_id}", response_model=SavedSearchResponse)
async def update_saved_search(
    search_id: int,
    search_data: SavedSearchUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update a saved search.
    
    Security:
    - Only owner can update
    """
    
    result = await db.execute(
        select(SavedSearch).where(
            and_(
                SavedSearch.id == search_id,
                SavedSearch.user_id == current_user.id
            )
        )
    )
    search = result.scalar_one_or_none()
    
    if not search:
        raise HTTPException(status_code=404, detail="Saved search not found")
    
    # Update fields
    if search_data.name is not None:
        search.name = search_data.name
    if search_data.description is not None:
        search.description = search_data.description
    if search_data.query is not None:
        search.query = search_data.query
    if search_data.filters is not None:
        search.filters = search_data.filters
    
    search.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(search)
    
    return _to_response(search)


@router.delete("/{search_id}", status_code=204)
async def delete_saved_search(
    search_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a saved search.
    
    Security:
    - Only owner can delete
    """
    
    result = await db.execute(
        select(SavedSearch).where(
            and_(
                SavedSearch.id == search_id,
                SavedSearch.user_id == current_user.id
            )
        )
    )
    search = result.scalar_one_or_none()
    
    if not search:
        raise HTTPException(status_code=404, detail="Saved search not found")
    
    await db.delete(search)
    await db.commit()
    
    return None


@router.post("/{search_id}/execute")
async def execute_saved_search(
    search_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Execute a saved search with current access controls.
    
    Security:
    - Access control applied at execution time (not storage time)
    - Respects current course/semester
    - Results may differ if user's permissions changed
    """
    
    # Get saved search
    result = await db.execute(
        select(SavedSearch).where(
            and_(
                SavedSearch.id == search_id,
                SavedSearch.user_id == current_user.id
            )
        )
    )
    search = result.scalar_one_or_none()
    
    if not search:
        raise HTTPException(status_code=404, detail="Saved search not found")
    
    # Update last_executed_at
    search.last_executed_at = datetime.utcnow()
    await db.commit()
    
    # Build filters from saved search
    filters = search.filters or {}
    filters['page'] = page
    filters['page_size'] = page_size
    
    # Execute search using Phase 6.1 search endpoint logic
    # Note: This reuses the existing search logic with access control
    from backend.routes.search import search_content as search_fn
    
    return await execute_search(
    q=search.query,
    content_types=filters.get('content_types'),
    subject_id=filters.get('subject_id'),
    semester=filters.get('semester'),
    page=page,
    page_size=page_size,
    db=db,
    current_user=current_user
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _to_response(search: SavedSearch) -> SavedSearchResponse:
    """Convert SavedSearch to response model"""
    return SavedSearchResponse(
        id=search.id,
        name=search.name,
        description=search.description,
        query=search.query,
        filters=search.filters or {},
        created_at=search.created_at.isoformat(),
        updated_at=search.updated_at.isoformat(),
        last_executed_at=search.last_executed_at.isoformat() if search.last_executed_at else None
    )
