"""
backend/orm/submission_audit.py
Phase 5D: Submission audit log for compliance and accountability
Append-only log of all submission actions
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from datetime import datetime
from backend.orm.base import Base


class SubmissionAuditLog(Base):
    """
    Phase 5D: Append-only audit log for submission actions.
    Every submission, lock, unlock, and override is logged here.
    """
    __tablename__ = "submission_audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution scoping
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # What was affected
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("moot_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Who performed the action
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_role = Column(String(50), nullable=False)  # STUDENT, JUDGE, FACULTY, ADMIN, SUPER_ADMIN
    
    # Action details
    action = Column(String(50), nullable=False)  # submit, lock, unlock, extend_deadline, force_submit, etc.
    reason = Column(Text, nullable=True)  # Required for admin actions
    
    # Context at time of action
    competition_status = Column(String(50), nullable=True)  # Status when action occurred
    deadline_at_action = Column(DateTime, nullable=True)  # Current deadline at action time
    
    # Metadata
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "competition_id": self.competition_id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "user_role": self.user_role,
            "action": self.action,
            "reason": self.reason,
            "competition_status": self.competition_status,
            "deadline_at_action": self.deadline_at_action.isoformat() if self.deadline_at_action else None,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
