"""add finding_dispositions table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-24

Phase 2 — per-finding accept/reject/adjust workflow.

One row per finding. Status values: accepted, rejected, needs_review, adjusted.
Default seeded by DetectorService on finding creation based on detector type +
confidence (see app/services/disposition_service.py).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "finding_dispositions",
        sa.Column("disposition_id", sa.String(length=36), nullable=False),
        sa.Column("finding_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("original_amount", sa.Float(), nullable=False),
        sa.Column("adjusted_amount", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("decided_at", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.finding_id"]),
        sa.ForeignKeyConstraint(["case_id"], ["opa_cases.case_id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("disposition_id"),
        sa.UniqueConstraint("finding_id"),
    )
    op.create_index(
        "ix_finding_dispositions_case_id", "finding_dispositions", ["case_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_finding_dispositions_case_id", table_name="finding_dispositions")
    op.drop_table("finding_dispositions")
