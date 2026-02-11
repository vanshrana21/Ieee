"""
backend/orm/user_skill_progress.py
Phase 5: Analytics Dashboards - Skill Progress Model
Isolated from existing models - NEW FILE
"""
from sqlalchemy import Column, Integer, Float, DateTime, Date, ForeignKey, Boolean, Enum as SQLEnum, func, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import date
import enum
from backend.orm.base import Base


class SkillType(str, enum.Enum):
    """Skill categories for analytics tracking"""
    CITATION_ACCURACY = "citation_accuracy"
    ETIQUETTE_COMPLIANCE = "etiquette_compliance"
    LEGAL_REASONING = "legal_reasoning"
    DOCTRINE_MASTERY = "doctrine_mastery"
    TIME_MANAGEMENT = "time_management"


class UserSkillProgress(Base):
    """
    Phase 5: User skill progress tracking for learning analytics.
    Tracks individual skill scores over time with percentile rankings.
    """
    __tablename__ = "user_skill_progress"
    
    __table_args__ = (
        UniqueConstraint('user_id', 'skill_type', 'measurement_date', name='uq_user_skill_date'),
        Index('idx_user_skill_date', 'user_id', 'measurement_date'),
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Skill tracking
    skill_type = Column(SQLEnum(SkillType), nullable=False)
    measurement_date = Column(Date, nullable=False, default=date.today)
    score_value = Column(Float, nullable=False)  # 0.0-5.0
    percentile_rank = Column(Integer, nullable=False)  # 0-100
    improvement_delta = Column(Float, nullable=True)  # Change from previous
    weakness_flag = Column(Boolean, default=False)  # Flags consistent errors
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    user = relationship("User", lazy="selectin")
    
    def __init__(self, user_id: int, skill_type: SkillType, score_value: float, 
                 percentile_rank: int = 0, improvement_delta: float = None,
                 weakness_flag: bool = False, measurement_date: date = None):
        self.user_id = user_id
        self.skill_type = skill_type
        self.score_value = score_value
        self.percentile_rank = percentile_rank
        self.improvement_delta = improvement_delta
        self.weakness_flag = weakness_flag
        self.measurement_date = measurement_date or date.today()
    
    def to_dict(self, include_history: bool = False):
        """Convert to dictionary for API responses"""
        result = {
            "id": self.id,
            "user_id": self.user_id,
            "skill_type": self.skill_type.value,
            "measurement_date": self.measurement_date.isoformat(),
            "score_value": self.score_value,
            "percentile_rank": self.percentile_rank,
            "improvement_delta": self.improvement_delta,
            "weakness_flag": self.weakness_flag,
            "created_at": self.created_at.isoformat()
        }
        
        if include_history and self.user:
            result["user_name"] = self.user.name
        
        return result
    
    def calculate_improvement(self, previous_score: float):
        """Calculate improvement from previous measurement"""
        self.improvement_delta = self.score_value - previous_score
        return self.improvement_delta
    
    def mark_weakness(self, threshold: float = 2.5):
        """Mark as weakness if score consistently below threshold"""
        self.weakness_flag = self.score_value < threshold
        return self.weakness_flag


def get_skill_type_display(skill_type: SkillType) -> str:
    """Get human-readable display name for skill type"""
    display_names = {
        SkillType.CITATION_ACCURACY: "Citation Accuracy",
        SkillType.ETIQUETTE_COMPLIANCE: "Etiquette Compliance",
        SkillType.LEGAL_REASONING: "Legal Reasoning",
        SkillType.DOCTRINE_MASTERY: "Doctrine Mastery",
        SkillType.TIME_MANAGEMENT: "Time Management"
    }
    return display_names.get(skill_type, skill_type.value.replace("_", " ").title())
