"""
Alembic migration: Phase 6 Leaderboard Indexes

Adds performance indexes for competitive leaderboard queries.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "phase6_leaderboard_indexes"
down_revision = "phase4_match_engine"  # Set appropriately in real deployment
branch_labels = None
depends_on = None


def upgrade():
    # Index on PlayerRating.current_rating for leaderboard sorting
    op.create_index(
        "ix_player_ratings_current_rating",
        "player_ratings",
        ["current_rating"],
        unique=False
    )
    
    # Index on RatingHistory.user_id for profile queries
    op.create_index(
        "ix_rating_history_user_id_timestamp",
        "rating_history",
        ["user_id", "timestamp"],
        unique=False
    )
    
    # Index on Match.state for filtering finalized matches
    op.create_index(
        "ix_matches_state",
        "matches",
        ["state"],
        unique=False
    )
    
    # Index on Match.is_ai_match for excluding AI matches
    op.create_index(
        "ix_matches_is_ai_match",
        "matches",
        ["is_ai_match"],
        unique=False
    )
    
    # Composite index for finalized non-AI matches
    op.create_index(
        "ix_matches_finalized_non_ai",
        "matches",
        ["state", "is_ai_match", "rating_processed"],
        unique=False
    )
    
    # Add season_id column to matches (nullable for now)
    op.add_column(
        "matches",
        sa.Column("season_id", sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_index("ix_matches_finalized_non_ai", table_name="matches")
    op.drop_index("ix_matches_is_ai_match", table_name="matches")
    op.drop_index("ix_matches_state", table_name="matches")
    op.drop_index("ix_rating_history_user_id_timestamp", table_name="rating_history")
    op.drop_index("ix_player_ratings_current_rating", table_name="player_ratings")
    op.drop_column("matches", "season_id")
