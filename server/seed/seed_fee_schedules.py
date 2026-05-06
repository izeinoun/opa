"""Seed fee schedules and contract limitations — synchronous sqlite3.

Generates 135 fee schedule rows (3 orgs × 15 CPTs × 3 LOBs) and
7 contract limitations. Also writes a PDF rate card to seed/outputs/.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2024-01-01T08:00:00"
EFF_DATE = "2020-01-01"
TERM_DATE = "2099-12-31"

LOBS = ["MA", "PPO", "Medicaid"]

# Base rates per CPT (Medicare-like baseline)
CPT_BASE_RATES = {
    "99213": 77.00,
    "99214": 115.00,
    "99215": 155.00,
    "99232": 112.00,
    "93000": 19.00,
    "93306": 456.00,
    "93458": 1_320.00,
    "27447": 1_500.00,
    "29881": 840.00,
    "97110": 42.00,
    "97530": 48.00,
    "70553": 520.00,
    "72148": 380.00,
    "99285": 225.00,
    "99291": 610.00,
}

# LOB multipliers per org
LOB_MULTIPLIERS = {
    "9900000001": {"MA": 1.05, "PPO": 1.18, "Medicaid": 0.82},
    "9900000002": {"MA": 1.02, "PPO": 1.15, "Medicaid": 0.80},
    "9900000003": {"MA": 1.00, "PPO": 1.12, "Medicaid": 0.78},
}

# 7 contract limitations: (org_npi, cpt_code, limitation_type, limitation_value, description)
CONTRACT_LIMITATIONS = [
    ("9900000001", "93458", "prior_auth_required",  "mandatory",
     "Left heart catheterization requires prior authorization for all LOBs."),
    ("9900000001", "93306", "max_frequency",         "2_per_year",
     "Echocardiography limited to 2 studies per member per year without exception."),
    ("9900000001", "27447", "second_opinion",        "required",
     "Total knee arthroplasty requires documented second surgical opinion."),
    ("9900000002", "99215", "documentation_required","attestation",
     "High-complexity E&M requires clinician attestation of medical necessity."),
    ("9900000002", "99291", "place_of_service",      "inpatient_only",
     "Critical care codes valid only in inpatient or ICU setting."),
    ("9900000003", "97110", "max_units",             "4_per_day",
     "Therapeutic exercises capped at 4 units per day per member."),
    ("9900000003", "97530", "max_units",             "4_per_day",
     "Therapeutic activities capped at 4 units per day per member."),
]


def _write_pdf(org_rows: dict, out_path: Path) -> None:
    """Write a simple PDF rate card; falls back to a plain-text stub if reportlab absent."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
        from reportlab.lib import colors

        doc = SimpleDocTemplate(str(out_path), pagesize=letter,
                                topMargin=0.75*inch, bottomMargin=0.75*inch)
        styles = getSampleStyleSheet()
        story = []

        # Cover page
        story.append(Spacer(1, 2*inch))
        story.append(Paragraph("OPA Fee Schedule Rate Card", styles["Title"]))
        story.append(Paragraph("Effective January 1, 2024 – December 31, 2024", styles["Normal"]))
        story.append(Spacer(1, 0.5*inch))
        story.append(Paragraph(
            "This document contains contracted reimbursement rates for all participating provider "
            "organizations across Medicare Advantage (MA), PPO, and Medicaid lines of business. "
            "Rates are expressed as dollar amounts per unit of service.",
            styles["Normal"],
        ))
        story.append(PageBreak())

        # Per-org tables
        for org_npi, lob_data in org_rows.items():
            story.append(Paragraph(f"Provider Org NPI: {org_npi}", styles["Heading2"]))
            story.append(Spacer(1, 0.2*inch))

            header = ["CPT Code", "Description (abbreviated)", "MA Rate", "PPO Rate", "Medicaid Rate"]
            cpt_labels = {
                "99213": "Office visit – low complexity",
                "99214": "Office visit – moderate complexity",
                "99215": "Office visit – high complexity",
                "99232": "Subsequent hospital care",
                "93000": "ECG routine",
                "93306": "Echocardiography complete",
                "93458": "Left heart catheterization",
                "27447": "Total knee arthroplasty",
                "29881": "Knee arthroscopy with meniscectomy",
                "97110": "Therapeutic exercises (per 15 min)",
                "97530": "Therapeutic activities (per 15 min)",
                "70553": "MRI brain w/ and w/o contrast",
                "72148": "MRI lumbar spine w/o contrast",
                "99285": "ED visit – high complexity",
                "99291": "Critical care – first 30-74 min",
            }
            rows_data = [header]
            for cpt in sorted(CPT_BASE_RATES.keys()):
                rows_data.append([
                    cpt,
                    cpt_labels.get(cpt, cpt),
                    f"${lob_data['MA'].get(cpt, 0):.2f}",
                    f"${lob_data['PPO'].get(cpt, 0):.2f}",
                    f"${lob_data['Medicaid'].get(cpt, 0):.2f}",
                ])

            table = Table(rows_data, colWidths=[0.8*inch, 2.4*inch, 1*inch, 1*inch, 1.1*inch])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5f8a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ]))
            story.append(table)
            story.append(PageBreak())

        # Page numbering via onFirstPage/onLaterPages
        def add_page_num(canvas, doc):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.drawRightString(7.5*inch, 0.4*inch, f"Page {doc.page}")
            canvas.restoreState()

        doc.build(story, onFirstPage=add_page_num, onLaterPages=add_page_num)
        print(f"  PDF written → {out_path}")

    except ImportError:
        out_path.write_text(
            "Fee Schedule Rate Card\n"
            "reportlab not installed — plain-text stub\n\n"
            + "\n".join(
                f"Org {org_npi}: MA/PPO/Medicaid rates available"
                for org_npi in org_rows
            )
        )
        print(f"  PDF stub (no reportlab) → {out_path}")


