"""
backend/orm/bulk_upload_session.py
Phase 6: Bulk upload tracking for student CSV imports
"""
import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.orm.base import Base


class BulkUploadStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BulkUploadSession(Base):
    """
    Bulk upload session tracking for CSV student imports.
    Phase 6: Tracks progress of large CSV uploads (500+ students).
    """
    __tablename__ = "bulk_upload_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False)
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    csv_file_path = Column(String(500), nullable=False)
    total_rows = Column(Integer, nullable=False)
    processed_rows = Column(Integer, default=0, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    error_count = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default=BulkUploadStatus.PENDING.value, nullable=False)
    error_log_path = Column(String(500), nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    institution = relationship("Institution", back_populates="bulk_upload_sessions")
    uploaded_by = relationship("User", backref="bulk_upload_sessions")
    
    def __repr__(self):
        return f"<BulkUploadSession(id={self.id}, status={self.status}, total={self.total_rows}, success={self.success_count})>"
    
    def to_dict(self):
        # Calculate progress percentage
        progress_percentage = 0
        estimated_time_remaining = None
        
        if self.total_rows > 0:
            progress_percentage = int((self.processed_rows / self.total_rows) * 100)
        
        # Estimate remaining time (rough calculation: 2 seconds per row)
        if self.status == BulkUploadStatus.PROCESSING.value and self.processed_rows > 0:
            remaining_rows = self.total_rows - self.processed_rows
            seconds_remaining = remaining_rows * 2
            minutes = seconds_remaining // 60
            seconds = seconds_remaining % 60
            estimated_time_remaining = f"00:{minutes:02d}:{seconds:02d}"
        
        return {
            "session_id": self.id,
            "institution_id": self.institution_id,
            "uploaded_by_user_id": self.uploaded_by_user_id,
            "status": self.status,
            "total_rows": self.total_rows,
            "processed_rows": self.processed_rows,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "progress_percentage": progress_percentage,
            "estimated_time_remaining": estimated_time_remaining,
            "error_log_path": self.error_log_path,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    def get_progress_percentage(self):
        if self.total_rows == 0:
            return 0
        return int((self.processed_rows / self.total_rows) * 100)
