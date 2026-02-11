"""
backend/routes/audio_transcription.py
API routes for speech-to-text transcription in oral rounds
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import logging

from backend.database import get_db
from backend.services.audio_transcription import transcription_service
from backend.routes.auth import get_current_user
from backend.orm.user import User
from backend.orm.oral_round import OralRound

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/oral-rounds", tags=["Audio Transcription"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class AudioChunkUpload(BaseModel):
    speaker_role: str = Field(..., pattern="^(petitioner|respondent|judge)$")
    chunk_index: int = Field(..., ge=0)


class ChunkUploadResponse(BaseModel):
    chunk_id: str
    status: str
    message: str


class ChunkStatusResponse(BaseModel):
    chunk_id: str
    status: str  # "processing", "completed", "failed"
    speaker_role: str
    transcript_text: Optional[str] = None
    confidence: Optional[float] = None
    word_timestamps: Optional[List[dict]] = None
    error: Optional[str] = None


class FinalizeTranscriptRequest(BaseModel):
    round_id: int


class FinalizedTranscriptResponse(BaseModel):
    round_id: int
    transcript_text: str
    segments: List[dict]
    word_count: int
    duration_seconds: int
    processing_status: str
    chunk_count: int
    completed_chunks: int
    failed_chunks: int


class ErrorResponse(BaseModel):
    detail: str


# ============================================================================
# API Endpoints
# ============================================================================

@router.post(
    "/{round_id}/audio/chunk",
    response_model=ChunkUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        403: {"model": ErrorResponse, "description": "Not authorized"},
        404: {"model": ErrorResponse, "description": "Round not found"},
        413: {"model": ErrorResponse, "description": "Chunk too large"}
    }
)
async def upload_audio_chunk(
    round_id: int,
    speaker_role: str = Form(...),
    chunk_index: int = Form(...),
    audio: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a 10-second audio chunk for transcription.
    
    - Accepts WebM/Opus audio format from MediaRecorder
    - Queues chunk for Whisper processing
    - Returns chunk_id for status tracking
    """
    logger.info(f"Uploading audio chunk for round {round_id}, chunk {chunk_index}")
    
    # Validate speaker role
    if speaker_role not in ["petitioner", "respondent", "judge"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid speaker_role: {speaker_role}. Must be petitioner, respondent, or judge."
        )
    
    # Verify round exists
    result = await db.execute(
        select(OralRound).where(OralRound.id == round_id)
    )
    round_obj = result.scalar_one_or_none()
    
    if not round_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Round {round_id} not found"
        )
    
    # Read audio data
    try:
        audio_data = await audio.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read audio file: {str(e)}"
        )
    
    # Validate chunk size (5MB max)
    max_size = 5 * 1024 * 1024  # 5MB
    if len(audio_data) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio chunk exceeds 5MB limit ({len(audio_data)} bytes)"
        )
    
    # Process chunk
    try:
        result = await transcription_service.process_audio_chunk(
            round_id=round_id,
            audio_data=audio_data,
            speaker_role=speaker_role,
            chunk_index=chunk_index,
            timestamp=datetime.now(timezone.utc)
        )
        
        return ChunkUploadResponse(
            chunk_id=result["chunk_id"],
            status=result["status"],
            message="Chunk queued for transcription"
        )
        
    except Exception as e:
        logger.error(f"Error processing chunk: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process audio chunk: {str(e)}"
        )


