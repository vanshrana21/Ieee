"""
backend/routes/notes.py
Phase 7: Smart Notes API
Phase 8: Auto-generate embeddings for semantic search
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, delete
from typing import List, Optional
from datetime import datetime
import logging

from backend.database import get_db
from backend.orm.user import User
from backend.orm.smart_note import SmartNote, ImportanceLevel
from backend.orm.subject import Subject
from backend.orm.case_content import CaseContent
from backend.orm.learn_content import LearnContent
from backend.orm.practice_question import PracticeQuestion
from backend.routes.auth import get_current_user
from backend.schemas.note_schemas import (
    SmartNoteCreate,
    SmartNoteUpdate,
    SmartNoteResponse,
    SmartNoteListResponse,
    AIAssistRequest,
    AIAssistResponse
)
from backend.services.ai_note_service import ai_assist_note
from backend.services.embedding_service import store_embedding, delete_embedding  # PHASE 8

router = APIRouter(prefix="/api/notes", tags=["notes"])
logger = logging.getLogger(__name__)

# ============================================================================
# CRUD ENDPOINTS
# ============================================================================

@router.post("", response_model=SmartNoteResponse, status_code=201)
async def create_note(
    note_data: SmartNoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new note.
    
    Security:
    - User must be authenticated
    - If entity is linked, validates user has access to it
    
    Phase 8: Auto-generates embedding for semantic search
    """
    
    # Validate entity access if linked
    if note_data.linked_entity_type and note_data.linked_entity_id:
        has_access = await _validate_entity_access(
            db=db,
            user=current_user,
            entity_type=note_data.linked_entity_type,
            entity_id=note_data.linked_entity_id
        )
        
        if not has_access:
            raise HTTPException(
                status_code=404,
                detail=f"{note_data.linked_entity_type.capitalize()} not found or not accessible"
            )
    
    # Create note
    new_note = SmartNote(
        user_id=current_user.id,
        title=note_data.title,
        content=note_data.content,
        linked_entity_type=note_data.linked_entity_type,
        linked_entity_id=note_data.linked_entity_id,
        tags=note_data.tags or [],
        importance=note_data.importance,  # Already a string in your model
        is_pinned=1 if note_data.is_pinned else 0
    )
    
    db.add(new_note)
    await db.commit()
    await db.refresh(new_note)
    
    # PHASE 8: Auto-generate embedding (non-blocking)
    try:
        embedding_text = f"{new_note.title}\n\n{new_note.content}"
        await store_embedding(
            db=db,
            entity_type="note",
            entity_id=new_note.id,
            text=embedding_text
        )
        logger.info(f"✅ Generated embedding for note {new_note.id}")
    except Exception as e:
        # Log but don't fail note creation
        logger.warning(f"⚠️  Failed to generate embedding for note {new_note.id}: {e}")
    
    # Enrich response
    response = new_note.to_dict()
    entity_meta = await _get_entity_metadata(db, new_note)
    response.update(entity_meta)
    
    return SmartNoteResponse(**response)


