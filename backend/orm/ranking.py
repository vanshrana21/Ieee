"""
backend/orm/ranking.py
Phase 5E: Ranking, leaderboard, and winner selection system
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum as PyEnum
from backend.orm.base import Base


class RankingType(str, PyEnum):
    """Types of rankings"""
    MEMORIAL = "memorial"           # Written submissions only
    ORAL = "oral"                   # Oral rounds only
    OVERALL = "overall"             # Combined memorial + oral
    ROUND_SPECIFIC = "round"        # Specific round (preliminary, quarterfinal, etc.)


class RankStatus(str, PyEnum):
    """Ranking status"""
    DRAFT = "draft"                 # Being computed
    PUBLISHED = "published"         # Visible to all
    FINAL = "final"                 # Competition complete, rankings frozen


class TeamRanking(Base):
    """
    Computed ranking for a team in a competition.
    Phase 5E: Stores calculated rank based on aggregated scores.
    """
    __tablename__ = "team_rankings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution and Competition scoping (Phase 5B)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    round_id = Column(Integer, ForeignKey("competition_rounds.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # What is being ranked
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    ranking_type = Column(SQLEnum(RankingType), default=RankingType.OVERALL, nullable=False)
    
    # Ranking position (Phase 5E)
    rank = Column(Integer, nullable=False, index=True)  # 1 = first place
    rank_display = Column(String(10), nullable=True)  # "1st", "2nd", "3rd", etc.
    
    # Scores (Phase 5E: Aggregated from judge scores)
    total_score = Column(Float, nullable=True)  # Sum or average of all criteria
    raw_score = Column(Float, nullable=True)  # Before normalization
    normalized_score = Column(Float, nullable=True)  # 0-100 scale
    
    # Individual criterion aggregates (Phase 5E)
    issue_framing_avg = Column(Float, nullable=True)
    legal_reasoning_avg = Column(Float, nullable=True)
    use_of_authority_avg = Column(Float, nullable=True)
    structure_clarity_avg = Column(Float, nullable=True)
    oral_advocacy_avg = Column(Float, nullable=True)
    responsiveness_avg = Column(Float, nullable=True)
    
    # Tie-break info (Phase 5E)
    is_tied = Column(Boolean, default=False)
    tied_with_team_ids = Column(JSON, default=list)  # List of team IDs tied with
    tie_break_reason = Column(Text, nullable=True)  # Why they won/lost tie
    tie_break_applied = Column(String(50), nullable=True)  # Which rule was used
    
    # Medal/Winner designation (Phase 5E)
    medal = Column(String(20), nullable=True)  # "gold", "silver", "bronze", None
    is_winner = Column(Boolean, default=False)  # Competition winner
    is_runner_up = Column(Boolean, default=False)
    is_semifinalist = Column(Boolean, default=False)
    
    # Status
    status = Column(SQLEnum(RankStatus), default=RankStatus.DRAFT, nullable=False)
    is_published = Column(Boolean, default=False, nullable=False)
    
    # Metadata
    computed_at = Column(DateTime, nullable=True)  # When ranking was calculated
    computed_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # System or admin
    published_at = Column(DateTime, nullable=True)
    published_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<TeamRanking(rank={self.rank}, team={self.team_id}, score={self.total_score})>"
    
    def to_dict(self, include_details=False):
        data = {
            "id": self.id,
            "institution_id": self.institution_id,
            "competition_id": self.competition_id,
            "round_id": self.round_id,
            "team_id": self.team_id,
            "ranking_type": self.ranking_type.value if self.ranking_type else None,
            
            # Ranking
            "rank": self.rank,
            "rank_display": self.get_rank_display(),
            
            # Scores
            "total_score": round(self.total_score, 2) if self.total_score else None,
            "raw_score": round(self.raw_score, 2) if self.raw_score else None,
            "normalized_score": round(self.normalized_score, 1) if self.normalized_score else None,
            
            # Tie info
            "is_tied": self.is_tied,
            "tied_with": self.tied_with_team_ids,
            "tie_break_reason": self.tie_break_reason,
            
            # Medals
            "medal": self.medal,
            "is_winner": self.is_winner,
            "is_runner_up": self.is_runner_up,
            "is_semifinalist": self.is_semifinalist,
            
            # Status
            "status": self.status.value if self.status else None,
            "is_published": self.is_published,
            "published_at": self.published_at.isoformat() if self.published_at else None
        }
        
        if include_details:
            data["criterion_scores"] = {
                "issue_framing": round(self.issue_framing_avg, 2) if self.issue_framing_avg else None,
                "legal_reasoning": round(self.legal_reasoning_avg, 2) if self.legal_reasoning_avg else None,
                "use_of_authority": round(self.use_of_authority_avg, 2) if self.use_of_authority_avg else None,
                "structure_clarity": round(self.structure_clarity_avg, 2) if self.structure_clarity_avg else None,
                "oral_advocacy": round(self.oral_advocacy_avg, 2) if self.oral_advocacy_avg else None,
                "responsiveness": round(self.responsiveness_avg, 2) if self.responsiveness_avg else None
            }
        
        return data
    
    def get_rank_display(self):
        """Get human-readable rank (1st, 2nd, 3rd, etc.)"""
        if self.rank is None:
            return None
        
        if self.rank_display:
            return self.rank_display
        
        # Auto-generate
        if 10 <= self.rank % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(self.rank % 10, "th")
        
        return f"{self.rank}{suffix}"


class Leaderboard(Base):
    """
    Phase 5E: Leaderboard view for competitions.
    Aggregates team rankings for display.
    """
    __tablename__ = "leaderboards"
    
    id = Column(Integer, primary_key=True, index=True)
    
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False)
    
    # Leaderboard type
    ranking_type = Column(SQLEnum(RankingType), default=RankingType.OVERALL, nullable=False)
    round_id = Column(Integer, ForeignKey("competition_rounds.id"), nullable=True)
    
    # Configuration
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    show_scores = Column(Boolean, default=True)  # Show numeric scores or just ranks?
    show_medals = Column(Boolean, default=True)
    
    # Status
    is_published = Column(Boolean, default=False, nullable=False)
    published_at = Column(DateTime, nullable=True)
    
    # Computed data (cached)
    entries = Column(JSON, default=list)  # Array of ranking entries
    last_computed_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "competition_id": self.competition_id,
            "ranking_type": self.ranking_type.value if self.ranking_type else None,
            "title": self.title,
            "description": self.description,
            "show_scores": self.show_scores,
            "show_medals": self.show_medals,
            "is_published": self.is_published,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "entries": self.entries,
            "last_computed_at": self.last_computed_at.isoformat() if self.last_computed_at else None
        }


class WinnerSelection(Base):
    """
    Phase 5E: Official winner designation for competitions.
    """
    __tablename__ = "winner_selections"
    
    id = Column(Integer, primary_key=True, index=True)
    
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False)
    round_id = Column(Integer, ForeignKey("competition_rounds.id"), nullable=True)  # Null = overall winner
    
    # Winner
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    rank = Column(Integer, nullable=False)  # 1, 2, 3, etc.
    
    # Winner details
    title = Column(String(100), nullable=False)  # "Winner", "Runner-up", "Semi-finalist", etc.
    medal = Column(String(20), nullable=True)  # gold, silver, bronze
    certificate_text = Column(Text, nullable=True)  # Custom certificate text
    
    # Selection method
    selection_method = Column(String(50), default="ranking")  # ranking, manual, tie_break
    selected_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    selected_at = Column(DateTime, default=datetime.utcnow)
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Status
    is_official = Column(Boolean, default=False)  # Can be provisional until final
    announced_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "competition_id": self.competition_id,
            "round_id": self.round_id,
            "team_id": self.team_id,
            "rank": self.rank,
            "title": self.title,
            "medal": self.medal,
            "selection_method": self.selection_method,
            "is_official": self.is_official,
            "announced_at": self.announced_at.isoformat() if self.announced_at else None,
            "selected_at": self.selected_at.isoformat() if self.selected_at else None
        }


class TieBreakRule(Base):
    """
    Phase 5E: Configuration for tie-break rules.
    """
    __tablename__ = "tie_break_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False)
    
    # Rule configuration
    rule_order = Column(Integer, nullable=False)  # 1 = first rule to apply
    rule_name = Column(String(100), nullable=False)  # e.g., "higher_legal_reasoning"
    rule_description = Column(Text, nullable=True)
    criterion = Column(String(50), nullable=True)  # Which criterion to compare
    comparison = Column(String(20), default="higher")  # higher, lower, exact
    
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "rule_order": self.rule_order,
            "rule_name": self.rule_name,
            "description": self.rule_description,
            "criterion": self.criterion,
            "comparison": self.comparison,
            "is_active": self.is_active
        }
