"""add document_templates table and findings fwa_indicator/fwa_rule_code

Revision ID: o5j6k7l8m9n0
Revises: n4i5j6k7l8m9
Create Date: 2026-06-01

Closes model↔migration drift surfaced by a from-scratch chain rebuild:
- document_templates — generic LLM document-generation templates, partitioned
  by the `app` discriminator ('payguard' | 'claimguard'). Was previously only
  realized via create_all (model present, no migration).
- findings.fwa_indicator / findings.fwa_rule_code — SIU fraud/waste/abuse
  markers added to the model earlier without a matching migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "o5j6k7l8m9n0"
down_revision: Union[str, None] = "n4i5j6k7l8m9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_templates",
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("app", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("task_prompt", sa.Text(), nullable=False),
        sa.Column("template_markdown", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.String(length=30), nullable=False),
        sa.Column("updated_at", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("template_id"),
    )
    op.create_index("ix_document_templates_app", "document_templates", ["app"])

    with op.batch_alter_table("findings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "fwa_indicator",
                sa.Boolean(),
                server_default="0",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("fwa_rule_code", sa.String(length=20), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("findings") as batch_op:
        batch_op.drop_column("fwa_rule_code")
        batch_op.drop_column("fwa_indicator")

    op.drop_index("ix_document_templates_app", table_name="document_templates")
    op.drop_table("document_templates")