@router.get("", response_model=SmartNoteListResponse)
async def list_notes(
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    entity_id: Optional[int] = Query(None, description="Filter by entity ID"),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    search: Optional[str] = Query(None, description="Search in title/content"),
    importance: Optional[str] = Query(None, description="Filter by importance"),
    pinned_only: bool = Query(False, description="Show only pinned notes"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List user's notes with filtering and pagination.
    
    Security:
    - Only returns current user's notes
    """
    
    # Build query
    query = select(SmartNote).where(SmartNote.user_id == current_user.id)
    
    # Filters
    if entity_type:
        query = query.where(SmartNote.linked_entity_type == entity_type)
    
    if entity_id:
        query = query.where(SmartNote.linked_entity_id == entity_id)
    
    if tags:
        tag_list = [t.strip().lower() for t in tags.split(",")]
        # JSON contains check (SQLite-compatible)
        for tag in tag_list:
            query = query.where(SmartNote.tags.contains(tag))
    
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                SmartNote.title.ilike(search_pattern),
                SmartNote.content.ilike(search_pattern)
            )
        )
    
    if importance:
        query = query.where(SmartNote.importance == importance)
    
    if pinned_only:
        query = query.where(SmartNote.is_pinned == 1)
    
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0
    
    # Order: pinned first, then by importance, then by date
    query = query.order_by(
        SmartNote.is_pinned.desc(),
        SmartNote.importance.desc(),
        SmartNote.created_at.desc()
    )
    
    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    result = await db.execute(query)
    notes = result.scalars().all()
    
    # Enrich with entity metadata
    enriched_notes = []
    for note in notes:
        note_dict = note.to_dict()
        entity_meta = await _get_entity_metadata(db, note)
        note_dict.update(entity_meta)
        enriched_notes.append(SmartNoteResponse(**note_dict))
    
    return SmartNoteListResponse(
        notes=enriched_notes,
        total_count=total_count,
        page=page,
        page_size=page_size,
        has_more=(offset + page_size) < total_count
    )


@router.get("/{note_id}", response_model=SmartNoteResponse)
async def get_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific note by ID"""
    
    result = await db.execute(
        select(SmartNote).where(
            and_(
                SmartNote.id == note_id,
                SmartNote.user_id == current_user.id
            )
        )
    )
    note = result.scalar_one_or_none()
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    note_dict = note.to_dict()
    entity_meta = await _get_entity_metadata(db, note)
    note_dict.update(entity_meta)
    
    return SmartNoteResponse(**note_dict)


@router.put("/{note_id}", response_model=SmartNoteResponse)
async def update_note(
    note_id: int,
    note_data: SmartNoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update a note.
    
    Security:
    - Only owner can update
    
    Phase 8: Regenerates embedding if content changed
    """
    
    result = await db.execute(
        select(SmartNote).where(
            and_(
                SmartNote.id == note_id,
                SmartNote.user_id == current_user.id
            )
        )
    )
    note = result.scalar_one_or_none()
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Update fields
    if note_data.title is not None:
        note.title = note_data.title
    
    if note_data.content is not None:
        note.content = note_data.content
    
    if note_data.tags is not None:
        note.tags = note_data.tags
    
    if note_data.importance is not None:
        note.importance = note_data.importance
    
    if note_data.is_pinned is not None:
        note.is_pinned = 1 if note_data.is_pinned else 0
    
    note.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(note)
    
    # PHASE 8: Regenerate embedding if content changed
    if note_data.content is not None or note_data.title is not None:
        try:
            embedding_text = f"{note.title}\n\n{note.content}"
            await store_embedding(
                db=db,
                entity_type="note",
                entity_id=note.id,
                text=embedding_text,
                force_regenerate=True
            )
            logger.info(f"✅ Regenerated embedding for note {note.id}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to regenerate embedding for note {note.id}: {e}")
    
    note_dict = note.to_dict()
    entity_meta = await _get_entity_metadata(db, note)
    note_dict.update(entity_meta)
    
    return SmartNoteResponse(**note_dict)


@router.delete("/{note_id}", status_code=204)
async def delete_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a note
    
    Phase 8: Also deletes associated embedding
    """
    
    result = await db.execute(
        select(SmartNote).where(
            and_(
                SmartNote.id == note_id,
                SmartNote.user_id == current_user.id
            )
        )
    )
    note = result.scalar_one_or_none()
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # PHASE 8: Delete embedding
    try:
        await delete_embedding(db=db, entity_type="note", entity_id=note.id)
        logger.info(f"✅ Deleted embedding for note {note.id}")
    except Exception as e:
        logger.warning(f"⚠️  Failed to delete embedding for note {note.id}: {e}")
    
    await db.delete(note)
    await db.commit()
    
    return None


# ============================================================================
# AI ASSISTANCE ENDPOINT
# ============================================================================

@router.post("/ai-assist", response_model=AIAssistResponse)
async def ai_assist(
    request: AIAssistRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get AI assistance for a note.
    
    IMPORTANT: This NEVER modifies the original note.
    Returns AI-generated text that user can choose to use.
    """
    
    # Get note
    result = await db.execute(
        select(SmartNote).where(
            and_(
                SmartNote.id == request.note_id,
                SmartNote.user_id == current_user.id
            )
        )
    )
    note = result.scalar_one_or_none()
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    try:
        # Generate AI assistance
        ai_result = await ai_assist_note(
            content=note.content,
            action=request.action
        )
        
        return AIAssistResponse(
            note_id=note.id,
            action=request.action,
            result=ai_result,
            original_preserved=True
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"AI service unavailable: {str(e)}"
        )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def _validate_entity_access(
    db: AsyncSession,
    user: User,
    entity_type: str,
    entity_id: int
) -> bool:
    """Validate user has access to linked entity"""
    
    if not user.course_id or not user.current_semester:
        return False
    
    try:
        if entity_type == "subject":
            from backend.orm.curriculum import CourseCurriculum
            
            stmt = select(Subject).join(
                CourseCurriculum
            ).where(
                and_(
                    Subject.id == entity_id,
                    CourseCurriculum.course_id == user.course_id,
                    CourseCurriculum.semester <= user.current_semester
                )
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none() is not None
        
        elif entity_type == "case":
            from backend.orm.content_module import ContentModule
            from backend.orm.curriculum import CourseCurriculum
            
            stmt = select(CaseContent).join(
                ContentModule
            ).join(
                Subject
            ).join(
                CourseCurriculum
            ).where(
                and_(
                    CaseContent.id == entity_id,
                    CourseCurriculum.course_id == user.course_id,
                    CourseCurriculum.semester <= user.current_semester,
                    ContentModule.is_locked == False
                )
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none() is not None
        
        elif entity_type == "learn":
            from backend.orm.content_module import ContentModule
            from backend.orm.curriculum import CourseCurriculum
            
            stmt = select(LearnContent).join(
                ContentModule
            ).join(
                Subject
            ).join(
                CourseCurriculum
            ).where(
                and_(
                    LearnContent.id == entity_id,
                    CourseCurriculum.course_id == user.course_id,
                    CourseCurriculum.semester <= user.current_semester,
                    ContentModule.is_locked == False
                )
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none() is not None
        
        elif entity_type == "practice":
            from backend.orm.content_module import ContentModule
            from backend.orm.curriculum import CourseCurriculum
            
            stmt = select(PracticeQuestion).join(
                ContentModule
            ).join(
                Subject
            ).join(
                CourseCurriculum
            ).where(
                and_(
                    PracticeQuestion.id == entity_id,
                    CourseCurriculum.course_id == user.course_id,
                    CourseCurriculum.semester <= user.current_semester,
                    ContentModule.is_locked == False
                )
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none() is not None
        
        return False
    
    except Exception:
        return False


async def _get_entity_metadata(db: AsyncSession, note: SmartNote) -> dict:
    """Get metadata for linked entity"""
    
    if not note.linked_entity_type or not note.linked_entity_id:
        return {"entity_title": None, "entity_subtitle": None}
    
    try:
        if note.linked_entity_type == "subject":
            result = await db.execute(
                select(Subject).where(Subject.id == note.linked_entity_id)
            )
            entity = result.scalar_one_or_none()
            if entity:
                return {
                    "entity_title": entity.title,
                    "entity_subtitle": entity.code
                }
        
        elif note.linked_entity_type == "case":
            result = await db.execute(
                select(CaseContent).where(CaseContent.id == note.linked_entity_id)
            )
            entity = result.scalar_one_or_none()
            if entity:
                return {
                    "entity_title": entity.case_name,
                    "entity_subtitle": entity.citation
                }
        
        elif note.linked_entity_type == "learn":
            result = await db.execute(
                select(LearnContent).where(LearnContent.id == note.linked_entity_id)
            )
            entity = result.scalar_one_or_none()
            if entity:
                return {
                    "entity_title": entity.title,
                    "entity_subtitle": None
                }
        
        elif note.linked_entity_type == "practice":
            result = await db.execute(
                select(PracticeQuestion).where(PracticeQuestion.id == note.linked_entity_id)
            )
            entity = result.scalar_one_or_none()
            if entity:
                return {
                    "entity_title": f"Question: {entity.question[:50]}...",
                    "entity_subtitle": f"{entity.difficulty} • {entity.marks} marks"
                }
    
    except Exception:
        pass
    
    return {"entity_title": None, "entity_subtitle": None}
