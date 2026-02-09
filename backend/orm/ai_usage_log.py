"""
backend/orm/ai_usage_log.py
Phase 8: AI Governance, Safety & Explainability Layer

AI Usage Log ORM - Governance logging for AI tool invocations.
NO prompts stored. NO responses stored. NO student content stored.
This is governance logging, not surveillance.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum as PyEnum

from backend.orm.base import Base


class AIFeatureType(str, PyEnum):
    """Types of AI features that can be invoked"""
    AI_COACH = "ai_coach"              # Student coaching
    AI_REVIEW = "ai_review"            # Student work review
    COUNTER_ARGUMENT = "counter_argument"  # Student counter-arguments
    JUDGE_ASSIST = "judge_assist"      # Judge assistance tools
    BENCH_QUESTIONS = "bench_questions"  # AI-generated bench questions
    FEEDBACK_SUGGEST = "feedback_suggest"  # Feedback suggestions


class AIUsageLog(Base):
    """
    Phase 8: AI Usage Governance Log
    
    Records WHO used AI, WHEN, and WHY.
    Does NOT record WHAT was sent or returned.
    
    Governance-only logging for:
    - Auditing AI access patterns
    - Proving compliance with role-based policies
    - Demonstrating advisory-only usage
    """
    __tablename__ = "ai_usage_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution scoping - ALWAYS enforced
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # User who invoked AI
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True
    )
    
    # Role at time of invocation (captured, not inferred)
    role_at_time = Column(String(50), nullable=False)
    
    # Project context (if applicable)
    project_id = Column(
        Integer,
        ForeignKey("moot_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # AI Feature invoked
    feature_name = Column(SQLEnum(AIFeatureType), nullable=False)
    
    # Purpose/description (high-level, not content)
    purpose = Column(String(255), nullable=True)
    
    # Timestamp
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Client IP for audit trail
    ip_address = Column(String(45), nullable=True)
    
    # Was this request blocked by governance?
    was_blocked = Column(Boolean, default=False, nullable=False)
    
    # If blocked, why?
    block_reason = Column(String(255), nullable=True)
    
    # Mandatory safety flags that were enforced
    advisory_only_enforced = Column(Boolean, default=True, nullable=False)
    not_evaluative_enforced = Column(Boolean, default=True, nullable=False)
    human_decision_required_enforced = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    institution = relationship("Institution", lazy="selectin")
    user = relationship("User", lazy="selectin")
    project = relationship("MootProject", lazy="selectin")
    
    def __repr__(self):
        status = "BLOCKED" if self.was_blocked else "ALLOWED"
        return f"<AIUsageLog({self.feature_name.value}, {status}, user={self.user_id})>"
    
    def to_dict(self, include_user=False):
        """Convert to dictionary for API responses"""
        data = {
            "id": self.id,
            "institution_id": self.institution_id,
            "role_at_time": self.role_at_time,
            "feature_name": self.feature_name.value if self.feature_name else None,
            "purpose": self.purpose,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "was_blocked": self.was_blocked,
            "block_reason": self.block_reason,
            "safety_flags": {
                "advisory_only": self.advisory_only_enforced,
                "not_evaluative": self.not_evaluative_enforced,
                "human_decision_required": self.human_decision_required_enforced,
            }
        }
        
        if self.project_id:
            data["project_id"] = self.project_id
        
        if include_user and self.user:
            data["user"] = {
                "id": self.user.id,
                "full_name": self.user.full_name if hasattr(self.user, 'full_name') else None,
                "email": self.user.email if hasattr(self.user, 'email') else None,
            }
        else:
            data["user_id"] = self.user_id
        
        return data
