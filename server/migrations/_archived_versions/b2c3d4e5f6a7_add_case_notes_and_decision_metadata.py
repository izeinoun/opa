"""add case_notes table and decision_metadata column on opa_cases

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-24

Phase 1 of analyst workflow:
- case_notes table for free-text analyst/supervisor commentary
- opa_cases.decision_metadata JSON column holding pending closure data
  (disposition + reason + recovered_amount + submitted_by_user_id)
  while the case is in pending_supervisor state

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "case_notes",
        sa.Column("note_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("author_user_id", sa.String(length=36), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["opa_cases.case_id"]),
        sa.ForeignKeyConstraint(["author_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("note_id"),
    )
    op.create_index(
        "ix_case_notes_case_id", "case_notes", ["case_id"]
    )

    with op.batch_alter_table("opa_cases") as batch_op:
        batch_op.add_column(
            sa.Column("decision_metadata", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("opa_cases") as batch_op:
        batch_op.drop_column("decision_metadata")
    op.drop_index("ix_case_notes_case_id", table_name="case_notes")
    op.drop_table("case_notes")
