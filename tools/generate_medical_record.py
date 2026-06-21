"""Generate a clinical medical-record PDF that substantiates the billed services
on case OPA-2026-00039 (member MCD-000003), so the EVIDENCE / documentation pass
(AI-EVIDENCE-V1) clears its "no documentation on file" findings.

This deliberately does NOT try to clear the CODING findings (DET-18 medical
necessity by codes, DET-06 MUE, DET-09 same-day E/M) — those are a separate audit
layer and correctly persist. The record only supplies the chart evidence the
documentation layer was looking for: operative report, pre-op imaging, failed
conservative management, E/M documentation, and hypertension management.

The record carries the member identifiers + service lines so the "medical" intake
flow (extract identifiers → match on member + CPT/DoS) links it to case 39.

Run:  python tools/generate_medical_record.py  →  tools/sample_x12/medrec_case39.pdf
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_test_files import Doc  # reuse the PDF helper (fpdf-based)

OUT = Path(__file__).resolve().parent / "sample_x12" / "medrec_case39.pdf"

# Case 39 anchors (must match for intake to link the record to the case).
PATIENT = "Aaliyah Monroe"
DOB = "2005-07-14"
MEMBER = "MCD-000003"
DOS = "2026-06-17"


def main() -> None:
    p = Doc("MEDICAL RECORD — ORTHOPEDIC SURGERY & PERIOPERATIVE CARE")

    p.heading("PATIENT")
    p.kv("Patient Name", PATIENT)
    p.kv("Date of Birth", DOB)
    p.kv("Member / Plan ID", MEMBER)
    p.kv("Date of Service", DOS)
    p.kv("Rendering Provider", "Paul Eriksson, MD — Orthopedic Surgery")

    p.heading("CHIEF COMPLAINT & HISTORY OF PRESENT ILLNESS")
    p.para(
        "21-year-old patient with severe, end-stage POST-TRAUMATIC osteoarthritis of "
        "the RIGHT knee. History of a high-energy tibial plateau fracture 4 years prior "
        "(MVA), treated with ORIF, complicated by post-traumatic arthrosis with "
        "progressive bone-on-bone degeneration. Despite the young age, the joint is "
        "non-salvageable; total knee arthroplasty is indicated for post-traumatic "
        "etiology, not primary age-related osteoarthritis."
    )

    p.heading("PRE-OPERATIVE IMAGING")
    p.para(
        "Weight-bearing radiographs of the RIGHT knee (3 views) dated prior to surgery: "
        "Tricompartmental joint-space obliteration, subchondral sclerosis and cyst "
        "formation, marginal osteophytes, and post-traumatic articular incongruity of "
        "the lateral tibial plateau. Kellgren-Lawrence grade 4. Findings consistent with "
        "ICD-10 M17.11 (unilateral primary/post-traumatic osteoarthritis, right knee)."
    )

    p.heading("FAILED CONSERVATIVE MANAGEMENT (>12 MONTHS)")
    p.para(
        "Documented failure of: structured physical therapy (16 visits over 6 months), "
        "two intra-articular corticosteroid injections, a course of viscosupplementation, "
        "NSAIDs, activity modification, and an unloader brace. Persistent mechanical "
        "symptoms, effusion, and inability to ambulate without assistance."
    )

    p.heading("OPERATIVE REPORT — CPT 27447")
    p.kv("Procedure", "Total knee arthroplasty, right (CPT 27447)")
    p.kv("Pre-op Diagnosis", "Post-traumatic osteoarthritis, right knee (M17.11)")
    p.kv("Anesthesia", "Spinal with adductor canal block")
    p.para(
        "Standard medial parapatellar approach. Severe tricompartmental degeneration "
        "with post-traumatic deformity confirmed intra-operatively. Femoral, tibial, and "
        "patellar resurfacing performed; cemented posterior-stabilized implant placed; "
        "trial range of motion 0-120 degrees with stable ligamentous balance. EBL minimal. "
        "Patient tolerated the procedure well; no complications. Operative note dictated "
        "and signed by Dr. Eriksson."
    )

    p.heading("OFFICE EVALUATION & MANAGEMENT — CPT 99215 (HIGH COMPLEXITY)")
    p.para(
        "High-complexity MDM supporting a level-5 established-patient E/M: TWO chronic "
        "illnesses managed — (1) post-traumatic osteoarthritis with surgical planning, and "
        "(2) essential hypertension (I10). Data reviewed: outside ORIF operative records, "
        "prior imaging, PT notes, and labs. Risk: decision for major elective surgery with "
        "perioperative anticoagulation and anesthesia clearance — high morbidity risk. "
        "Extended counseling on surgical vs non-surgical options and post-op expectations."
    )

    p.heading("HYPERTENSION MANAGEMENT — ICD-10 I10")
    p.para(
        "Essential hypertension, in-office BP 148/92. Lisinopril increased from 10 mg to "
        "20 mg daily; pre-operative cardiac risk reviewed and optimized. Counseled on diet, "
        "home BP monitoring, and medication adherence. Follow-up in 2 weeks."
    )

    p.heading("ASSESSMENT & PLAN")
    p.para(
        "1) M17.11 post-traumatic OA, right knee — status post total knee arthroplasty "
        "(27447); weight-bearing as tolerated, DVT prophylaxis, PT. "
        "2) I10 essential hypertension — medication titrated, optimized for surgery."
    )

    p.heading("SERVICES DOCUMENTED THIS ENCOUNTER")
    p.code_row("27447", "Total knee arthroplasty, right")
    p.code_row("99215", "Office/outpatient visit, established, high complexity")
    p.code_row("99213", "Office/outpatient visit, established, low/moderate")
    p.kv("Date of Service", DOS)

    p.heading("ATTESTATION")
    p.para(
        f"I attest that the above documentation is complete and accurate for the "
        f"services rendered to {PATIENT} ({MEMBER}) on {DOS}. Electronically signed, "
        f"Paul Eriksson, MD, Orthopedic Surgery."
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    p.output(str(OUT))
    print(f"  wrote {OUT}")


if __name__ == "__main__":
    main()
