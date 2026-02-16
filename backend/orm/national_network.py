"""
National Moot Network Models — Phase 7 (Cross-Institution Tournament Engine)

Provides:
- Multi-institution tournament hosting
- Cross-institutional judging panels
- National-level team rankings
- Swiss and knockout tournament formats
- Deterministic pairing algorithms
- Tamper-evident audit ledger

Rules:
- All foreign keys use ON DELETE RESTRICT
- All tables are append-only (no updates to historical data)
- All timestamps are UTC
- All numeric uses Decimal (never float)
- Deterministic pairing (no random(), no Python hash())
- Judges cannot be from same institution as teams being judged
"""
import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey,
    Text, Numeric, Index, UniqueConstraint, Enum, Boolean,
    event
)
from sqlalchemy.orm import relationship

from backend.database import Base
from backend.orm.round_pairing import TournamentRound
from backend.core.db_types import UniversalJSON


# =============================================================================
# Tournament Format Enums
# =============================================================================

class TournamentFormat(str, enum.Enum):
    """
    Tournament pairing format.
    
    SWISS: Swiss-system tournament (multiple rounds, no elimination)
    KNOCKOUT: Single-elimination bracket
    HYBRID: Swiss followed by knockout for top teams
    """
    SWISS = "swiss"
    KNOCKOUT = "knockout"
    HYBRID = "hybrid"


