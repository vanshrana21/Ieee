"""
Phase 15 — AI Judge Intelligence Layer ORM Models

This module defines the database models for AI judge evaluations.
All models are strictly independent from Phase 14 tables.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional, List

from sqlalchemy import (
    Column, String, DateTime, Float, Integer, Text,
    ForeignKey, Index, CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID

from backend.database import Base
from backend.core.db_types import UniversalJSON


class AIMatchEvaluation(Base):
    """
    Stores official AI evaluations for frozen matches.
    Each evaluation is linked to a snapshot hash for verification.
    """
    __tablename__ = "ai_match_evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tournament_matches.id", ondelete="CASCADE"),
        nullable=False
    )

    # Hashes for verification
    snapshot_hash = Column(String(64), nullable=False, index=True)
    evaluation_hash = Column(String(64), nullable=False, index=True)

    # Model information
    model_name = Column(String(100), nullable=False)
    mode = Column(String(20), nullable=False, default="official")  # shadow or official

    # Scores as JSON for flexibility
    petitioner_score_json = Column(UniversalJSON, nullable=True)
    respondent_score_json = Column(UniversalJSON, nullable=True)

    # Winner determination
    winner = Column(String(20), nullable=True)  # PETITIONER or RESPONDENT

    # Reasoning and confidence
    reasoning_summary = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)

    # Status tracking
    evaluation_status = Column(
        String(20),
        nullable=False,
        default="completed"
    )  # completed, pending_retry, failed

    # Token usage for cost tracking
    token_usage = Column(Integer, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        # Performance indexes
        Index("idx_ai_match_eval_match", "match_id"),
        Index("idx_ai_snapshot_hash", "snapshot_hash"),
        Index("idx_ai_eval_status", "evaluation_status"),
        Index("idx_ai_created_at", "created_at"),

        # Constraints
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_confidence_range"
        ),
        CheckConstraint(
            "mode IN ('shadow', 'official')",
            name="ck_mode_valid"
        ),
        CheckConstraint(
            "evaluation_status IN ('completed', 'pending_retry', 'failed')",
            name="ck_eval_status_valid"
        ),
        CheckConstraint(
            "winner IS NULL OR winner IN ('PETITIONER', 'RESPONDENT')",
            name="ck_winner_valid"
        ),
        UniqueConstraint(
            'match_id', 'snapshot_hash', 'mode',
            name='uq_match_snapshot_mode'
        ),
    )

    def compute_evaluation_hash(
        self,
        snapshot_hash: str,
        model_name: str,
        response_json: Dict[str, Any]
    ) -> str:
        """
        Compute deterministic evaluation hash.
        Formula: sha256(snapshot_hash + model_name + sorted_json_response)
        """
        import hashlib
        import json

        # Ensure deterministic JSON serialization
        response_str = json.dumps(response_json, sort_keys=True, separators=(',', ':'))

        # Combine components
        hash_input = f"{snapshot_hash}:{model_name}:{response_str}"

        # Compute SHA256
        return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Convert evaluation to dictionary."""
        return {
            "id": str(self.id),
            "match_id": str(self.match_id),
            "snapshot_hash": self.snapshot_hash,
            "evaluation_hash": self.evaluation_hash,
            "model_name": self.model_name,
            "mode": self.mode,
            "petitioner_score": self.petitioner_score_json,
            "respondent_score": self.respondent_score_json,
            "winner": self.winner,
            "reasoning_summary": self.reasoning_summary,
            "confidence_score": self.confidence_score,
            "evaluation_status": self.evaluation_status,
            "token_usage": self.token_usage,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AIShadowScore(Base):
    """
    Stores provisional shadow scores during LIVE matches.
    These are temporary and auto-deleted when match is frozen.
    """
    __tablename__ = "ai_shadow_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tournament_matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    turn_id = Column(
        UUID(as_uuid=True),
        ForeignKey("match_speaker_turns.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    # Provisional scoring
    provisional_score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)

    # Scoring breakdown (simplified for shadow)
    legal_knowledge = Column(Float, nullable=True)
    application_of_law = Column(Float, nullable=True)
    structure_clarity = Column(Float, nullable=True)
    etiquette = Column(Float, nullable=True)

    # Heuristics used
    heuristic_version = Column(String(20), nullable=True, default="1.0")
    used_llm = Column(String(100), nullable=True)  # null if pure heuristic

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)  # Auto-expire after freeze

    __table_args__ = (
        # Performance indexes
        Index("idx_shadow_match_turn", "match_id", "turn_id"),
        Index("idx_shadow_created", "created_at"),

        # Constraints
        CheckConstraint(
            "provisional_score >= 0 AND provisional_score <= 100",
            name="ck_provisional_score_range"
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_shadow_confidence_range"
        ),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert shadow score to dictionary."""
        return {
            "id": str(self.id),
            "match_id": str(self.match_id),
            "turn_id": str(self.turn_id) if self.turn_id else None,
            "provisional_score": self.provisional_score,
            "confidence": self.confidence,
            "legal_knowledge": self.legal_knowledge,
            "application_of_law": self.application_of_law,
            "structure_clarity": self.structure_clarity,
            "etiquette": self.etiquette,
            "heuristic_version": self.heuristic_version,
            "used_llm": self.used_llm,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AIEvaluationCache(Base):
    """
    Cache for AI evaluations to avoid redundant API calls.
    Keyed by snapshot hash for deterministic lookup.
    """
    __tablename__ = "ai_evaluation_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Cache key
    snapshot_hash = Column(String(64), nullable=False, unique=True, index=True)
    model_name = Column(String(100), nullable=False)

    # Cached result
    cached_response_json = Column(UniversalJSON, nullable=False)
    winner = Column(String(20), nullable=True)
    confidence_score = Column(Float, nullable=True)

    # Usage tracking
    hit_count = Column(Integer, default=1, nullable=False)
    last_accessed = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)  # TTL for cache entries

    __table_args__ = (
        Index("idx_cache_hash_model", "snapshot_hash", "model_name"),
        Index("idx_cache_expires", "expires_at"),
    )

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert cache entry to dictionary."""
        return {
            "id": str(self.id),
            "snapshot_hash": self.snapshot_hash,
            "model_name": self.model_name,
            "winner": self.winner,
            "confidence_score": self.confidence_score,
            "hit_count": self.hit_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_expired": self.is_expired(),
        }
