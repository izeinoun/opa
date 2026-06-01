"""add finding issue_summary/suggestion columns and prepay_finding_decisions

Revision ID: n4i5j6k7l8m9
Revises: m3h4i5j6k7l8
Create Date: 2026-06-01

Provider-facing AI findings:
- findings.issue_summary + findings.suggestion — concise, billing-provider-facing
  issue/fix pair emitted by the AI audit (ANALYZE prompt). Detector findings and
  pre-existing AI findings leave them NULL (UI falls back to rationale).
- prepay_finding_decisions — per-finding Accept/Reject decision (with optional
  reject comment) driven by the specialist in ClaimGuard's "AI Findings" tab.
  Accepted findings + their suggestions feed the generated provider letter.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "n4i5j6k7l8m9"
down_revision: Union[str, None] = "m3h4i5j6k7l8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("findings") as batch_op:
        batch_op.add_column(sa.Column("issue_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("suggestion", sa.Text(), nullable=True))

    op.create_table(
        "prepay_finding_decisions",
        sa.Column("decision_id", sa.String(length=36), nullable=False),
        sa.Column("finding_id", sa.String(length=36), nullable=False),
        sa.Column("claim_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("decided_at", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.finding_id"]),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.claim_id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("decision_id"),
        sa.UniqueConstraint("finding_id"),
    )
    op.create_index(
        "ix_prepay_finding_decisions_claim_id",
        "prepay_finding_decisions",
        ["claim_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prepay_finding_decisions_claim_id",
        table_name="prepay_finding_decisions",
    )
    op.drop_table("prepay_finding_decisions")
    with op.batch_alter_table("findings") as batch_op:
        batch_op.drop_column("suggestion")
        batch_op.drop_column("issue_summary")
