"""Evidence scanner — per-document text + code requirements + findings.

Revision ID: m3h4i5j6k7l8
Revises: l2g3h4i5j6k7
Create Date: 2026-05-30

Adds the storage layer for the medical-record evidence scanner:

  documents.extracted_text        per-document PDF text (was only on claims)
  documents.extraction_status     pending|complete|failed
  documents.extracted_at          when text extraction last completed
  documents.page_count            int, used by frontend PDF viewer

  code_evidence_requirements      configurable rules: which ICD-10/DRG codes
                                  require documentary evidence, and a short
                                  description used in the scan prompt

  evidence_findings               per (claim, code) scan result with the
                                  verbatim quote, document_id, page_number,
                                  section heading, alternates JSON, and a
                                  gap description when nothing was found

create_all-compatible: all NOT NULL columns either have a server_default,
or are populated by the scanner/extractor at insert time.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m3h4i5j6k7l8"
down_revision: Union[str, None] = "l2g3h4i5j6k7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. per-document extracted text ─────────────────────────────────────
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("extracted_text", sa.Text(), nullable=True))
        batch.add_column(sa.Column("extracted_at", sa.String(length=30), nullable=True))
        batch.add_column(sa.Column(
            "extraction_status", sa.String(length=20), nullable=True,
        ))
        batch.add_column(sa.Column("page_count", sa.Integer(), nullable=True))

    # ── 2. code_evidence_requirements ──────────────────────────────────────
    op.create_table(
        "code_evidence_requirements",
        sa.Column("requirement_id", sa.String(length=36), nullable=False),
        sa.Column("code_type", sa.String(length=10), nullable=False),  # icd10|drg
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("requirement_description", sa.Text(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("created_at", sa.String(length=30), nullable=False),
        sa.Column("updated_at", sa.String(length=30), nullable=False),
        sa.PrimaryKeyConstraint("requirement_id"),
        sa.UniqueConstraint("code_type", "code", name="uq_code_evidence_req_code"),
    )
    op.create_index(
        "idx_code_evidence_req_lookup", "code_evidence_requirements",
        ["code_type", "code", "is_active"],
    )

    # ── 3. evidence_findings ───────────────────────────────────────────────
    op.create_table(
        "evidence_findings",
        sa.Column("finding_id", sa.String(length=36), nullable=False),
        sa.Column("claim_id", sa.String(length=36), nullable=False),
        # Document where the evidence was located — nullable for not_found.
        sa.Column("document_id", sa.String(length=36), nullable=True),
        # Optional link back to the requirement that drove the scan; nullable
        # for ad-hoc scans on codes that have no registered requirement yet.
        sa.Column("requirement_id", sa.String(length=36), nullable=True),
        sa.Column("code_type", sa.String(length=10), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        # found | not_found | partial
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.String(length=10), nullable=True),  # high|medium|low
        # Verbatim quote from the document text. NULL when result=not_found.
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_heading", sa.String(length=200), nullable=True),
        # JSON list of additional locations: [{document_id, page_number,
        # section_heading, evidence_text}].
        sa.Column(
            "additional_sources", sa.Text(), nullable=False,
            server_default="[]",
        ),
        sa.Column("gap_description", sa.Text(), nullable=True),
        sa.Column("model_used", sa.String(length=80), nullable=True),
        sa.Column("scanned_at", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.claim_id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.document_id"]),
        sa.ForeignKeyConstraint(
            ["requirement_id"], ["code_evidence_requirements.requirement_id"],
        ),
        sa.PrimaryKeyConstraint("finding_id"),
        # Re-scans upsert on this pair — one row per (claim, code).
        sa.UniqueConstraint("claim_id", "code_type", "code", name="uq_evidence_finding_code"),
    )
    op.create_index(
        "idx_evidence_findings_claim", "evidence_findings",
        ["claim_id", "code_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_evidence_findings_claim", table_name="evidence_findings")
    op.drop_table("evidence_findings")
    op.drop_index("idx_code_evidence_req_lookup", table_name="code_evidence_requirements")
    op.drop_table("code_evidence_requirements")
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("page_count")
        batch.drop_column("extraction_status")
        batch.drop_column("extracted_at")
        batch.drop_column("extracted_text")