def run(db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    try:
        if conn.execute("SELECT COUNT(*) FROM fee_schedules").fetchone()[0]:
            print("  fee_schedules already seeded — skipping")
            return 0

        org_rows: dict[str, dict[str, dict[str, float]]] = {}

        # Collect org IDs keyed by NPI
        org_map: dict[str, str] = {
            row[0]: row[1]
            for row in conn.execute("SELECT npi, provider_org_id FROM provider_orgs").fetchall()
        }

        inserted = 0
        for org_npi, multipliers in LOB_MULTIPLIERS.items():
            org_id = org_map.get(org_npi)
            if not org_id:
                continue
            org_rows[org_npi] = {lob: {} for lob in LOBS}
            for cpt, base in CPT_BASE_RATES.items():
                for lob in LOBS:
                    rate = round(base * multipliers[lob], 2)
                    org_rows[org_npi][lob][cpt] = rate
                    conn.execute(
                        "INSERT INTO fee_schedules "
                        "(fee_schedule_id, provider_org_id, lob, cpt_code, effective_date, "
                        "termination_date, base_rate, rate_basis, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (str(uuid4()), org_id, lob, cpt, EFF_DATE, TERM_DATE,
                         rate, "per_unit", NOW, NOW),
                    )
                    inserted += 1

        for org_npi, cpt, lim_type, lim_val, desc in CONTRACT_LIMITATIONS:
            org_id = org_map.get(org_npi)
            if not org_id:
                continue
            conn.execute(
                "INSERT INTO contract_limitations "
                "(limitation_id, provider_org_id, cpt_code, limitation_type, "
                "limitation_value, effective_date, description, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), org_id, cpt, lim_type, lim_val, EFF_DATE, desc, NOW, NOW),
            )

        conn.commit()

        # Write PDF
        out_dir = Path(db_path).parent / "seed" / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_pdf(org_rows, out_dir / "fee_schedule_rate_card.pdf")

        print(f"  Inserted {inserted} fee schedule rows, {len(CONTRACT_LIMITATIONS)} contract limitations")
        return inserted
    finally:
        conn.close()


if __name__ == "__main__":
    run()
