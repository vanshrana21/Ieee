"""
backend/orm/cohort_benchmark.py
Phase 5: Analytics Dashboards - Cohort Benchmark Model
Isolated from existing models - NEW FILE
"""
from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, Enum as SQLEnum, func, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.orm.base import Base
from backend.orm.user_skill_progress import SkillType


class CohortBenchmark(Base):
    """
    Phase 5: Pre-calculated cohort benchmarks for fast dashboard rendering.
    Stores anonymized percentile data for skill comparisons.
    """
    __tablename__ = "cohort_benchmarks"
    
    __table_args__ = (
        UniqueConstraint('institution_id', 'course_id', 'semester', 'skill_type', 'measurement_period',
                        name='uq_cohort_benchmark'),
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Scope fields (NULL = all)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True)
    semester = Column(String(20), nullable=True)  # e.g., "Semester 5"
    
    # Benchmark data
    skill_type = Column(SQLEnum(SkillType), nullable=False)
    percentile_25 = Column(Float, nullable=False)  # 25th percentile
    percentile_50 = Column(Float, nullable=False)  # Median
    percentile_75 = Column(Float, nullable=False)  # 75th percentile
    mean_score = Column(Float, nullable=False)
    sample_size = Column(Integer, nullable=False)
    measurement_period = Column(String(50), nullable=False)  # "Last 30 days", "Current semester"
    
    # Metadata
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    institution = relationship("Institution", lazy="selectin")
    course = relationship("Course", lazy="selectin")
    
    def __init__(self, skill_type: SkillType, percentile_25: float, percentile_50: float,
                 percentile_75: float, mean_score: float, sample_size: int,
                 measurement_period: str, institution_id: int = None,
                 course_id: int = None, semester: str = None):
        self.skill_type = skill_type
        self.percentile_25 = percentile_25
        self.percentile_50 = percentile_50
        self.percentile_75 = percentile_75
        self.mean_score = mean_score
        self.sample_size = sample_size
        self.measurement_period = measurement_period
        self.institution_id = institution_id
        self.course_id = course_id
        self.semester = semester
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "institution_id": self.institution_id,
            "institution_name": self.institution.name if self.institution else "All Institutions",
            "course_id": self.course_id,
            "course_name": self.course.name if self.course else "All Courses",
            "semester": self.semester or "All Semesters",
            "skill_type": self.skill_type.value,
            "percentile_25": self.percentile_25,
            "percentile_50": self.percentile_50,
            "percentile_75": self.percentile_75,
            "mean_score": self.mean_score,
            "sample_size": self.sample_size,
            "measurement_period": self.measurement_period,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    def get_percentile_for_score(self, score: float) -> int:
        """
        Estimate percentile rank for a given score using linear interpolation.
        Returns 0-100 integer percentile.
        """
        if score <= self.percentile_25:
            return int((score / self.percentile_25) * 25) if self.percentile_25 > 0 else 0
        elif score <= self.percentile_50:
            return 25 + int(((score - self.percentile_25) / (self.percentile_50 - self.percentile_25)) * 25)
        elif score <= self.percentile_75:
            return 50 + int(((score - self.percentile_50) / (self.percentile_75 - self.percentile_50)) * 25)
        else:
            above_75 = score - self.percentile_75
            range_above = 5.0 - self.percentile_75
            return 75 + int((above_75 / range_above) * 25) if range_above > 0 else 100
    
    def is_valid_sample(self, min_sample_size: int = 5) -> bool:
        """Check if benchmark has valid sample size for reporting"""
        return self.sample_size >= min_sample_size


class AnalyticsCache(Base):
    """
    Phase 5: Simple cache for expensive analytics queries.
    Stores pre-computed results with TTL.
    """
    __tablename__ = "analytics_cache"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_key = Column(String(255), nullable=False, unique=True)
    cache_data = Column(String(4000), nullable=False)  # JSON string
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now())
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired"""
        return datetime.utcnow() > self.expires_at
