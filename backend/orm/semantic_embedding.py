"""
backend/orm/semantic_embedding.py
Phase 8: Semantic Embeddings Storage

DESIGN:
- Polymorphic entity linking (note, case, learn, practice)
- Stores vector embeddings as JSON (SQLite-compatible)
- Hash-based change detection (no duplicate embeddings)
- Future-ready for Postgres + pgvector

CRITICAL: This does NOT modify any existing tables
"""

from sqlalchemy import Column, Integer, String, Text, Index, JSON
from sqlalchemy.orm import relationship
from backend.orm.base import BaseModel
import hashlib


class SemanticEmbedding(BaseModel):
    """
    Stores vector embeddings for semantic search.
    
    Architecture:
    - One embedding per entity (identified by entity_type + entity_id)
    - Embeddings stored as JSON array (SQLite-compatible)
    - text_hash enables change detection (regenerate only if text changed)
    - No foreign keys (decoupled from core entities)
    
    Supported Entities:
    - note (smart_notes)
    - case (case_content)
    - learn (learn_content)
    - practice (practice_question)
    
    Example:
    - entity_type='case', entity_id=42 → embedding for Kesavananda Bharati
    - entity_type='note', entity_id=15 → embedding for user's note
    
    Postgres Migration Path:
    - Change 'embedding' column from JSON to VECTOR type
    - Add GIN index on vector column
    - Use pgvector extension for similarity search
    """
    
    __tablename__ = "semantic_embeddings"
    
    # Entity Reference (polymorphic)
    entity_type = Column(
        String(20),
        nullable=False,
        index=True,
        comment="Entity type: note, case, learn, practice"
    )
    
    entity_id = Column(
        Integer,
        nullable=False,
        index=True,
        comment="ID of the entity"
    )
    
    # Embedding Data
    embedding = Column(
        JSON,
        nullable=False,
        comment="Vector embedding as JSON array (e.g., [0.1, 0.2, ...])"
    )
    
    # Change Detection
    text_hash = Column(
        String(64),
        nullable=False,
        index=True,
        comment="SHA256 hash of source text (for change detection)"
    )
    
    # Metadata
    embedding_model = Column(
        String(50),
        nullable=False,
        default="gemini-embedding-001",
        comment="Model used to generate embedding"
    )
    
    dimension = Column(
        Integer,
        nullable=False,
        default=768,
        comment="Embedding vector dimension"
    )
    
    # Database Constraints
    __table_args__ = (
        # Unique constraint: one embedding per entity
        Index(
            'uq_embedding_entity',
            'entity_type',
            'entity_id',
            unique=True
        ),
        # Index for text hash lookup (deduplication)
        Index(
            'ix_embedding_text_hash',
            'text_hash'
        ),
    )
    
    def __repr__(self):
        return f"<SemanticEmbedding(entity={self.entity_type}:{self.entity_id}, dim={self.dimension})>"
    
    def to_dict(self):
        """Convert to API response format"""
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "embedding_model": self.embedding_model,
            "dimension": self.dimension,
            "text_hash": self.text_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    @staticmethod
    def compute_text_hash(text: str) -> str:
        """
        Compute SHA256 hash of text for change detection.
        
        Args:
            text: Source text
        
        Returns:
            64-character hex hash
        """
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
