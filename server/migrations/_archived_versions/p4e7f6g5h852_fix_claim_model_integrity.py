"""Fix claim model integrity

- ClaimLine: replace icd_codes (TEXT/JSON) with diag_1..diag_4 (String cols)
- ClaimLine: add modifier_3, modifier_4
- Claim: add source_type, submitter_npi, claim_frequency_code
- ClaimPayment835: add claim_id + claim_line_id FKs, drop adjustment_reason_code
- New era_adjustment_codes table (one CAS triplet per row)
- Drop claim_headers_837 table (data migrated into claims)

Revision ID: p4e7f6g5h852
Revises: o3d6e5f4g740
Create Date: 2026-06-05
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "p4e7f6g5h852"
down_revision = "a3014f73b8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. claims: add source_type, submitter_npi, claim_frequency_code ──────
    with op.batch_alter_table("claims") as bop:
        bop.add_column(sa.Column("source_type", sa.String(20), nullable=True))
        bop.add_column(sa.Column("submitter_npi", sa.String(20), nullable=True))
        bop.add_column(sa.Column("claim_frequency_code", sa.String(5), nullable=True))

    # ── 2. backfill claims from claim_headers_837 ────────────────────────────
    try:
        headers = conn.execute(sa.text(
            "SELECT claim_icn, submitter_npi, claim_frequency_code FROM claim_headers_837"
        )).fetchall()
        for h in headers:
            conn.execute(sa.text(
                "UPDATE claims SET submitter_npi=:npi, claim_frequency_code=:freq, source_type='x12_837' "
                "WHERE icn=:icn"
            ), {"npi": h[1], "freq": h[2], "icn": h[0]})
    except Exception:
        pass  # table may already be gone on a fresh DB

    # ── 3. claim_lines: add diag_1..4 + modifier_3/4 ────────────────────────
    with op.batch_alter_table("claim_lines") as bop:
        bop.add_column(sa.Column("diag_1", sa.String(10), nullable=True))
        bop.add_column(sa.Column("diag_2", sa.String(10), nullable=True))
        bop.add_column(sa.Column("diag_3", sa.String(10), nullable=True))
        bop.add_column(sa.Column("diag_4", sa.String(10), nullable=True))
        bop.add_column(sa.Column("modifier_3", sa.String(5), nullable=True))
        bop.add_column(sa.Column("modifier_4", sa.String(5), nullable=True))

    # ── 4. backfill diag_1..4 from icd_codes JSON ───────────────────────────
    try:
        rows = conn.execute(sa.text(
            "SELECT claim_line_id, icd_codes FROM claim_lines"
        )).fetchall()
        for row in rows:
            try:
                codes = json.loads(row[1] or "[]") if row[1] else []
            except Exception:
                codes = []
            conn.execute(sa.text(
                "UPDATE claim_lines SET diag_1=:d1, diag_2=:d2, diag_3=:d3, diag_4=:d4 "
                "WHERE claim_line_id=:id"
            ), {
                "d1": codes[0] if len(codes) > 0 else None,
                "d2": codes[1] if len(codes) > 1 else None,
                "d3": codes[2] if len(codes) > 2 else None,
                "d4": codes[3] if len(codes) > 3 else None,
                "id": row[0],
            })
    except Exception:
        pass  # icd_codes may not exist on a fresh DB

    # ── 5. drop icd_codes from claim_lines ──────────────────────────────────
    try:
        with op.batch_alter_table("claim_lines") as bop:
            bop.drop_column("icd_codes")
    except Exception:
        pass  # already absent

    # ── 6. create era_adjustment_codes ──────────────────────────────────────
    op.create_table(
        "era_adjustment_codes",
        sa.Column("adjustment_id", sa.String(36), primary_key=True),
        sa.Column("payment_id", sa.String(36),
                  sa.ForeignKey("claim_payments_835.payment_id"), nullable=False),
        sa.Column("group_code", sa.String(2), nullable=False),
        sa.Column("reason_code", sa.String(10), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=True),
        sa.Column("sequence", sa.Integer, nullable=False, server_default="1"),
    )

    # ── 7. migrate existing adjustment_reason_code rows ─────────────────────
    try:
        pays = conn.execute(sa.text(
            "SELECT payment_id, adjustment_amount, adjustment_reason_code "
            "FROM claim_payments_835 WHERE adjustment_reason_code IS NOT NULL"
        )).fetchall()
        for pay in pays:
            raw = pay[2]
            if not raw:
                continue
            parts = raw.split("-", 1)
            group = parts[0] if len(parts) >= 1 else "CO"
            reason = parts[1] if len(parts) >= 2 else raw
            conn.execute(sa.text(
                "INSERT INTO era_adjustment_codes "
                "(adjustment_id, payment_id, group_code, reason_code, amount, sequence) "
                "VALUES (:aid, :pid, :gc, :rc, :amt, 1)"
            ), {
                "aid": str(uuid.uuid4()),
                "pid": pay[0],
                "gc": group[:2],
                "rc": reason[:10],
                "amt": pay[1],
            })
    except Exception:
        pass

    # ── 8. claim_payments_835: add claim_id + claim_line_id ─────────────────
    with op.batch_alter_table("claim_payments_835") as bop:
        bop.add_column(sa.Column("claim_id", sa.String(36), nullable=True))
        bop.add_column(sa.Column("claim_line_id", sa.String(36), nullable=True))

    # ── 9. backfill claim_id on payments ────────────────────────────────────
    conn.execute(sa.text(
        "UPDATE claim_payments_835 "
        "SET claim_id = ("
        "  SELECT claim_id FROM claims WHERE claims.icn = claim_payments_835.claim_icn"
        ")"
    ))

    # ── 10. drop adjustment_reason_code from claim_payments_835 ─────────────
    try:
        with op.batch_alter_table("claim_payments_835") as bop:
            bop.drop_column("adjustment_reason_code")
    except Exception:
        pass  # already absent

    # ── 11. drop claim_headers_837 ───────────────────────────────────────────
    try:
        op.drop_table("claim_headers_837")
    except Exception:
        pass  # already absent


def downgrade() -> None:
    # Restore claim_headers_837 as empty shell (data is lost).
    op.create_table(
        "claim_headers_837",
        sa.Column("header_id", sa.String(36), primary_key=True),
        sa.Column("claim_icn", sa.String(100), unique=True),
        sa.Column("submitter_npi", sa.String(20)),
        sa.Column("billing_provider_npi", sa.String(20)),
        sa.Column("submission_date", sa.String(10)),
        sa.Column("total_billed", sa.Float),
        sa.Column("claim_frequency_code", sa.String(5)),
        sa.Column("raw_837_json", sa.Text),
        sa.Column("created_at", sa.String(30)),
    )

    with op.batch_alter_table("claim_payments_835") as bop:
        bop.add_column(sa.Column("adjustment_reason_code", sa.String(20), nullable=True))
        bop.drop_column("claim_id")
        bop.drop_column("claim_line_id")

    op.drop_table("era_adjustment_codes")

    with op.batch_alter_table("claim_lines") as bop:
        bop.add_column(sa.Column("icd_codes", sa.Text, server_default="[]"))
        bop.drop_column("diag_1")
        bop.drop_column("diag_2")
        bop.drop_column("diag_3")
        bop.drop_column("diag_4")
        bop.drop_column("modifier_3")
        bop.drop_column("modifier_4")

    with op.batch_alter_table("claims") as bop:
        bop.drop_column("source_type")
        bop.drop_column("submitter_npi")
        bop.drop_column("claim_frequency_code")
