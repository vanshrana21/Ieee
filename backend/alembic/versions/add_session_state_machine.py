"""
Alembic migration: Add session state transitions and session state log tables
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers
revision = 'add_session_state_machine'
down_revision = None  # Will be set based on existing migrations
branch_labels = None
depends_on = None


def upgrade():
    """
    Create session_state_transitions table and classroom_session_state_log table.
    Seed default state transitions for the classroom state machine.
    """
    # Create session_state_transitions table
    op.create_table(
        'session_state_transitions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('from_state', sa.String(length=50), nullable=False),
        sa.Column('to_state', sa.String(length=50), nullable=False),
        sa.Column('trigger_type', sa.String(length=50), nullable=True),
        sa.Column('requires_all_rounds_complete', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('requires_faculty', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('from_state', 'to_state', name='uq_state_from_to')
    )
    
    # Create index for faster lookups
    op.create_index('ix_session_state_transitions_from_state', 'session_state_transitions', ['from_state'])
    
    # Seed default transitions
    transitions_table = sa.table(
        'session_state_transitions',
        sa.column('from_state', sa.String),
        sa.column('to_state', sa.String),
        sa.column('trigger_type', sa.String),
        sa.column('requires_all_rounds_complete', sa.Boolean),
        sa.column('requires_faculty', sa.Boolean),
    )
    
    op.bulk_insert(
        transitions_table,
        [
            # Standard flow transitions
            {"from_state": "CREATED", "to_state": "PREPARING", "trigger_type": "faculty_action", "requires_all_rounds_complete": False, "requires_faculty": True},
            {"from_state": "PREPARING", "to_state": "ARGUING_PETITIONER", "trigger_type": "faculty_action", "requires_all_rounds_complete": False, "requires_faculty": True},
            {"from_state": "ARGUING_PETITIONER", "to_state": "ARGUING_RESPONDENT", "trigger_type": "round_completed", "requires_all_rounds_complete": False, "requires_faculty": False},
            {"from_state": "ARGUING_RESPONDENT", "to_state": "REBUTTAL", "trigger_type": "round_completed", "requires_all_rounds_complete": False, "requires_faculty": False},
            {"from_state": "REBUTTAL", "to_state": "JUDGING", "trigger_type": "faculty_action", "requires_all_rounds_complete": False, "requires_faculty": True},
            {"from_state": "JUDGING", "to_state": "COMPLETED", "trigger_type": "all_evaluations_complete", "requires_all_rounds_complete": True, "requires_faculty": True},
            
            # Cancel transitions (allowed from any state)
            {"from_state": "CREATED", "to_state": "CANCELLED", "trigger_type": "faculty_action", "requires_all_rounds_complete": False, "requires_faculty": True},
            {"from_state": "PREPARING", "to_state": "CANCELLED", "trigger_type": "faculty_action", "requires_all_rounds_complete": False, "requires_faculty": True},
            {"from_state": "ARGUING_PETITIONER", "to_state": "CANCELLED", "trigger_type": "faculty_action", "requires_all_rounds_complete": False, "requires_faculty": True},
            {"from_state": "ARGUING_RESPONDENT", "to_state": "CANCELLED", "trigger_type": "faculty_action", "requires_all_rounds_complete": False, "requires_faculty": True},
            {"from_state": "REBUTTAL", "to_state": "CANCELLED", "trigger_type": "faculty_action", "requires_all_rounds_complete": False, "requires_faculty": True},
            {"from_state": "JUDGING", "to_state": "CANCELLED", "trigger_type": "faculty_action", "requires_all_rounds_complete": False, "requires_faculty": True},
        ]
    )
    
    # Create classroom_session_state_log table (audit trail)
    op.create_table(
        'classroom_session_state_log',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('classroom_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('from_state', sa.String(length=50), nullable=False),
        sa.Column('to_state', sa.String(length=50), nullable=False),
        sa.Column('triggered_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('trigger_type', sa.String(length=50), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('is_successful', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    
    # Create indexes for audit log queries
    op.create_index('ix_classroom_session_state_log_session_id', 'classroom_session_state_log', ['session_id'])
    op.create_index('ix_classroom_session_state_log_created_at', 'classroom_session_state_log', ['created_at'])
    
    # Add state_updated_at column to classroom_sessions if not exists
    # Note: This might already exist, so we use batch_alter_table for safety
    try:
        op.add_column(
            'classroom_sessions',
            sa.Column('state_updated_at', sa.DateTime(), nullable=True)
        )
    except Exception:
        pass  # Column might already exist


def downgrade():
    """
    Remove session state machine tables and columns.
    """
    # Drop audit log table
    op.drop_index('ix_classroom_session_state_log_created_at', table_name='classroom_session_state_log')
    op.drop_index('ix_classroom_session_state_log_session_id', table_name='classroom_session_state_log')
    op.drop_table('classroom_session_state_log')
    
    # Drop transitions table
    op.drop_index('ix_session_state_transitions_from_state', table_name='session_state_transitions')
    op.drop_table('session_state_transitions')
    
    # Remove state_updated_at column if we added it
    try:
        op.drop_column('classroom_sessions', 'state_updated_at')
    except Exception:
        pass  # Column might not exist
