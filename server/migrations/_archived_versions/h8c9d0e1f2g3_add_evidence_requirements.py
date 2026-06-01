"""add evidence_requirements reference table

Revision ID: h8c9d0e1f2g3
Revises: g7b8c9d0e1f2
Create Date: 2026-05-29

Deterministic "what evidence does this code require" rules. Used by the AI
evidence-validation pass to inject auditable, citation-backed expectations
into the prompt instead of relying on freeform model inference.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h8c9d0e1f2g3"
down_revision: Union[str, None] = "g7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evidence_requirements",
        sa.Column("requirement_id", sa.String(length=36), nullable=False),
        sa.Column("code_type", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("required_evidence", sa.Text(), nullable=False),
        sa.Column("policy_reference", sa.String(length=255), nullable=False),
        sa.Column("severity_if_missing", sa.String(length=20),
                  nullable=False, server_default="warning"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.String(length=30), nullable=False),
        sa.Column("updated_at", sa.String(length=30), nullable=False),
        sa.PrimaryKeyConstraint("requirement_id"),
    )
    op.create_index(
        "ix_evidence_requirements_code", "evidence_requirements",
        ["code_type", "code"],
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_requirements_code", table_name="evidence_requirements")
    op.drop_table("evidence_requirements")
