"""unify ClaimGuard into PayGuard schema

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-29

Brings the ClaimGuard (pre-pay) pipeline onto the unified data model.

Changes:
  • claims: add pipeline_mode, claim_form_type, care_setting, drg, specialty,
    description, extracted_text, claim_summary, code_descriptions. Relax
    total_paid + paid_date to nullable (pre-pay claims have no payment yet).
  • claim_lines: relax units_paid, paid_amount, allowed_amount to nullable.
  • findings: relax detector_id, overpayment_amount, confidence, rule_version
    to nullable (AI / pre-pay findings have no edit code or confidence).
    Add title (ClaimGuard's short label for AI findings).
  • opa_cases: relax total_overpayment_amount to nullable; add review_time_minutes.
  • audit_logs: add nullable claim_id for pre-case lifecycle audits.
  • opa_users: add initials, color_hex, specialty, supervisor_id (self-FK).
  • New table: documents (PDF/file uploads attached to claim or case).
  • New table: runtime_config (flat key/value for operator feature flags).

No tenant scoping in this migration — each tenant is deployed as a separate
instance per architectural decision.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── opa_users: 4 new nullable columns ────────────────────────────────
    with op.batch_alter_table("opa_users") as batch_op:
        batch_op.add_column(sa.Column("initials", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("color_hex", sa.String(length=7), nullable=True))
        batch_op.add_column(sa.Column("specialty", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("supervisor_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_opa_users_supervisor",
            "opa_users",
            ["supervisor_id"],
            ["user_id"],
        )

    # ── claims: pipeline_mode + 8 ClaimGuard columns + relax 2 NOT NULLs ─
    with op.batch_alter_table("claims") as batch_op:
        batch_op.add_column(sa.Column(
            "pipeline_mode", sa.String(length=20),
            nullable=False, server_default="post_pay",
        ))
        batch_op.add_column(sa.Column("claim_form_type", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("care_setting", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("drg", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("specialty", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("extracted_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("claim_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("code_descriptions", sa.Text(), nullable=True))
        batch_op.alter_column("total_paid", existing_type=sa.Float(), nullable=True)
        batch_op.alter_column("paid_date", existing_type=sa.String(length=10), nullable=True)

    # ── claim_lines: relax 3 columns to nullable ─────────────────────────
    with op.batch_alter_table("claim_lines") as batch_op:
        batch_op.alter_column("units_paid", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("paid_amount", existing_type=sa.Float(), nullable=True)
        batch_op.alter_column("allowed_amount", existing_type=sa.Float(), nullable=True)

    # ── findings: relax 4 columns + add title ────────────────────────────
    with op.batch_alter_table("findings") as batch_op:
        batch_op.alter_column("detector_id", existing_type=sa.String(length=50), nullable=True)
        batch_op.alter_column("overpayment_amount", existing_type=sa.Float(), nullable=True)
        batch_op.alter_column("confidence", existing_type=sa.Float(), nullable=True)
        batch_op.alter_column("rule_version", existing_type=sa.String(length=20), nullable=True)
        batch_op.add_column(sa.Column("title", sa.String(length=200), nullable=True))

    # ── opa_cases: relax total_overpayment_amount + add review_time_minutes ─
    with op.batch_alter_table("opa_cases") as batch_op:
        batch_op.alter_column("total_overpayment_amount", existing_type=sa.Float(), nullable=True)
        batch_op.add_column(sa.Column(
            "review_time_minutes", sa.Integer(),
            nullable=False, server_default="0",
        ))

    # ── audit_logs: add nullable claim_id ────────────────────────────────
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.add_column(sa.Column("claim_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_audit_logs_claim",
            "claims",
            ["claim_id"],
            ["claim_id"],
        )

    # ── New table: documents ─────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("claim_id", sa.String(length=36), nullable=True),
        sa.Column("case_id", sa.String(length=36), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("file_size_kb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(length=30), nullable=False, server_default="supporting"),
        sa.Column("uploaded_at", sa.String(length=30), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.claim_id"]),
        sa.ForeignKeyConstraint(["case_id"], ["opa_cases.case_id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("document_id"),
    )
    op.create_index("ix_documents_claim_id", "documents", ["claim_id"])
    op.create_index("ix_documents_case_id", "documents", ["case_id"])

    # ── New table: runtime_config ────────────────────────────────────────
    op.create_table(
        "runtime_config",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(length=30), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("runtime_config")
    op.drop_index("ix_documents_case_id", table_name="documents")
    op.drop_index("ix_documents_claim_id", table_name="documents")
    op.drop_table("documents")

    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_constraint("fk_audit_logs_claim", type_="foreignkey")
        batch_op.drop_column("claim_id")

    with op.batch_alter_table("opa_cases") as batch_op:
        batch_op.drop_column("review_time_minutes")
        batch_op.alter_column("total_overpayment_amount", existing_type=sa.Float(), nullable=False)

    with op.batch_alter_table("findings") as batch_op:
        batch_op.drop_column("title")
        batch_op.alter_column("rule_version", existing_type=sa.String(length=20), nullable=False)
        batch_op.alter_column("confidence", existing_type=sa.Float(), nullable=False)
        batch_op.alter_column("overpayment_amount", existing_type=sa.Float(), nullable=False)
        batch_op.alter_column("detector_id", existing_type=sa.String(length=50), nullable=False)

    with op.batch_alter_table("claim_lines") as batch_op:
        batch_op.alter_column("allowed_amount", existing_type=sa.Float(), nullable=False)
        batch_op.alter_column("paid_amount", existing_type=sa.Float(), nullable=False)
        batch_op.alter_column("units_paid", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("claims") as batch_op:
        batch_op.alter_column("paid_date", existing_type=sa.String(length=10), nullable=False)
        batch_op.alter_column("total_paid", existing_type=sa.Float(), nullable=False)
        batch_op.drop_column("code_descriptions")
        batch_op.drop_column("claim_summary")
        batch_op.drop_column("extracted_text")
        batch_op.drop_column("description")
        batch_op.drop_column("specialty")
        batch_op.drop_column("drg")
        batch_op.drop_column("care_setting")
        batch_op.drop_column("claim_form_type")
        batch_op.drop_column("pipeline_mode")

    with op.batch_alter_table("opa_users") as batch_op:
        batch_op.drop_constraint("fk_opa_users_supervisor", type_="foreignkey")
        batch_op.drop_column("supervisor_id")
        batch_op.drop_column("specialty")
        batch_op.drop_column("color_hex")
        batch_op.drop_column("initials")
