"""add detector_rule_config and prioritization_config

Revision ID: a1b2c3d4e5f6
Revises: 20bc1e724080
Create Date: 2026-05-24

These tables were added to app/models/workflow.py after the initial schema
was authored but no migration was ever generated for them. Without this
migration, a fresh `alembic upgrade head` followed by detector execution
fails with "no such table: detector_rule_config".

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "20bc1e724080"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "detector_rule_config",
        sa.Column("rule_code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.String(length=30), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("rule_code"),
    )

    op.create_table(
        "prioritization_config",
        sa.Column("config_id", sa.String(length=20), nullable=False),
        sa.Column("amount_weight", sa.Float(), nullable=False),
        sa.Column("likelihood_weight", sa.Float(), nullable=False),
        sa.Column("urgency_weight", sa.Float(), nullable=False),
        sa.Column("amount_cap", sa.Float(), nullable=False),
        sa.Column("urgency_window_days", sa.Integer(), nullable=False),
        sa.Column("high_threshold", sa.Float(), nullable=False),
        sa.Column("medium_threshold", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.String(length=30), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("config_id"),
    )


def downgrade() -> None:
    op.drop_table("prioritization_config")
    op.drop_table("detector_rule_config")
