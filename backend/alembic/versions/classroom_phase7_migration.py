"""
Alembic Migration: Classroom Phase 7

Revision ID: classroom_phase7
Revises: previous_revision
Create Date: 2025-01-01

This migration adds tables for Phase 7 Classroom Mode:
- classroom_rounds
- classroom_round_actions

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import enum

# revision identifiers, used by Alembic.
revision = 'classroom_phase7'
down_revision = 'previous_revision'
branch_labels = None
depends_on = None


class RoundState(str, enum.Enum):
    WAITING = "waiting"
    ARGUMENT_PETITIONER = "argument_petitioner"
    ARGUMENT_RESPONDENT = "argument_respondent"
    REBUTTAL = "rebuttal"
    SUR_REBUTTAL = "sur_rebuttal"
    JUDGE_QUESTIONS = "judge_questions"
    SCORING = "scoring"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class PairingMode(str, enum.Enum):
    RANDOM = "random"
    MANUAL = "manual"
    SKILL = "skill"
    AI_FALLBACK = "ai_fallback"


class ActionType(str, enum.Enum):
    ROUND_CREATED = "round_created"
    ROUND_STARTED = "round_started"
    STATE_TRANSITION = "state_transition"
    ROUND_PAUSED = "round_paused"
    ROUND_RESUMED = "round_resumed"
    ROUND_COMPLETED = "round_completed"
    ROUND_CANCELLED = "round_cancelled"
    PARTICIPANT_JOINED = "participant_joined"
    PARTICIPANT_LEFT = "participant_left"
    PARTICIPANT_DISCONNECTED = "participant_disconnected"
    PARTICIPANT_RECONNECTED = "participant_reconnected"
    ROLE_ASSIGNED = "role_assigned"
    ARGUMENT_SUBMITTED = "argument_submitted"
    OBJECTION_RAISED = "objection_raised"
    OBJECTION_RULED = "objection_ruled"
    QUESTION_ASKED = "question_asked"
    RESPONSE_GIVEN = "response_given"
    SCORE_SUBMITTED = "score_submitted"
    SCORE_OVERRIDDEN = "score_overridden"
    WINNER_DECLARED = "winner_declared"
    FORCE_STATE_CHANGE = "force_state_change"
    TIME_EXTENDED = "time_extended"
    PARTICIPANT_REMOVED = "participant_removed"
    PAIRING_UPDATED = "pairing_updated"
    AUTO_TRANSITION = "auto_transition"
    AI_RESPONSE_GENERATED = "ai_response_generated"
    TIMER_EXPIRED = "timer_expired"


def upgrade():
    # Create classroom_rounds table
    op.create_table(
        'classroom_rounds',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('petitioner_id', sa.Integer(), nullable=True),
        sa.Column('respondent_id', sa.Integer(), nullable=True),
        sa.Column('judge_id', sa.Integer(), nullable=True),
        sa.Column('petitioner_is_ai', sa.Boolean(), default=False),
        sa.Column('respondent_is_ai', sa.Boolean(), default=False),
        sa.Column('judge_is_ai', sa.Boolean(), default=False),
        sa.Column('ai_opponent_session_id', sa.Integer(), nullable=True),
        sa.Column('state', sa.Enum(RoundState), default=RoundState.WAITING, nullable=False),
        sa.Column('previous_state', sa.Enum(RoundState), nullable=True),
        sa.Column('time_limit_seconds', sa.Integer(), default=600),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('phase_start_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('phase_duration_seconds', sa.Integer(), nullable=True),
        sa.Column('petitioner_score', sa.Float(), nullable=True),
        sa.Column('respondent_score', sa.Float(), nullable=True),
        sa.Column('winner_id', sa.Integer(), nullable=True),
        sa.Column('case_title', sa.String(255), nullable=True),
        sa.Column('case_summary', sa.Text(), nullable=True),
        sa.Column('logs', sa.JSON(), default=list),
        sa.Column('transcript', sa.Text(), nullable=True),
        sa.Column('round_number', sa.Integer(), default=1),
        sa.Column('pairing_mode', sa.Enum(PairingMode), default=PairingMode.RANDOM),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('version', sa.Integer(), default=1),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['session_id'], ['classroom_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['petitioner_id'], ['users.id']),
        sa.ForeignKeyConstraint(['respondent_id'], ['users.id']),
        sa.ForeignKeyConstraint(['judge_id'], ['users.id']),
        sa.ForeignKeyConstraint(['winner_id'], ['users.id']),
        sa.ForeignKeyConstraint(['ai_opponent_session_id'], ['ai_opponent_sessions.id']),
    )
    
    # Create indexes for classroom_rounds
    op.create_index('ix_classroom_rounds_session_id', 'classroom_rounds', ['session_id'])
    op.create_index('ix_classroom_rounds_state', 'classroom_rounds', ['state'])
    op.create_index('ix_classroom_rounds_session_state', 'classroom_rounds', ['session_id', 'state'])
    op.create_index('ix_classroom_rounds_petitioner', 'classroom_rounds', ['petitioner_id'])
    op.create_index('ix_classroom_rounds_respondent', 'classroom_rounds', ['respondent_id'])
    
    # Create classroom_round_actions table
    op.create_table(
        'classroom_round_actions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('round_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('actor_type', sa.String(20), default='user'),
        sa.Column('action_type', sa.Enum(ActionType), nullable=False),
        sa.Column('action_description', sa.String(255), nullable=True),
        sa.Column('from_state', sa.String(50), nullable=True),
        sa.Column('to_state', sa.String(50), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('client_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('sequence_number', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['round_id'], ['classroom_rounds.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['classroom_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id']),
    )
    
    # Create indexes for classroom_round_actions
    op.create_index('ix_round_actions_session_id', 'classroom_round_actions', ['session_id'])
    op.create_index('ix_round_actions_action_type', 'classroom_round_actions', ['action_type'])
    op.create_index('ix_round_actions_created_at', 'classroom_round_actions', ['created_at'])
    op.create_index('ix_round_actions_session_type_time', 'classroom_round_actions', ['session_id', 'action_type', 'created_at'])
    op.create_index('ix_round_actions_round_time', 'classroom_round_actions', ['round_id', 'created_at'])
    op.create_index('ix_round_actions_actor', 'classroom_round_actions', ['actor_user_id', 'created_at'])
    
    # Add columns to existing classroom_sessions table if needed
    # (These should already exist from previous migrations)
    # op.add_column('classroom_sessions', sa.Column('pairing_mode', sa.Enum(PairingMode), default=PairingMode.RANDOM))


def downgrade():
    # Drop indexes first
    op.drop_index('ix_round_actions_actor', table_name='classroom_round_actions')
    op.drop_index('ix_round_actions_round_time', table_name='classroom_round_actions')
    op.drop_index('ix_round_actions_session_type_time', table_name='classroom_round_actions')
    op.drop_index('ix_round_actions_created_at', table_name='classroom_round_actions')
    op.drop_index('ix_round_actions_action_type', table_name='classroom_round_actions')
    op.drop_index('ix_round_actions_session_id', table_name='classroom_round_actions')
    
    op.drop_index('ix_classroom_rounds_respondent', table_name='classroom_rounds')
    op.drop_index('ix_classroom_rounds_petitioner', table_name='classroom_rounds')
    op.drop_index('ix_classroom_rounds_session_state', table_name='classroom_rounds')
    op.drop_index('ix_classroom_rounds_state', table_name='classroom_rounds')
    op.drop_index('ix_classroom_rounds_session_id', table_name='classroom_rounds')
    
    # Drop tables
    op.drop_table('classroom_round_actions')
    op.drop_table('classroom_rounds')
