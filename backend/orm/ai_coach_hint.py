"""
backend/orm/ai_coach_hint.py
Phase 4: AI Coach Hints for Oral Rounds (Hybrid Mode 3)
Isolated from existing models - NEW FILE
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Enum as SQLEnum, func
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.orm.base import Base


class HintType(str, enum.Enum):
    """Types of AI coach hints"""
    CITATION = "citation"  # Citation format hints (SCC format)
    ETIQUETTE = "etiquette"  # Courtroom etiquette hints ("My Lord")
    DOCTRINE = "doctrine"  # Legal doctrine hints (apply proportionality test)
    STRUCTURE = "structure"  # Argument structure hints (IRAC format)


class AICoachHint(Base):
    """
    Phase 4: AI Coach hints generated during oral arguments.
    Non-intrusive real-time coaching for human teams.
    """
    __tablename__ = "ai_coach_hints"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    round_id = Column(Integer, ForeignKey("oral_rounds.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Student receiving hint
    
    # Hint content
    hint_type = Column(SQLEnum(HintType), nullable=False)
    hint_text = Column(Text, nullable=False)
    trigger_keyword = Column(String(255), nullable=True)  # Keyword that triggered hint
    
    # Context
    user_argument_context = Column(Text, nullable=True)  # Snippet of user's argument
    
    # Display status
    is_displayed = Column(Boolean, default=False)
    displayed_at = Column(DateTime, nullable=True)
    is_dismissed = Column(Boolean, default=False)
    dismissed_at = Column(DateTime, nullable=True)
    dismissed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    round = relationship("OralRound", foreign_keys=[round_id], lazy="selectin")
    team = relationship("Team", foreign_keys=[team_id], lazy="selectin")
    user = relationship("User", foreign_keys=[user_id], lazy="selectin")
    dismissed_by = relationship("User", foreign_keys=[dismissed_by_user_id], lazy="selectin")
    
    def display(self):
        """Mark hint as displayed"""
        self.is_displayed = True
        self.displayed_at = datetime.utcnow()
    
    def dismiss(self, user_id: int):
        """Dismiss the hint"""
        self.is_dismissed = True
        self.dismissed_at = datetime.utcnow()
        self.dismissed_by_user_id = user_id
    
    def to_dict(self):
        """Convert hint to dictionary for API responses"""
        return {
            "id": self.id,
            "round_id": self.round_id,
            "team_id": self.team_id,
            "team_name": self.team.name if self.team else None,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else None,
            "hint_type": self.hint_type.value if self.hint_type else None,
            "hint_text": self.hint_text,
            "trigger_keyword": self.trigger_keyword,
            "is_displayed": self.is_displayed,
            "displayed_at": self.displayed_at.isoformat() if self.displayed_at else None,
            "is_dismissed": self.is_dismissed,
            "dismissed_at": self.dismissed_at.isoformat() if self.dismissed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class HintTemplate(Base):
    """
    Phase 4: Reusable hint templates for AI coach.
    Stores common hint patterns that can be triggered by keywords.
    """
    __tablename__ = "ai_coach_hint_templates"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    hint_type = Column(SQLEnum(HintType), nullable=False)
    trigger_pattern = Column(String(255), nullable=False)  # Regex pattern or keyword
    hint_text = Column(Text, nullable=False)
    
    # Priority for when multiple hints could apply
    priority = Column(Integer, default=5)  # 1-10, higher = more important
    
    # Enable/disable
    is_active = Column(Boolean, default=True)
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    def to_dict(self):
        return {
            "id": self.id,
            "hint_type": self.hint_type.value if self.hint_type else None,
            "trigger_pattern": self.trigger_pattern,
            "hint_text": self.hint_text,
            "priority": self.priority,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
