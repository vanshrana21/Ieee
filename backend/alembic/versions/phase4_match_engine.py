"""
Alembic migration: Phase 4 Competitive Match Engine

Adds:
- Structured competitive fields on existing matches table
- New match_rounds table for 3-round scoring
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "phase4_match_engine"
down_revision = None  # Set appropriately in real deployment
branch_labels = None
depends_on = None


def upgrade():
    # --- Extend existing matches table ---
    op.add_column(
        "matches",
        sa.Column("state", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "matches",
        sa.Column("player_1_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "matches",
        sa.Column("player_2_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "matches",
        sa.Column("player_1_legal_reasoning", sa.Float(), nullable=True),
    )
    op.add_column(
        "matches",
        sa.Column("player_2_legal_reasoning", sa.Float(), nullable=True),
    )
    op.add_column(
        "matches",
        sa.Column("is_ai_match", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "matches",
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "matches",
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Allow player2_id to be NULL for AI fallback matches
    op.alter_column(
        "matches",
        "player2_id",
        existing_type=sa.Integer(),
        nullable=True,
        existing_nullable=False,
    )

    # Check constraint: cannot finalize without both scores
    op.create_check_constraint(
        "ck_matches_scores_before_finalize",
        "matches",
        "(state != 'finalized') OR (player_1_score IS NOT NULL AND player_2_score IS NOT NULL)",
    )

    # --- New match_rounds table ---
    op.create_table(
        "match_rounds",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("argument_text", sa.Text(), nullable=True),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("is_submitted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "match_id",
            "player_id",
            "round_number",
            name="uq_match_round_player_round",
        ),
    )

    op.create_check_constraint(
        "ck_match_round_number_valid",
        "match_rounds",
        "round_number >= 1 AND round_number <= 3",
    )


def downgrade():
    # Drop match_rounds first
    op.drop_constraint("ck_match_round_number_valid", "match_rounds", type_="check")
    op.drop_table("match_rounds")

    # Drop check constraint on matches
    op.drop_constraint("ck_matches_scores_before_finalize", "matches", type_="check")

    # Revert player2_id nullability
    op.alter_column(
        "matches",
        "player2_id",
        existing_type=sa.Integer(),
        nullable=False,
        existing_nullable=True,
    )

    # Drop added columns
    for col in [
        "finalized_at",
        "is_locked",
        "is_ai_match",
        "player_2_legal_reasoning",
        "player_1_legal_reasoning",
        "player_2_score",
        "player_1_score",
        "state",
    ]:
        op.drop_column("matches", col)