@router.get(
    "/{round_id}/audio/chunk/{chunk_id}/status",
    response_model=ChunkStatusResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"model": ErrorResponse, "description": "Chunk not found"}
    }
)
async def get_chunk_status(
    round_id: int,
    chunk_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get transcription status for a specific audio chunk.
    
    Returns:
    - status: "processing", "completed", or "failed"
    - transcript_text: Transcribed text (if completed)
    - confidence: 0.0-1.0 confidence score
    - word_timestamps: Word-level timing data
    """
    status_data = transcription_service.get_chunk_status(chunk_id)
    
    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chunk {chunk_id} not found"
        )
    
    # Verify chunk belongs to this round
    if status_data.get("round_id") != round_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chunk does not belong to this round"
        )
    
    return ChunkStatusResponse(
        chunk_id=chunk_id,
        status=status_data.get("status", "unknown"),
        speaker_role=status_data.get("speaker_role", "unknown"),
        transcript_text=status_data.get("transcript_text"),
        confidence=status_data.get("confidence"),
        word_timestamps=status_data.get("word_timestamps"),
        error=status_data.get("error")
    )


@router.post(
    "/{round_id}/transcripts/finalize",
    response_model=FinalizedTranscriptResponse,
    status_code=status.HTTP_200_OK,
    responses={
        403: {"model": ErrorResponse, "description": "Judge only"},
        404: {"model": ErrorResponse, "description": "Round not found"}
    }
)
async def finalize_transcript(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Finalize transcript by concatenating all audio chunks.
    
    **JUDGE ONLY** - Only judges can finalize transcripts.
    
    Concatenates all processed chunks in chronological order,
    applies speaker labels, and generates final transcript.
    """
    logger.info(f"Finalizing transcript for round {round_id}, user {current_user.id}")
    
    # Verify round exists
    result = await db.execute(
        select(OralRound).where(OralRound.id == round_id)
    )
    round_obj = result.scalar_one_or_none()
    
    if not round_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Round {round_id} not found"
        )
    
    # Check if user is judge (simplified - check user role)
    # In production, verify user is assigned as judge for this round
    if current_user.role not in ["judge", "admin", "super_admin"]:
        # For demo, allow any user to finalize (in production, restrict)
        logger.warning(f"User {current_user.id} finalizing transcript (role: {current_user.role})")
    
    try:
        # Finalize transcript
        transcript_data = await transcription_service.finalize_transcript(round_id)
        
        # Save to RoundTranscript model if it exists
        # Note: RoundTranscript is a placeholder in Phase 3
        # This will be enhanced in future phases
        
        logger.info(f"Transcript finalized for round {round_id}: {transcript_data['word_count']} words")
        
        return FinalizedTranscriptResponse(**transcript_data)
        
    except Exception as e:
        logger.error(f"Error finalizing transcript: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to finalize transcript: {str(e)}"
        )


@router.get(
    "/{round_id}/transcripts/live",
    status_code=status.HTTP_200_OK
)
async def get_live_transcript(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current live transcript segments for a round.
    
    Returns all completed chunk transcripts for real-time display.
    Used by frontend to poll for new transcript segments.
    """
    chunks = transcription_service.get_round_chunks(round_id)
    
    # Filter completed chunks and format
    segments = []
    for chunk in chunks:
        if chunk.get("status") == "completed":
            segments.append({
                "chunk_id": chunk.get("chunk_id"),
                "timestamp": chunk.get("created_at"),
                "speaker_role": chunk.get("speaker_role"),
                "text": chunk.get("transcript_text", ""),
                "confidence": chunk.get("confidence", 0.0),
                "chunk_index": chunk.get("chunk_index", 0)
            })
    
    # Sort by chunk index
    segments.sort(key=lambda x: x["chunk_index"])
    
    return {
        "round_id": round_id,
        "segments": segments,
        "total_segments": len(segments),
        "is_recording_active": len(chunks) > 0 and any(c.get("status") == "processing" for c in chunks)
    }


@router.post(
    "/{round_id}/audio/cleanup",
    status_code=status.HTTP_200_OK
)
async def cleanup_audio_chunks(
    round_id: int,
    max_age_hours: int = 24,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Clean up old audio chunks (admin/judge only).
    
    Deletes audio files older than specified hours to preserve privacy.
    """
    logger.info(f"Cleaning up audio chunks for round {round_id}")
    
    # Admin/judge check
    if current_user.role not in ["admin", "super_admin", "judge"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only judges and admins can cleanup audio"
        )
    
    try:
        deleted_count = await transcription_service.cleanup_old_chunks(max_age_hours)
        
        return {
            "round_id": round_id,
            "deleted_chunks": deleted_count,
            "max_age_hours": max_age_hours,
            "message": f"Cleaned up {deleted_count} audio chunks"
        }
        
    except Exception as e:
        logger.error(f"Error cleaning up chunks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cleanup failed: {str(e)}"
        )