class TournamentStatus(str, enum.Enum):
    """Tournament lifecycle status."""
    DRAFT = "draft"
    REGISTRATION_OPEN = "registration_open"
    REGISTRATION_CLOSED = "registration_closed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class MatchStatus(str, enum.Enum):
    """Status of a tournament match."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DISPUTED = "disputed"
    VOIDED = "voided"


class JudgeAssignmentRole(str, enum.Enum):
    """Role of a judge in a panel."""
    PRESIDENT = "president"
    MEMBER = "member"
    CLERK = "clerk"


class TournamentLedgerEventType(str, enum.Enum):
    """Types of events in the national tournament ledger."""
    TOURNAMENT_CREATED = "tournament_created"
    INSTITUTION_INVITED = "institution_invited"
    INSTITUTION_ACCEPTED = "institution_accepted"
    TEAM_REGISTERED = "team_registered"
    PAIRINGS_GENERATED = "pairings_generated"
    PANEL_ASSIGNED = "panel_assigned"
    MATCH_SUBMITTED = "match_submitted"
    MATCH_FINALIZED = "match_finalized"
    ROUND_FINALIZED = "round_finalized"
    RANKING_COMPUTED = "ranking_computed"
    TOURNAMENT_FINALIZED = "tournament_finalized"


# =============================================================================
# PART 1 — National Tournament
# =============================================================================

class NationalTournament(Base):
    """
    A cross-institution national moot tournament.
    
    Hosted by one institution but allows participation from multiple institutions.
    """
    __tablename__ = "national_tournaments"
    
    id = Column(Integer, primary_key=True)
    
    # Host institution (owns the tournament)
    host_institution_id = Column(
        Integer, 
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    # Tournament details
    name = Column(String(200), nullable=False)
    slug = Column(String(50), nullable=False, unique=True)
    description = Column(Text)
    
    # Tournament format
    format = Column(
        Enum(TournamentFormat, create_constraint=True),
        nullable=False,
        default=TournamentFormat.SWISS
    )
    
    # Tournament lifecycle
    status = Column(
        Enum(TournamentStatus, create_constraint=True),
        nullable=False,
        default=TournamentStatus.DRAFT
    )
    
    # Schedule
    registration_opens_at = Column(DateTime, nullable=False)
    registration_closes_at = Column(DateTime, nullable=False)
    tournament_starts_at = Column(DateTime, nullable=False)
    tournament_ends_at = Column(DateTime)
    
    # Configuration
    max_teams_per_institution = Column(Integer, nullable=False, default=2)
    total_rounds = Column(Integer, nullable=False, default=5)
    teams_advance_to_knockout = Column(Integer, nullable=False, default=8)
    
    # Scoring weights (stored as string, parsed to Decimal)
    preliminary_round_weight = Column(Numeric(5, 4), nullable=False, default=Decimal("1.0"))
    knockout_round_weight = Column(Numeric(5, 4), nullable=False, default=Decimal("1.5"))
    
    # Audit
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    host_institution = relationship("Institution", foreign_keys=[host_institution_id])
    creator = relationship("User", foreign_keys=[created_by])
    
    invited_institutions = relationship(
        "TournamentInstitution",
        back_populates="tournament",
        foreign_keys="TournamentInstitution.tournament_id"
    )
    
    teams = relationship(
        "TournamentTeam",
        back_populates="tournament",
        foreign_keys="TournamentTeam.tournament_id"
    )
    
    rounds = relationship(
        "TournamentRound",
        back_populates="tournament",
        foreign_keys="TournamentRound.tournament_id"
    )
    
    ledger_entries = relationship(
        "NationalLedgerEntry",
        back_populates="tournament",
        foreign_keys="NationalLedgerEntry.tournament_id"
    )
    
    __table_args__ = (
        Index("idx_tournaments_slug", "slug"),
        Index("idx_tournaments_host", "host_institution_id", "status"),
        Index("idx_tournaments_status", "status", "tournament_starts_at"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize tournament to dictionary."""
        return {
            "id": self.id,
            "host_institution_id": self.host_institution_id,
            "name": self.name,
            "slug": self.slug,
            "format": self.format.value,
            "status": self.status.value,
            "registration_opens_at": self.registration_opens_at.isoformat() if self.registration_opens_at else None,
            "registration_closes_at": self.registration_closes_at.isoformat() if self.registration_closes_at else None,
            "tournament_starts_at": self.tournament_starts_at.isoformat() if self.tournament_starts_at else None,
            "tournament_ends_at": self.tournament_ends_at.isoformat() if self.tournament_ends_at else None,
            "max_teams_per_institution": self.max_teams_per_institution,
            "total_rounds": self.total_rounds,
            "teams_advance_to_knockout": self.teams_advance_to_knockout,
            "preliminary_round_weight": str(self.preliminary_round_weight) if self.preliminary_round_weight else "1.0",
            "knockout_round_weight": str(self.knockout_round_weight) if self.knockout_round_weight else "1.5",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# PART 2 — Tournament Institution Invitations
# =============================================================================

class TournamentInstitution(Base):
    """
    Represents an institution invited to participate in a tournament.
    
    Tracks invitation status and acceptance.
    """
    __tablename__ = "tournament_institutions"
    
    id = Column(Integer, primary_key=True)
    
    tournament_id = Column(
        Integer,
        ForeignKey("national_tournaments.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    # Invitation status
    is_invited = Column(Boolean, nullable=False, default=True)
    invited_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    invited_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    
    # Acceptance
    is_accepted = Column(Boolean, nullable=False, default=False)
    accepted_at = Column(DateTime)
    accepted_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    
    # Number of teams allowed
    max_teams_allowed = Column(Integer, nullable=False, default=2)
    
    # Audit
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tournament = relationship(
        "NationalTournament",
        back_populates="invited_institutions",
        foreign_keys=[tournament_id]
    )
    
    institution = relationship("Institution", foreign_keys=[institution_id])
    
    __table_args__ = (
        UniqueConstraint("tournament_id", "institution_id", name="uq_tournament_institution"),
        Index("idx_tournament_institutions_tournament", "tournament_id"),
        Index("idx_tournament_institutions_institution", "institution_id"),
        Index("idx_tournament_institutions_accepted", "tournament_id", "is_accepted"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "tournament_id": self.tournament_id,
            "institution_id": self.institution_id,
            "is_invited": self.is_invited,
            "invited_at": self.invited_at.isoformat() if self.invited_at else None,
            "is_accepted": self.is_accepted,
            "accepted_at": self.accepted_at.isoformat() if self.accepted_at else None,
            "max_teams_allowed": self.max_teams_allowed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# PART 3 — Tournament Teams
# =============================================================================

class TournamentTeam(Base):
    """
    A team registered for a tournament.
    
    Links to existing participants from the institution.
    """
    __tablename__ = "tournament_teams"
    
    id = Column(Integer, primary_key=True)
    
    tournament_id = Column(
        Integer,
        ForeignKey("national_tournaments.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    # Team identity (may link to existing participants)
    team_name = Column(String(200), nullable=False)
    
    # Team members (JSON array of participant IDs/names)
    members_json = Column(Text)
    
    # Seeding/initial rank
    seed_number = Column(Integer)
    
    # Competition stats (updated after each round)
    wins = Column(Integer, nullable=False, default=0)
    losses = Column(Integer, nullable=False, default=0)
    draws = Column(Integer, nullable=False, default=0)
    total_score = Column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    is_eliminated = Column(Boolean, nullable=False, default=False)
    
    # Knockout bracket position (if applicable)
    bracket_position = Column(Integer)
    
    # Audit
    registered_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    registered_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    tournament = relationship(
        "NationalTournament",
        back_populates="teams",
        foreign_keys=[tournament_id]
    )
    
    institution = relationship("Institution", foreign_keys=[institution_id])
    
    matches_as_petitioner = relationship(
        "TournamentMatch",
        back_populates="petitioner_team",
        foreign_keys="TournamentMatch.petitioner_team_id"
    )
    
    matches_as_respondent = relationship(
        "TournamentMatch",
        back_populates="respondent_team",
        foreign_keys="TournamentMatch.respondent_team_id"
    )
    
    __table_args__ = (
        UniqueConstraint("tournament_id", "team_name", name="uq_tournament_team_name"),
        Index("idx_tournament_teams_tournament", "tournament_id", "is_active"),
        Index("idx_tournament_teams_institution", "institution_id"),
        Index("idx_tournament_teams_ranking", "tournament_id", "total_score"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "tournament_id": self.tournament_id,
            "institution_id": self.institution_id,
            "team_name": self.team_name,
            "members_json": self.members_json,
            "seed_number": self.seed_number,
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
            "total_score": str(self.total_score) if self.total_score else "0",
            "is_active": self.is_active,
            "is_eliminated": self.is_eliminated,
            "bracket_position": self.bracket_position,
            "registered_at": self.registered_at.isoformat() if self.registered_at else None,
        }


# =============================================================================
# PART 4 — Tournament Rounds
# =============================================================================

# TournamentRound is defined in backend.orm.round_pairing.py
# to avoid table name conflicts


# =============================================================================
# PART 5 — Tournament Matches
# =============================================================================

class TournamentMatch(Base):
    """
    A single match between two teams.
    
    Links to a judging panel and contains match results.
    """
    __tablename__ = "tournament_matches"
    
    id = Column(Integer, primary_key=True)
    
    round_id = Column(
        Integer,
        ForeignKey("tournament_rounds.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    tournament_id = Column(
        Integer,
        ForeignKey("national_tournaments.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    # Teams
    petitioner_team_id = Column(
        Integer,
        ForeignKey("tournament_teams.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    respondent_team_id = Column(
        Integer,
        ForeignKey("tournament_teams.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    # Winner (null if draw or not completed)
    winner_team_id = Column(
        Integer,
        ForeignKey("tournament_teams.id", ondelete="RESTRICT")
    )
    
    is_draw = Column(Boolean, nullable=False, default=False)
    
    # Scores (only stored for completed matches)
    petitioner_score = Column(Numeric(10, 4))
    respondent_score = Column(Numeric(10, 4))
    
    # Panel assignment
    panel_id = Column(
        Integer,
        ForeignKey("cross_institution_panels.id", ondelete="RESTRICT")
    )
    
    # Match status
    status = Column(
        Enum(MatchStatus, create_constraint=True),
        nullable=False,
        default=MatchStatus.PENDING
    )
    
    # Scheduling
    scheduled_at = Column(DateTime)
    venue = Column(String(200))
    
    # Results submission (idempotency key)
    submission_idempotency_key = Column(String(64), unique=True)
    submitted_at = Column(DateTime)
    submitted_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    
    # Finalization
    finalized_at = Column(DateTime)
    finalized_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    
    # Notes
    notes = Column(Text)
    
    # Audit
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    round = relationship(
        "TournamentRound",
        foreign_keys=[round_id]
    )
    
    tournament = relationship("NationalTournament", foreign_keys=[tournament_id])
    
    petitioner_team = relationship(
        "TournamentTeam",
        back_populates="matches_as_petitioner",
        foreign_keys=[petitioner_team_id]
    )
    
    respondent_team = relationship(
        "TournamentTeam",
        back_populates="matches_as_respondent",
        foreign_keys=[respondent_team_id]
    )
    
    winner_team = relationship("TournamentTeam", foreign_keys=[winner_team_id])
    
    panel = relationship("CrossInstitutionPanel", foreign_keys=[panel_id])
    
    evaluations = relationship(
        "TournamentEvaluation",
        back_populates="match",
        foreign_keys="TournamentEvaluation.match_id"
    )
    
    __table_args__ = (
        Index("idx_tournament_matches_round", "round_id", "status"),
        Index("idx_tournament_matches_tournament", "tournament_id", "status"),
        Index("idx_tournament_matches_petitioner", "petitioner_team_id"),
        Index("idx_tournament_matches_respondent", "respondent_team_id"),
        Index("idx_tournament_matches_panel", "panel_id"),
        Index("idx_tournament_matches_winner", "winner_team_id"),
        Index("idx_tournament_matches_idempotency", "submission_idempotency_key"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "round_id": self.round_id,
            "tournament_id": self.tournament_id,
            "petitioner_team_id": self.petitioner_team_id,
            "respondent_team_id": self.respondent_team_id,
            "winner_team_id": self.winner_team_id,
            "is_draw": self.is_draw,
            "petitioner_score": str(self.petitioner_score) if self.petitioner_score else None,
            "respondent_score": str(self.respondent_score) if self.respondent_score else None,
            "panel_id": self.panel_id,
            "status": self.status.value if self.status else None,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "venue": self.venue,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "finalized_at": self.finalized_at.isoformat() if self.finalized_at else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# PART 6 — Cross-Institution Judge Panels
# =============================================================================

class CrossInstitutionPanel(Base):
    """
    A judging panel composed of judges from various institutions.
    
    Ensures no judge is from the same institution as teams being judged.
    """
    __tablename__ = "cross_institution_panels"
    
    id = Column(Integer, primary_key=True)
    
    tournament_id = Column(
        Integer,
        ForeignKey("national_tournaments.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    panel_name = Column(String(100), nullable=False)
    
    # Panel composition constraints
    require_mixed_institutions = Column(Boolean, nullable=False, default=True)
    min_institutions_represented = Column(Integer, nullable=False, default=2)
    
    # Audit
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    tournament = relationship("NationalTournament", foreign_keys=[tournament_id])
    
    judges = relationship(
        "PanelJudge",
        back_populates="panel",
        foreign_keys="PanelJudge.panel_id"
    )
    
    __table_args__ = (
        Index("idx_cross_institution_panels_tournament", "tournament_id"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "tournament_id": self.tournament_id,
            "panel_name": self.panel_name,
            "require_mixed_institutions": self.require_mixed_institutions,
            "min_institutions_represented": self.min_institutions_represented,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PanelJudge(Base):
    """
    A judge assigned to a panel.
    
    Tracks the judge's institution and role in the panel.
    """
    __tablename__ = "panel_judges"
    
    id = Column(Integer, primary_key=True)
    
    panel_id = Column(
        Integer,
        ForeignKey("cross_institution_panels.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    role = Column(
        Enum(JudgeAssignmentRole, create_constraint=True),
        nullable=False,
        default=JudgeAssignmentRole.MEMBER
    )
    
    # Availability/assignment tracking
    is_available = Column(Boolean, nullable=False, default=True)
    assigned_matches_count = Column(Integer, nullable=False, default=0)
    
    # Audit
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    panel = relationship(
        "CrossInstitutionPanel",
        back_populates="judges",
        foreign_keys=[panel_id]
    )
    
    user = relationship("User", foreign_keys=[user_id])
    institution = relationship("Institution", foreign_keys=[institution_id])
    
    __table_args__ = (
        UniqueConstraint("panel_id", "user_id", name="uq_panel_judge"),
        Index("idx_panel_judges_panel", "panel_id", "role"),
        Index("idx_panel_judges_user", "user_id"),
        Index("idx_panel_judges_institution", "institution_id"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "panel_id": self.panel_id,
            "user_id": self.user_id,
            "institution_id": self.institution_id,
            "role": self.role.value if self.role else None,
            "is_available": self.is_available,
            "assigned_matches_count": self.assigned_matches_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# PART 7 — Tournament Evaluations
# =============================================================================

class TournamentEvaluation(Base):
    """
    An evaluation/score given by a judge for a match.
    
    Links to the parent AI evaluation system or is standalone.
    """
    __tablename__ = "tournament_evaluations"
    
    id = Column(Integer, primary_key=True)
    
    match_id = Column(
        Integer,
        ForeignKey("tournament_matches.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    tournament_id = Column(
        Integer,
        ForeignKey("national_tournaments.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    # Evaluator
    judge_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    judge_institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    # Team being evaluated
    team_id = Column(
        Integer,
        ForeignKey("tournament_teams.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    # Side (petitioner/respondent)
    side = Column(String(20), nullable=False)
    
    # Scores (using components for transparency)
    legal_argument_score = Column(Numeric(5, 4), nullable=False)
    presentation_score = Column(Numeric(5, 4), nullable=False)
    rebuttal_score = Column(Numeric(5, 4), nullable=False)
    procedural_compliance_score = Column(Numeric(5, 4), nullable=False)
    
    # Composite total (computed deterministically)
    total_score = Column(Numeric(10, 4), nullable=False)
    
    # Weighted contribution (for tournament ranking)
    weighted_contribution = Column(Numeric(10, 4), nullable=False)
    
    # Optional link to AI evaluation
    ai_evaluation_id = Column(
        Integer,
        ForeignKey("ai_evaluations.id", ondelete="RESTRICT")
    )
    
    # Comments/feedback
    comments = Column(Text)
    
    # Audit
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    match = relationship(
        "TournamentMatch",
        back_populates="evaluations",
        foreign_keys=[match_id]
    )
    
    tournament = relationship("NationalTournament", foreign_keys=[tournament_id])
    judge = relationship("User", foreign_keys=[judge_id])
    judge_institution = relationship("Institution", foreign_keys=[judge_institution_id])
    team = relationship("TournamentTeam", foreign_keys=[team_id])
    ai_evaluation = relationship("AIEvaluation", foreign_keys=[ai_evaluation_id])
    
    __table_args__ = (
        Index("idx_tournament_evaluations_match", "match_id", "team_id"),
        Index("idx_tournament_evaluations_judge", "judge_id"),
        Index("idx_tournament_evaluations_team", "team_id"),
        Index("idx_tournament_evaluations_tournament", "tournament_id"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "match_id": self.match_id,
            "tournament_id": self.tournament_id,
            "judge_id": self.judge_id,
            "judge_institution_id": self.judge_institution_id,
            "team_id": self.team_id,
            "side": self.side,
            "legal_argument_score": str(self.legal_argument_score) if self.legal_argument_score else None,
            "presentation_score": str(self.presentation_score) if self.presentation_score else None,
            "rebuttal_score": str(self.rebuttal_score) if self.rebuttal_score else None,
            "procedural_compliance_score": str(self.procedural_compliance_score) if self.procedural_compliance_score else None,
            "total_score": str(self.total_score) if self.total_score else None,
            "weighted_contribution": str(self.weighted_contribution) if self.weighted_contribution else None,
            "ai_evaluation_id": self.ai_evaluation_id,
            "comments": self.comments,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# PART 8 — National Team Rankings (Immutable Snapshots)
# =============================================================================

class NationalTeamRanking(Base):
    """
    An immutable snapshot of tournament rankings at a point in time.
    
    Similar to SessionLeaderboardSnapshot but for cross-institution tournaments.
    """
    __tablename__ = "national_team_rankings"
    
    id = Column(Integer, primary_key=True)
    
    tournament_id = Column(
        Integer,
        ForeignKey("national_tournaments.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    round_id = Column(
        Integer,
        ForeignKey("tournament_rounds.id", ondelete="RESTRICT"),
        nullable=True  # Null for final tournament ranking
    )
    
    # Snapshot state
    is_final = Column(Boolean, nullable=False, default=False)  # True for tournament final
    
    # Computed at
    computed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    computed_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    # Team data (JSON for flexibility)
    # Contains: team_id, institution_id, rank, wins, losses, total_score, tiebreaker
    rankings_json = Column(Text, nullable=False)
    
    # Checksum for integrity
    checksum = Column(String(64), nullable=False)
    
    # Finalization
    is_finalized = Column(Boolean, nullable=False, default=False)
    finalized_at = Column(DateTime)
    finalized_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    
    # Audit
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    tournament = relationship("NationalTournament", foreign_keys=[tournament_id])
    round = relationship("TournamentRound", foreign_keys=[round_id])
    
    __table_args__ = (
        Index("idx_national_rankings_tournament", "tournament_id", "is_final"),
        Index("idx_national_rankings_round", "round_id"),
        Index("idx_national_rankings_finalized", "tournament_id", "is_finalized"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "tournament_id": self.tournament_id,
            "round_id": self.round_id,
            "is_final": self.is_final,
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
            "rankings_json": self.rankings_json,
            "checksum": self.checksum,
            "is_finalized": self.is_finalized,
            "finalized_at": self.finalized_at.isoformat() if self.finalized_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# PART 9 — National Ledger (Tamper-Evident Audit Trail)
# =============================================================================

class NationalLedgerEntry(Base):
    """
    Append-only ledger entry for tournament events.
    
    Blockchain-like hash chaining ensures tamper detection.
    """
    __tablename__ = "national_ledger_entries"
    
    id = Column(Integer, primary_key=True)
    
    tournament_id = Column(
        Integer,
        ForeignKey("national_tournaments.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    # Event details
    event_type = Column(
        Enum(TournamentLedgerEventType, create_constraint=True),
        nullable=False
    )
    
    # Entity being tracked
    entity_type = Column(String(30), nullable=False)
    entity_id = Column(Integer, nullable=False)
    
    # Event data (JSON)
    event_data_json = Column(Text)
    
    # Hash chain
    event_hash = Column(String(64), nullable=False, unique=True)
    previous_hash = Column(String(64), nullable=False)
    
    # Actor
    actor_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    
    # Institution scope for isolation
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    # Timestamp
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    tournament = relationship(
        "NationalTournament",
        back_populates="ledger_entries",
        foreign_keys=[tournament_id]
    )
    
    __table_args__ = (
        Index("idx_national_ledger_tournament", "tournament_id", "created_at"),
        Index("idx_national_ledger_entity", "entity_type", "entity_id"),
        Index("idx_national_ledger_event_type", "event_type"),
        Index("idx_national_ledger_previous_hash", "previous_hash"),
        Index("idx_national_ledger_institution", "institution_id"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "tournament_id": self.tournament_id,
            "event_type": self.event_type.value if self.event_type else None,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "event_data_json": self.event_data_json,
            "event_hash": self.event_hash,
            "previous_hash": self.previous_hash,
            "actor_user_id": self.actor_user_id,
            "institution_id": self.institution_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# Append-Only Guards
# =============================================================================

@event.listens_for(NationalLedgerEntry, 'before_update')
def prevent_ledger_update(mapper, connection, target):
    """Prevent updates to ledger entries (append-only)."""
    raise Exception("NationalLedgerEntry is append-only. Updates are prohibited.")


@event.listens_for(NationalLedgerEntry, 'before_delete')
def prevent_ledger_delete(mapper, connection, target):
    """Prevent deletions from ledger (append-only)."""
    raise Exception("NationalLedgerEntry is append-only. Deletions are prohibited.")


@event.listens_for(NationalTeamRanking, 'before_update')
def prevent_ranking_update(mapper, connection, target):
    """Prevent updates to finalized rankings."""
    if target.is_finalized:
        raise Exception("Finalized NationalTeamRanking cannot be modified.")


@event.listens_for(NationalTeamRanking, 'before_delete')
def prevent_ranking_delete(mapper, connection, target):
    """Prevent deletions of rankings."""
    raise Exception("NationalTeamRanking is append-only. Deletions are prohibited.")
