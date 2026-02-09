"""
backend/orm/team_activity.py
Phase 6C: Team Activity Log - Immutable audit trail for accountability
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum as PyEnum

from backend.orm.base import Base


class ActionType(str, PyEnum):
    """Types of actions that can be logged"""
    # Team Actions
    INVITE_SENT = "invite_sent"
    INVITE_ACCEPTED = "invite_accepted"
    INVITE_REJECTED = "invite_rejected"
    MEMBER_REMOVED = "member_removed"
    ROLE_CHANGED = "role_changed"
    CAPTAIN_TRANSFERRED = "captain_transferred"
    
    # Project Actions
    PROJECT_CREATED = "project_created"
    PROJECT_SUBMITTED = "project_submitted"
    PROJECT_LOCKED = "project_locked"
    PROJECT_UNLOCKED = "project_unlocked"
    DEADLINE_OVERRIDE = "deadline_override"
    
    # Writing Actions
    IRAC_SAVED = "irac_saved"
    ISSUE_CREATED = "issue_created"
    ISSUE_UPDATED = "issue_updated"
    ISSUE_DELETED = "issue_deleted"
    
    # Oral Round Actions
    ORAL_ROUND_STARTED = "oral_round_started"
    ORAL_ROUND_COMPLETED = "oral_round_completed"
    ORAL_RESPONSE_SUBMITTED = "oral_response_submitted"
    BENCH_QUESTION_ASKED = "bench_question_asked"
    
    # Evaluation Actions
    EVALUATION_DRAFT_CREATED = "evaluation_draft_created"
    EVALUATION_FINALIZED = "evaluation_finalized"
    SCORE_ASSIGNED = "score_assigned"
    
    # Faculty Actions (Phase 7)
    FACULTY_VIEW = "faculty_view"
    FACULTY_NOTE_ADDED = "faculty_note_added"
    
    # AI Governance Actions (Phase 8)
    AI_USAGE_ALLOWED = "ai_usage_allowed"
    AI_USAGE_BLOCKED = "ai_usage_blocked"
    AI_GOVERNANCE_OVERRIDE = "ai_governance_override"
    
    # Judging & Evaluation Actions (Phase 9)
    JUDGE_ASSIGNED = "judge_assigned"
    EVALUATION_STARTED = "evaluation_started"
    RESULTS_PUBLISHED = "results_published"


class TargetType(str, PyEnum):
    """Types of entities that can be targets of actions"""
    PROJECT = "project"
    ISSUE = "issue"
    IRAC = "irac"
    ORAL_ROUND = "oral_round"
    EVALUATION = "evaluation"
    TEAM = "team"
    INVITATION = "invitation"
    MEMBER = "member"


class TeamActivityLog(Base):
    """
    Phase 6C: Immutable team activity log for accountability.
    
    This table records what happened, who did it, when, and where.
    Logs are append-only and read-only.
    """
    __tablename__ = "team_activity_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Institution scoping - CRITICAL for multi-tenancy
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    
    # Team scoping
    team_id = Column(
        Integer,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    
    # Project scoping (nullable for team-level actions)
    project_id = Column(
        Integer,
        ForeignKey("moot_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Actor information (who performed the action)
    actor_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False
    )
    actor_role_at_time = Column(String(50), nullable=False)
    
    # Action details
    action_type = Column(SQLEnum(ActionType), nullable=False)
    target_type = Column(SQLEnum(TargetType), nullable=False)
    target_id = Column(Integer, nullable=True)  # ID of the target entity
    target_name = Column(String(255), nullable=True)  # Human-readable name
    
    # Context (flexible JSON for additional context)
    # e.g., {"old_role": "researcher", "new_role": "speaker"} for role changes
    context = Column(JSON, nullable=True)
    
    # Timestamp (when it happened)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # IP address for additional audit trail
    ip_address = Column(String(45), nullable=True)
    
    # Relationships (read-only, no backref for safety)
    institution = relationship("Institution", lazy="selectin")
    team = relationship("Team", lazy="selectin")
    project = relationship("MootProject", lazy="selectin")
    actor = relationship("User", lazy="selectin")
    
    def __repr__(self):
        return f"<TeamActivityLog({self.action_type.value}, team={self.team_id}, actor={self.actor_id})>"
    
    def to_dict(self, include_actor=False):
        """Convert to dictionary for API responses"""
        data = {
            "id": self.id,
            "institution_id": self.institution_id,
            "team_id": self.team_id,
            "project_id": self.project_id,
            "action_type": self.action_type.value if self.action_type else None,
            "target_type": self.target_type.value if self.target_type else None,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "context": self.context,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
        
        if include_actor and self.actor:
            data["actor"] = {
                "id": self.actor.id,
                "full_name": self.actor.full_name if hasattr(self.actor, 'full_name') else None,
                "email": self.actor.email if hasattr(self.actor, 'email') else None,
                "role_at_time": self.actor_role_at_time
            }
        else:
            data["actor_id"] = self.actor_id
            data["actor_role_at_time"] = self.actor_role_at_time
        
        return data
    
    def to_human_readable(self) -> str:
        """Generate human-readable description of the activity"""
        actor_name = self.actor.full_name if self.actor and hasattr(self.actor, 'full_name') else f"User {self.actor_id}"
        target = self.target_name or f"{self.target_type.value} {self.target_id}"
        
        action_descriptions = {
            ActionType.INVITE_SENT: f"{actor_name} sent an invitation",
            ActionType.INVITE_ACCEPTED: f"{actor_name} accepted an invitation",
            ActionType.INVITE_REJECTED: f"{actor_name} rejected an invitation",
            ActionType.MEMBER_REMOVED: f"{actor_name} removed a member",
            ActionType.ROLE_CHANGED: f"{actor_name} changed a role",
            ActionType.CAPTAIN_TRANSFERRED: f"{actor_name} transferred captaincy",
            ActionType.PROJECT_CREATED: f"{actor_name} created {target}",
            ActionType.PROJECT_SUBMITTED: f"{actor_name} submitted {target}",
            ActionType.PROJECT_LOCKED: f"{actor_name} locked {target}",
            ActionType.PROJECT_UNLOCKED: f"{actor_name} unlocked {target}",
            ActionType.DEADLINE_OVERRIDE: f"{actor_name} extended deadline for {target}",
            ActionType.IRAC_SAVED: f"{actor_name} saved IRAC for {target}",
            ActionType.ISSUE_CREATED: f"{actor_name} created {target}",
            ActionType.ISSUE_UPDATED: f"{actor_name} updated {target}",
            ActionType.ISSUE_DELETED: f"{actor_name} deleted {target}",
            ActionType.ORAL_ROUND_STARTED: f"{actor_name} started {target}",
            ActionType.ORAL_ROUND_COMPLETED: f"{actor_name} completed {target}",
            ActionType.ORAL_RESPONSE_SUBMITTED: f"{actor_name} submitted an oral response",
            ActionType.BENCH_QUESTION_ASKED: f"{actor_name} asked a bench question",
            ActionType.EVALUATION_DRAFT_CREATED: f"{actor_name} created evaluation draft for {target}",
            ActionType.EVALUATION_FINALIZED: f"{actor_name} finalized evaluation for {target}",
            ActionType.SCORE_ASSIGNED: f"{actor_name} assigned scores for {target}",
            # Faculty Actions (Phase 7)
            ActionType.FACULTY_VIEW: f"{actor_name} viewed {target} (Faculty)",
            ActionType.FACULTY_NOTE_ADDED: f"{actor_name} added faculty note to {target}",
            # AI Governance Actions (Phase 8)
            ActionType.AI_USAGE_ALLOWED: f"{actor_name} used AI {target} (Allowed)",
            ActionType.AI_USAGE_BLOCKED: f"{actor_name} attempted AI {target} (Blocked)",
            ActionType.AI_GOVERNANCE_OVERRIDE: f"{actor_name} performed AI governance override on {target}",
            # Judging & Evaluation Actions (Phase 9)
            ActionType.JUDGE_ASSIGNED: f"{actor_name} assigned judge to {target}",
            ActionType.EVALUATION_STARTED: f"{actor_name} started evaluation for {target}",
            ActionType.RESULTS_PUBLISHED: f"{actor_name} published results for {target}",
        }
        
        return action_descriptions.get(
            self.action_type, 
            f"{actor_name} performed {self.action_type.value} on {target}"
        )
