"""
backend/models/base.py
Base model for legacy models - use backend.orm.base.Base instead
"""
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime

# Use the canonical Base from orm.base
from backend.orm.base import Base


class TimestampMixin:
    """
    Mixin to add timestamp fields to models.
    
    Provides:
    - created_at: Timestamp when record was created
    - updated_at: Timestamp when record was last updated (auto-updates)
    """
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )
    
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )


class BaseModel(Base, TimestampMixin):
    """
    Abstract base model with id and timestamps.
    
    All models should inherit from this instead of Base directly.
    
    Provides:
    - id: Primary key (auto-increment)
    - created_at: Creation timestamp
    - updated_at: Last update timestamp
    """
    __abstract__ = True
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    def __repr__(self):
        """String representation of model"""
        return f"<{self.__class__.__name__}(id={self.id})>"