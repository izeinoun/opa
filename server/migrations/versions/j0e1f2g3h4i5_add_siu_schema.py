"""add SIU schema + rename fwa→siu, investigator→siu_investigator

Revision ID: j0e1f2g3h4i5
Revises: i9d0e1f2g3h4
Create Date: 2026-05-30

Implements the data layer for the SIU workspace (UC-SIU-01 through UC-SIU-06):

- New tables:
    siu_investigations          investigation lifecycle, mode, hold flags
    investigation_cases         M:N investigation ↔ cases (pattern grouping)
    investigation_notes         immutable investigator notes (with confidential flag)
    law_enforcement_referrals   immutable formal LE referrals
    siu_export_packages         versioned JSON export packages (Mode B)

- New columns on opa_cases:
    siu_investigation_id        FK; non-null when case is in/post SIU
    law_enforcement_hold        bool; mirrors active LE referrals on linked invest
    siu_frozen                  bool; marks the case as read-only outside SIU

- New columns on documents:
    investigation_id            FK; for SIU file attachments
    investigation_note_id       FK; for note-level attachment association

- Data renames (the FWA app was the spec's name for what we now call SIU):
    apps.app_name 'fwa'             → 'siu'
    roles.role_name 'investigator'  → 'siu_investigator'
  All existing user_roles / role_apps rows continue working since the FKs
  point at UUIDs, not the renamed string columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j0e1f2g3h4i5"
down_revision: Union[str, None] = "i9d0e1f2g3h4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── siu_investigations ───────────────────────────────────────────────
    op.create_table(
        "siu_investigations",
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="OPEN"),
        sa.Column("outcome", sa.String(length=40), nullable=True),
        sa.Column("closure_notes", sa.Text(), nullable=True),
        sa.Column("escalation_source", sa.String(length=40), nullable=False),
        sa.Column("escalation_reason", sa.Text(), nullable=False),
        sa.Column("escalated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("escalated_at", sa.String(length=30), nullable=False),
        sa.Column("investigator_assigned_user_id", sa.String(length=36), nullable=True),
        sa.Column("opened_at", sa.String(length=30), nullable=True),
        sa.Column("closed_at", sa.String(length=30), nullable=True),
        sa.Column("closed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("law_enforcement_hold", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("siu_mode", sa.String(length=10), nullable=False, server_default="A"),
        sa.Column("created_at", sa.String(length=30), nullable=False),
        sa.Column("updated_at", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["escalated_by_user_id"], ["opa_users.user_id"]),
        sa.ForeignKeyConstraint(["investigator_assigned_user_id"], ["opa_users.user_id"]),
        sa.ForeignKeyConstraint(["closed_by_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("investigation_id"),
    )
    op.create_index("ix_siu_investigations_status", "siu_investigations", ["status"])
    op.create_index("ix_siu_investigations_assigned",
                    "siu_investigations", ["investigator_assigned_user_id"])

    # ── investigation_cases (M:N) ────────────────────────────────────────
    op.create_table(
        "investigation_cases",
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["investigation_id"], ["siu_investigations.investigation_id"]),
        sa.ForeignKeyConstraint(["case_id"], ["opa_cases.case_id"]),
        sa.PrimaryKeyConstraint("investigation_id", "case_id"),
    )

    # ── investigation_notes ──────────────────────────────────────────────
    op.create_table(
        "investigation_notes",
        sa.Column("note_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("note_date", sa.String(length=10), nullable=False),
        sa.Column("note_type", sa.String(length=40), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_confidential", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("author_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["investigation_id"], ["siu_investigations.investigation_id"]),
        sa.ForeignKeyConstraint(["author_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("note_id"),
    )
    op.create_index("ix_investigation_notes_inv",
                    "investigation_notes", ["investigation_id"])

    # ── law_enforcement_referrals ────────────────────────────────────────
    op.create_table(
        "law_enforcement_referrals",
        sa.Column("referral_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("referral_date", sa.String(length=10), nullable=False),
        sa.Column("agency_name", sa.String(length=100), nullable=False),
        sa.Column("referral_type", sa.String(length=30), nullable=False),
        sa.Column("referral_summary", sa.Text(), nullable=False),
        sa.Column("referral_contact_name", sa.String(length=255), nullable=False),
        sa.Column("submitted_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("submitted_at", sa.String(length=30), nullable=False),
        sa.Column("response_received_date", sa.String(length=10), nullable=True),
        sa.Column("referral_outcome", sa.String(length=20), nullable=True),
        sa.Column("outcome_notes", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.String(length=30), nullable=True),
        sa.ForeignKeyConstraint(["investigation_id"], ["siu_investigations.investigation_id"]),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("referral_id"),
    )
    op.create_index("ix_law_enforcement_referrals_inv",
                    "law_enforcement_referrals", ["investigation_id"])

    # ── siu_export_packages ──────────────────────────────────────────────
    op.create_table(
        "siu_export_packages",
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("package_json", sa.Text(), nullable=False),
        sa.Column("integrity_hash", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.String(length=30), nullable=False),
        sa.Column("generated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("delivery_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("delivery_destination", sa.String(length=255), nullable=True),
        sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_attempt_at", sa.String(length=30), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["investigation_id"], ["siu_investigations.investigation_id"]),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["opa_users.user_id"]),
        sa.PrimaryKeyConstraint("package_id"),
    )

    # ── opa_cases additions ──────────────────────────────────────────────
    with op.batch_alter_table("opa_cases") as batch_op:
        batch_op.add_column(sa.Column("siu_investigation_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("law_enforcement_hold", sa.Boolean(),
                                      nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("siu_frozen", sa.Boolean(),
                                      nullable=False, server_default=sa.text("0")))
        batch_op.create_foreign_key(
            "fk_opa_cases_siu_investigation",
            "siu_investigations",
            ["siu_investigation_id"],
            ["investigation_id"],
        )

    # ── documents additions ──────────────────────────────────────────────
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("investigation_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("investigation_note_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_documents_investigation",
            "siu_investigations",
            ["investigation_id"],
            ["investigation_id"],
        )
        batch_op.create_foreign_key(
            "fk_documents_investigation_note",
            "investigation_notes",
            ["investigation_note_id"],
            ["note_id"],
        )

    # ── Data renames: fwa → siu, investigator → siu_investigator ─────────
    op.execute("UPDATE apps SET app_name='siu', description='Special Investigation Unit — fraud, waste & abuse case management and external referrals' WHERE app_name='fwa'")
    op.execute("UPDATE roles SET role_name='siu_investigator', description='SIU investigator (alias siu_user) — opens investigations, attaches evidence, files law enforcement referrals' WHERE role_name='investigator'")


def downgrade() -> None:
    op.execute("UPDATE roles SET role_name='investigator' WHERE role_name='siu_investigator'")
    op.execute("UPDATE apps SET app_name='fwa' WHERE app_name='siu'")

    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint("fk_documents_investigation_note", type_="foreignkey")
        batch_op.drop_constraint("fk_documents_investigation", type_="foreignkey")
        batch_op.drop_column("investigation_note_id")
        batch_op.drop_column("investigation_id")

    with op.batch_alter_table("opa_cases") as batch_op:
        batch_op.drop_constraint("fk_opa_cases_siu_investigation", type_="foreignkey")
        batch_op.drop_column("siu_frozen")
        batch_op.drop_column("law_enforcement_hold")
        batch_op.drop_column("siu_investigation_id")

    op.drop_table("siu_export_packages")
    op.drop_index("ix_law_enforcement_referrals_inv", table_name="law_enforcement_referrals")
    op.drop_table("law_enforcement_referrals")
    op.drop_index("ix_investigation_notes_inv", table_name="investigation_notes")
    op.drop_table("investigation_notes")
    op.drop_table("investigation_cases")
    op.drop_index("ix_siu_investigations_assigned", table_name="siu_investigations")
    op.drop_index("ix_siu_investigations_status", table_name="siu_investigations")
    op.drop_table("siu_investigations")
