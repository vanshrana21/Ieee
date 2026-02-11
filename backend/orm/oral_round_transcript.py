"""
Phase 0: Virtual Courtroom Infrastructure - Oral Round Transcripts ORM Model
Tracks full round transcripts with audio transcription support and Whisper API integration.
"""
from sqlalchemy import Column, Integer, ForeignKey, DateTime, Enum as SQLEnum, func, String, Text, Boolean, Float, Index
from sqlalchemy.orm import relationship
import enum
import json
from backend.orm.base import Base


class TranscriptStatus(str, enum.Enum):
    """Processing status for transcript segments."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SpeakerRole(str, enum.Enum):
    """Speaker role for transcript segment."""
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    JUDGE = "judge"


class OralRoundTranscript(Base):
    """
    Transcripts table for oral rounds with audio transcription support.
    
    Stores both full transcript content and per-segment metadata including
    audio chunk IDs for Whisper API integration, word-level timestamps,
    and confidence scores.
    """
    __tablename__ = "oral_round_transcripts"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Core fields - Round identification
    round_id = Column(Integer, ForeignKey("oral_rounds.id"), nullable=False)
    
    # Transcript content
    transcript_text = Column(Text, nullable=False)  # Full transcript content
    transcript_json = Column(Text, nullable=True)  # Structured JSON with speaker + timestamp per segment
    word_count = Column(Integer, nullable=False, default=0)
    duration_seconds = Column(Integer, nullable=False, default=0)  # Round duration
    
    # Audio reference
    audio_file_path = Column(String(500), nullable=True)  # Path to full recorded audio
    
    # Per-segment audio transcription metadata (for 10-second chunks)
    speaker_role = Column(SQLEnum(SpeakerRole), nullable=True)  # Speaker for this segment
    audio_chunk_id = Column(String(100), nullable=True)  # UUID for 10s chunk
    whisper_job_id = Column(String(100), nullable=True)  # OpenAI Whisper job ID
    word_timestamps_json = Column(Text, nullable=True)  # JSON array of word-level timestamps
    confidence_score = Column(Float, nullable=True)  # 0.0-1.0 Whisper confidence
    
    # Processing status
    processing_status = Column(SQLEnum(TranscriptStatus), default=TranscriptStatus.PENDING)
    processing_error = Column(Text, nullable=True)  # Error message if failed
    generated_at = Column(DateTime, nullable=True)  # When transcription completed
    
    # Visibility
    is_public = Column(Boolean, default=True)  # Visible to teams
    
    # Metadata
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    round = relationship("OralRound", back_populates="transcripts")
    
    # Table indexes for common queries
    __table_args__ = (
        Index('idx_transcripts_round', 'round_id'),
        Index('idx_transcripts_chunk', 'audio_chunk_id'),
        Index('idx_transcripts_status', 'processing_status'),
    )
    
    def to_dict(self):
        """Convert transcript to dictionary for API responses."""
        return {
            "id": self.id,
            "round_id": self.round_id,
            "transcript": {
                "text": self.transcript_text,
                "json": self.get_transcript_json(),
                "word_count": self.word_count,
                "duration_seconds": self.duration_seconds
            },
            "audio": {
                "file_path": self.audio_file_path,
                "chunk_id": self.audio_chunk_id,
                "whisper_job_id": self.whisper_job_id
            },
            "segment": {
                "speaker_role": self.speaker_role.value if self.speaker_role else None,
                "word_timestamps": self.get_word_timestamps(),
                "confidence_score": self.confidence_score
            },
            "processing": {
                "status": self.processing_status.value if self.processing_status else None,
                "error": self.processing_error,
                "generated_at": self.generated_at.isoformat() if self.generated_at else None
            },
            "visibility": {
                "is_public": self.is_public
            },
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    def get_transcript_json(self):
        """Parse transcript JSON string to Python object."""
        if self.transcript_json:
            try:
                return json.loads(self.transcript_json)
            except json.JSONDecodeError:
                return None
        return None
    
    def set_transcript_json(self, data):
        """Serialize transcript data to JSON string."""
        self.transcript_json = json.dumps(data) if data else None
    
    def get_word_timestamps(self):
        """Parse word timestamps JSON string to Python list."""
        if self.word_timestamps_json:
            try:
                return json.loads(self.word_timestamps_json)
            except json.JSONDecodeError:
                return []
        return []
    
    def set_word_timestamps(self, timestamps):
        """Serialize word timestamps to JSON string."""
        self.word_timestamps_json = json.dumps(timestamps) if timestamps else None
    
    def mark_completed(self):
        """Mark transcript as completed."""
        self.processing_status = TranscriptStatus.COMPLETED
        self.generated_at = func.now()
    
    def mark_failed(self, error_message):
        """Mark transcript as failed with error."""
        self.processing_status = TranscriptStatus.FAILED
        self.processing_error = error_message
