"""add contact_logs table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-25

Phase 4 — structured contact log for analyst↔provider interactions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contact_logs",
        sa.Column("contact_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("logged_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("contact_date", sa.String(length=10), nullable=False),
        sa.Column("method", sa.String(length=30), nullable=False),
        sa.Column("direction", sa.String(length=15), nullable=False),
        sa.Column("participant_name", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["opa_cases.case_id"]),
        sa.ForeignKeyConstraint(["logged_by_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("contact_id"),
    )
    op.create_index(
        "ix_contact_logs_case_id", "contact_logs", ["case_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_contact_logs_case_id", table_name="contact_logs")
    op.drop_table("contact_logs")
