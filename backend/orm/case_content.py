"""
backend/orm/case_content.py
CaseContent model - Legal case database items

Items for CASES modules:
- Landmark judgments
- Case summaries
- Ratio decidendi
- Exam-relevant cases

Structure: Subject → ContentModule (CASES) → CaseContent items
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.orm import relationship
from enum import Enum
from backend.orm.base import BaseModel


class ExamImportance(str, Enum):
    """
    Exam relevance rating for cases.
    
    - HIGH: Must-know landmark cases
    - MEDIUM: Important supporting cases
    - LOW: Additional reference cases
    """
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CaseContent(BaseModel):
    """
    CaseContent represents a single case law entry in CASES module.
    
    Examples:
    - "Carlill v. Carbolic Smoke Ball Co. (1893)"
    - "Mohori Bibee v. Dharmodas Ghose (1903)"
    - "Balfour v. Balfour (1919)"
    
    Fields:
    - id: Primary key
    - module_id: Parent content module (FK)
    - case_name: Full case name with parties
    - citation: Legal citation (e.g., "(1893) 1 QB 256")
    - year: Year of judgment
    - court: Court that delivered judgment
    - facts: Summary of case facts
    - issue: Legal question/issue
    - judgment: Court's decision
    - ratio: Ratio decidendi (legal principle)
    - exam_importance: Relevance for exams
    - tags: Comma-separated tags (e.g., "offer,acceptance,unilateral")
    - created_at: When case was added
    - updated_at: Last modification time
    
    Relationships:
    - module: Parent ContentModule (type must be CASES)
    
    Usage:
    - Frontend can filter by exam_importance
    - Tags enable topic-based search
    - Ratio is the most important field for learning
    """
    __tablename__ = "case_content"
    
    # Foreign Keys
    module_id = Column(
        Integer,
        ForeignKey("content_modules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to content_modules table"
    )
    
    # Case Identification
    case_name = Column(
        String(300),
        nullable=False,
        index=True,
        comment="Full case name (e.g., 'Carlill v. Carbolic Smoke Ball Co.')"
    )
    
    citation = Column(
        String(200),
        nullable=True,
        comment="Legal citation (e.g., '(1893) 1 QB 256')"
    )
    
    year = Column(
        Integer,
        nullable=False,
        index=True,
        comment="Year of judgment"
    )
    
    court = Column(
        String(200),
        nullable=True,
        comment="Court that delivered judgment (e.g., 'Supreme Court of India')"
    )
    
    # Case Content
    facts = Column(
        Text,
        nullable=False,
        comment="Summary of case facts"
    )
    
    issue = Column(
        Text,
        nullable=False,
        comment="Legal question/issue before the court"
    )
    
    judgment = Column(
        Text,
        nullable=False,
        comment="Court's decision and reasoning"
    )
    
    ratio = Column(
        Text,
        nullable=False,
        comment="Ratio decidendi - legal principle established"
    )
    
    # Metadata
    exam_importance = Column(
        SQLEnum(ExamImportance),
        nullable=False,
        default=ExamImportance.MEDIUM,
        index=True,
        comment="Exam relevance rating"
    )
    
    tags = Column(
        String(500),
        nullable=True,
        comment="Comma-separated tags for filtering (e.g., 'offer,acceptance')"
    )
    
    # Relationships
    module = relationship(
        "ContentModule",
        back_populates="case_items",
        lazy="joined"
    )
    
    # Database Constraints
    __table_args__ = (
        # Composite index for year-based queries
        Index(
            "ix_module_year_importance",
            "module_id",
            "year",
            "exam_importance"
        ),
        # Index for case name search
        Index(
            "ix_case_name",
            "case_name"
        ),
    )
    
    def __repr__(self):
        return (
            f"<CaseContent("
            f"id={self.id}, "
            f"case_name='{self.case_name[:50]}', "
            f"year={self.year})>"
        )
    
    def to_dict(self, include_full_content: bool = True):
        """
        Convert model to dictionary for API responses.
        
        Args:
            include_full_content: If False, excludes lengthy fields (for list views)
        """
        data = {
            "id": self.id,
            "module_id": self.module_id,
            "case_name": self.case_name,
            "citation": self.citation,
            "year": self.year,
            "court": self.court,
            "exam_importance": self.exam_importance.value if self.exam_importance else None,
            "tags": self.tags.split(",") if self.tags else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_full_content:
            data.update({
                "facts": self.facts,
                "issue": self.issue,
                "judgment": self.judgment,
                "ratio": self.ratio,
            })
        
        return data
    
    def get_tag_list(self) -> list[str]:
        """Parse comma-separated tags into list"""
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]