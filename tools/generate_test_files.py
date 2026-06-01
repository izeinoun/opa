"""Generate test PDFs + X12 ERA files for ClaimGuard and PayGuard demos.

Outputs to opa/test_files/:

  ClaimGuard (pre-pay) — upload in this order per member:
    1) <member>_cms1500.pdf          → POST /api/prepay/claims/from-pdf
    2) <member>_encounter_notes.pdf  → upload as kind=medical_record, then "Recheck"

  PayGuard (post-pay):
    era_001_clean.x12       → single-claim 835, paid in full
    era_002_with_cas.x12    → multi-claim 835 with CAS adjustments
    era_001_remit.pdf       → human-readable remittance advice (visual companion)
    payguard_op_note.pdf    → supporting document for an existing case

The CMS-1500 PDFs aren't pixel-perfect government forms — they're text-form
intake documents whose layout matches what claimguard's LLM extractor reads.
Encounter notes are written to contain the language the evidence scanner
expects per the seeded `code_evidence_requirements` rows so re-scans land
clear 'found' results.
"""
from __future__ import annotations

from pathlib import Path
from fpdf import FPDF
from fpdf.enums import XPos, YPos

OUT = Path(__file__).resolve().parents[1] / "test_files"
OUT.mkdir(parents=True, exist_ok=True)


# fpdf2's core fonts (Helvetica/Courier) are Latin-1 only. Normalize the few
# Unicode punctuation marks we use into ASCII equivalents so we don't have to
# bundle a Unicode font for these demo PDFs.
_TRANSLATIONS = str.maketrans({
    "—": "--",    # em dash
    "–": "-",     # en dash
    "•": "-",     # bullet
    "‘": "'",     # left single quote
    "’": "'",     # right single quote
    "“": '"',     # left double quote
    "”": '"',     # right double quote
    "…": "...",   # ellipsis
    "°": " deg",  # degree symbol
    "≥": ">=",
    "≤": "<=",
})

def _ascii(s: str) -> str:
    return s.translate(_TRANSLATIONS)


# ── PDF helpers ─────────────────────────────────────────────────────────────

class Doc(FPDF):
    """Plain text-form PDF base class with a simple header/footer."""

    def __init__(self, title: str):
        super().__init__()
        self.title_txt = title
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(15, 15, 15)
        self.add_page()
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 8, _ascii(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        self.set_font("Helvetica", "", 9)
        self.ln(3)

    def heading(self, txt: str) -> None:
        self.ln(2)
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(230, 232, 240)
        self.cell(0, 6, _ascii(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_font("Helvetica", "", 9)
        self.ln(1)

    def kv(self, label: str, value: str) -> None:
        self.set_font("Helvetica", "B", 9)
        self.cell(48, 5, _ascii(f"{label}:"), new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 5, _ascii(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def para(self, txt: str) -> None:
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 5, _ascii(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def code_row(self, code: str, desc: str, amount: str = "") -> None:
        self.set_font("Courier", "", 9)
        self.cell(22, 5, _ascii(code), new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Helvetica", "", 9)
        self.cell(120, 5, _ascii(desc), new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Helvetica", "B", 9)
        self.cell(0, 5, _ascii(amount), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")


# ── CMS-1500 generator ──────────────────────────────────────────────────────

def cms1500(
    *,
    out_path: Path,
    patient_name: str,
    dob: str,
    member_number: str,
    provider_name: str,
    provider_npi: str,
    dos: str,
    pos_code: str,
    icd10: list[tuple[str, str]],          # [(code, description), …]
    cpts: list[tuple[str, str, int, float]],  # [(code, description, units, charge), …]
    billed_total: float,
    pcn: str,
) -> None:
    pdf = Doc("HEALTH INSURANCE CLAIM FORM (CMS-1500)")

    pdf.heading("CARRIER & PATIENT")
    pdf.kv("Carrier", "Penguin Health Plan")
    pdf.kv("Insurance Type", "Medicare Advantage")
    pdf.kv("Patient Name", patient_name)
    pdf.kv("Patient DOB", dob)
    pdf.kv("Patient ID / Member Number", member_number)
    pdf.kv("Patient Account Number", pcn)
    pdf.kv("Patient Sex", "M" if patient_name.split()[0] in {"Bernard"} else "F")

    pdf.heading("DIAGNOSIS CODES (ICD-10-CM)")
    for i, (code, desc) in enumerate(icd10, start=1):
        ptr = chr(64 + i)  # A, B, C, …
        pdf.code_row(f"{ptr}. {code}", desc)

    pdf.heading("SERVICES RENDERED")
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(22, 5, "Date", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(15, 5, "POS",  new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(22, 5, "CPT",  new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(80, 5, "Description", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(12, 5, "Units", new_x=XPos.RIGHT, new_y=YPos.TOP, align="C")
    pdf.cell(0, 5, "Charges", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
    pdf.set_font("Helvetica", "", 9)
    for cpt, desc, units, charge in cpts:
        pdf.cell(22, 5, dos, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(15, 5, pos_code, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Courier", "", 9)
        pdf.cell(22, 5, cpt, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(80, 5, desc[:55], new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(12, 5, str(units), new_x=XPos.RIGHT, new_y=YPos.TOP, align="C")
        pdf.cell(0, 5, f"${charge:,.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, f"TOTAL CHARGE: ${billed_total:,.2f}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")

    pdf.heading("BILLING PROVIDER")
    pdf.kv("Provider / Group", provider_name)
    pdf.kv("Billing NPI", provider_npi)
    pdf.kv("Federal Tax ID", "84-1234567")
    pdf.kv("Service Facility", provider_name)

    pdf.heading("CERTIFICATION")
    pdf.para(
        "I certify that the statements on the reverse apply to this bill and are "
        "made a part hereof. Signature of provider on file. Date of Service: " + dos + "."
    )

    pdf.output(str(out_path))


# ── Encounter notes generator ────────────────────────────────────────────────

def encounter_notes(
    *,
    out_path: Path,
    patient_name: str,
    dob: str,
    mrn: str,
    provider_name: str,
    dos: str,
    chief_complaint: str,
    hpi: str,
    pmh: str,
    exam: str,
    labs_imaging: str,
    assessment: list[str],   # list of bullet lines (each one supporting an ICD)
    plan: str,
    signed_by: str = "Dr. Elena Vasquez, MD",
) -> None:
    pdf = Doc("ENCOUNTER PROGRESS NOTE")

    pdf.heading("PATIENT")
    pdf.kv("Name", patient_name)
    pdf.kv("DOB", dob)
    pdf.kv("MRN", mrn)
    pdf.kv("Date of Service", dos)
    pdf.kv("Provider", provider_name)
    pdf.kv("Visit Type", "Office / Outpatient")

    pdf.heading("CHIEF COMPLAINT")
    pdf.para(chief_complaint)

    pdf.heading("HISTORY OF PRESENT ILLNESS")
    pdf.para(hpi)

    pdf.heading("PAST MEDICAL HISTORY")
    pdf.para(pmh)

    pdf.heading("PHYSICAL EXAMINATION")
    pdf.para(exam)

    pdf.heading("LABS / IMAGING")
    pdf.para(labs_imaging)

    pdf.heading("ASSESSMENT")
    for line in assessment:
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(5, 5, "-", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.multi_cell(0, 5, _ascii(line), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.heading("PLAN")
    pdf.para(plan)

    pdf.heading("PROVIDER SIGNATURE")
    pdf.para(f"Electronically signed by {signed_by} on {dos}.")

    pdf.output(str(out_path))


# ── Test-set data ────────────────────────────────────────────────────────────

TEST_MEMBERS = [
    {
        "key": "reyes",
        "patient_name": "Mildred Reyes",
        "dob": "1947-06-07",
        "member_number": "MA-000007",
        "mrn": "MRN-2026-0407",
        "provider_name": "Midwest Cardiac & Specialty Group",
        "provider_npi": "9900000001",
        "dos": "2026-04-15",
        "pos_code": "11",
        "pcn": "PCN-78421",
        "icd10": [
            ("I50.21", "Acute systolic (congestive) heart failure"),
            ("I10",    "Essential (primary) hypertension"),
        ],
        "cpts": [
            ("99223", "Initial hospital E/M, high complexity",      1, 295.00),
            ("93306", "Echo, complete with spectral and color Doppler", 1, 685.00),
            ("93000", "ECG, complete with interpretation",          1, 270.00),
        ],
        "billed_total": 1250.00,
        "encounter": {
            "chief_complaint":
                "Acute shortness of breath and lower-extremity swelling worsening "
                "over 4 days, with orthopnea and paroxysmal nocturnal dyspnea.",
            "hpi":
                "Mrs. Reyes is a 78-year-old female with longstanding heart failure "
                "who presents with progressively worsening dyspnea on exertion, now "
                "occurring with minimal activity (NYHA Class III). She reports 3-pillow "
                "orthopnea and PND that wakes her twice nightly. She has gained 6 lbs "
                "in 5 days and notes increased bilateral pedal edema up to the knees. "
                "No chest pain. Denies fever, cough, or recent travel.",
            "pmh":
                "Heart failure with reduced ejection fraction (HFrEF), hypertension, "
                "type 2 diabetes mellitus controlled on metformin. Prior MI 2019.",
            "exam":
                "BP 158/92, HR 98, RR 22, SpO2 92% on RA. Jugular venous distention "
                "to angle of jaw. Bilateral basilar crackles. S3 gallop audible. "
                "Bilateral 2+ pitting edema to the knees. No acute distress at rest.",
            "labs_imaging":
                "NT-proBNP elevated at 6,200 pg/mL (baseline ~1,800). Troponin "
                "negative x2. Creatinine 1.3, BUN 28. Echocardiogram performed: "
                "LVEF 30% (severely reduced), moderately dilated left ventricle, "
                "no regional wall motion abnormality beyond globally reduced "
                "function. Mild MR. ECG: sinus tachycardia, LBBB unchanged from "
                "prior. Chest X-ray: cardiomegaly with pulmonary vascular "
                "congestion and small bilateral pleural effusions.",
            "assessment": [
                "Acute decompensation of chronic systolic heart failure. The "
                "documented LVEF of 30% with new NYHA Class III symptoms, "
                "elevated NT-proBNP, and radiographic congestion support an "
                "acute systolic (congestive) heart failure exacerbation (I50.21).",
                "Hypertension, suboptimally controlled today in setting of "
                "volume overload (I10).",
            ],
            "plan":
                "IV furosemide 80 mg IV now, then 40 mg IV BID. Strict I/O monitoring. "
                "Daily weights. Increase carvedilol once euvolemic. Cardiology consult "
                "completed; agrees with management. Consider further uptitration of "
                "guideline-directed medical therapy on discharge.",
        },
    },
    {
        "key": "ostrowski",
        "patient_name": "Bernard Ostrowski",
        "dob": "1950-02-14",
        "member_number": "MA-000006",
        "mrn": "MRN-2026-0412",
        "provider_name": "Lakeside Multi-Specialty Associates",
        "provider_npi": "9900000002",
        "dos": "2026-04-22",
        "pos_code": "11",
        "pcn": "PCN-85103",
        "icd10": [
            ("J44.1", "COPD with (acute) exacerbation"),
            ("J18.9", "Pneumonia, unspecified organism"),
        ],
        "cpts": [
            ("99213", "Office E/M visit, established patient", 1, 165.00),
            ("71046", "Chest X-ray, 2 views",                  1, 220.00),
        ],
        "billed_total": 385.00,
        "encounter": {
            "chief_complaint":
                "3-day history of acute worsening of cough, increased purulent sputum, "
                "and dyspnea at rest.",
            "hpi":
                "Mr. Ostrowski is a 76-year-old male with established COPD (50 "
                "pack-year smoking history, on home oxygen 2 L NC) who presents with "
                "a 3-day acute exacerbation of his baseline shortness of breath. "
                "He reports increased cough with thick yellow-green sputum, low-grade "
                "fever to 100.8°F at home, and inability to walk to his mailbox "
                "without stopping. He has used his albuterol rescue inhaler every "
                "2 hours without relief.",
            "pmh":
                "Severe COPD (GOLD stage 3) on home O2, prior smoker (quit 2018), "
                "hypertension, hyperlipidemia.",
            "exam":
                "Temp 100.6°F, BP 132/78, HR 104, RR 24, SpO2 88% on 2L NC (baseline "
                "92% on 2L). Diffuse expiratory wheezes with prolonged expiratory "
                "phase. Scattered rhonchi bilaterally, more pronounced at the right "
                "lung base. Use of accessory muscles. No peripheral edema.",
            "labs_imaging":
                "Chest X-ray (CPT 71046): focal right lower lobe consolidation "
                "consistent with pneumonia, superimposed on chronic hyperinflation "
                "and flattened diaphragms. CBC: WBC 14.2 with left shift. "
                "Pulmonary function trended: documented baseline FEV1 38% predicted "
                "(severe obstruction) confirming underlying COPD.",
            "assessment": [
                "Acute exacerbation of severe COPD (J44.1). Documented baseline "
                "obstructive disease with acute worsening of dyspnea, increased "
                "sputum production, and hypoxia requiring treatment escalation "
                "beyond baseline therapy.",
                "Community-acquired pneumonia, right lower lobe (J18.9), "
                "confirmed by chest X-ray.",
            ],
            "plan":
                "Prednisone 40 mg PO daily x 5 days. Levofloxacin 750 mg PO daily x 7 "
                "days (covers CAP plus COPD exacerbation pathogens). Increase home O2 "
                "to 3 L NC. Albuterol/ipratropium nebs Q4H. Follow-up in 7 days; "
                "return precautions reviewed.",
        },
    },
    {
        "key": "kowalski",
        "patient_name": "Evelyn Kowalski",
        "dob": "1941-11-05",
        "member_number": "MA-000003",
        "mrn": "MRN-2026-0419",
        "provider_name": "Midwest Cardiac & Specialty Group",
        "provider_npi": "9900000001",
        "dos": "2026-04-28",
        "pos_code": "23",  # ER
        "pcn": "PCN-91207",
        "icd10": [
            ("A41.9", "Sepsis, unspecified organism"),
            ("N17.9", "Acute kidney injury, unspecified"),
            ("E86.0", "Dehydration"),
        ],
        "cpts": [
            ("99284", "ED visit, moderate-to-high complexity", 1, 540.00),
            ("36556", "Central venous catheter placement",      1, 350.00),
        ],
        "billed_total": 890.00,
        "encounter": {
            "chief_complaint":
                "Two-day history of fever, altered mental status, and decreased oral "
                "intake. Brought in by family for evaluation.",
            "hpi":
                "Mrs. Kowalski is an 84-year-old female who was in her usual state "
                "of health until 48 hours ago, when she developed subjective fevers, "
                "chills, and rigors. Her family reports she became progressively "
                "lethargic and confused, with poor oral intake. She has had two days "
                "of dysuria and urinary frequency, suggestive of a urinary source. "
                "No abdominal pain, no cough, no diarrhea.",
            "pmh":
                "Hypertension, mild cognitive impairment at baseline (alert, oriented "
                "x3), osteoarthritis. No prior history of sepsis. Baseline creatinine "
                "0.9 mg/dL per chart 2 months ago.",
            "exam":
                "Temp 102.1°F, BP 88/52 (hypotensive — baseline 130s/80s), HR 118, "
                "RR 22, SpO2 95% on RA. Patient is lethargic but arousable, oriented "
                "to person only (not place or time — change from baseline). Dry mucous "
                "membranes, tenting skin turgor. Mild suprapubic tenderness. No flank "
                "tenderness. Lungs clear. Heart tachycardic but regular. No focal "
                "neurologic deficit.",
            "labs_imaging":
                "WBC 18.5 with 92% neutrophils and bandemia. Serum lactate 3.2 mmol/L "
                "(elevated, normal <2.0). Procalcitonin 4.8 (elevated). Creatinine "
                "2.4 mg/dL — a sharp rise from baseline 0.9 within 48 hours, "
                "consistent with acute kidney injury (KDIGO Stage 2). BUN 52. "
                "Urinalysis: large leukocyte esterase, positive nitrites, >100 WBC "
                "per HPF — confirmed urinary source of infection. Blood cultures "
                "x 2 drawn prior to antibiotics. CXR clear.",
            "assessment": [
                "Sepsis, unspecified organism (A41.9). The patient meets SIRS "
                "criteria (fever, tachycardia, tachypnea, leukocytosis with "
                "bandemia) with a documented urinary source of infection and "
                "elevated lactate of 3.2. Hypotension and altered mental status "
                "are consistent with sepsis-induced organ dysfunction.",
                "Acute kidney injury (N17.9). Documented creatinine rise from "
                "baseline 0.9 to 2.4 mg/dL within 48 hours — meets KDIGO criteria "
                "(creatinine increase ≥0.3 mg/dL within 48h and ≥1.5x baseline "
                "within 7 days). Likely pre-renal in the setting of sepsis and "
                "volume depletion.",
                "Dehydration (E86.0).",
            ],
            "plan":
                "IV fluid bolus 2 L normal saline now. Broad-spectrum antibiotics: "
                "ceftriaxone 2 g IV (covers urinary pathogens). Central venous "
                "catheter placed via right internal jugular under ultrasound "
                "guidance for fluid resuscitation and vasopressor access if needed. "
                "Admit to step-down unit. Re-image lactate in 2 hours; reassess "
                "fluid status. Nephrology consult for AKI.",
        },
    },
]


def make_claimguard() -> None:
    for m in TEST_MEMBERS:
        cms_path = OUT / f"{m['key']}_cms1500.pdf"
        notes_path = OUT / f"{m['key']}_encounter_notes.pdf"
        cms1500(
            out_path=cms_path,
            patient_name=m["patient_name"],
            dob=m["dob"],
            member_number=m["member_number"],
            provider_name=m["provider_name"],
            provider_npi=m["provider_npi"],
            dos=m["dos"],
            pos_code=m["pos_code"],
            icd10=m["icd10"],
            cpts=m["cpts"],
            billed_total=m["billed_total"],
            pcn=m["pcn"],
        )
        encounter_notes(
            out_path=notes_path,
            patient_name=m["patient_name"],
            dob=m["dob"],
            mrn=m["mrn"],
            provider_name=m["provider_name"],
            dos=m["dos"],
            chief_complaint=m["encounter"]["chief_complaint"],
            hpi=m["encounter"]["hpi"],
            pmh=m["encounter"]["pmh"],
            exam=m["encounter"]["exam"],
            labs_imaging=m["encounter"]["labs_imaging"],
            assessment=m["encounter"]["assessment"],
            plan=m["encounter"]["plan"],
        )
        print(f"  ✓ {cms_path.name}")
        print(f"  ✓ {notes_path.name}")


# ── X12 835 generator ───────────────────────────────────────────────────────

def _x12_835(
    *,
    era_number: str,
    payment_date: str,             # YYYYMMDD
    payer_name: str,
    payment_total: float,
    claims: list[dict],            # see _build_clp below
) -> str:
    """Assemble a minimal but compliant 835 string. Returns the raw EDI text
    using '*' as element separator and '~' as segment terminator."""

    E = "*"
    SEG = "~"
    out: list[str] = []

    # ISA — 16 elements at fixed widths
    isa = E.join([
        "ISA",
        "00", " " * 10,           # ISA01 / ISA02 (auth)
        "00", " " * 10,           # ISA03 / ISA04 (security)
        "ZZ", "PENGUIN".ljust(15),
        "ZZ", "PROVIDER".ljust(15),
        payment_date[2:],         # 6-char date YYMMDD
        "1200",                   # 4-char time
        "U",                      # repetition sep (used as the 11th elem)
        "00501",
        "000000001",
        "0",                      # acknowledgement requested
        "P",                      # test indicator (P=production)
        ":",                      # subelem sep
    ])
    out.append(isa + SEG)

    # GS
    out.append(E.join([
        "GS", "HP", "PENGUIN", "PROVIDER", payment_date, "1200", "1", "X", "005010X221A1",
    ]) + SEG)

    # ST
    out.append(E.join(["ST", "835", "0001"]) + SEG)

    # BPR — payment / financial summary
    out.append(E.join([
        "BPR",
        "C", f"{payment_total:.2f}", "C", "ACH", "CCP",
        "01", "999999999", "DA", "1234567",
        "1234567890", "", "01", "999999999", "DA", "9876543", payment_date,
    ]) + SEG)

    # TRN — trace number (ERA number)
    out.append(E.join(["TRN", "1", era_number, "1234567890"]) + SEG)

    # DTM — payment effective date (qualifier 405 production date)
    out.append(E.join(["DTM", "405", payment_date]) + SEG)

    # N1 PR — payer
    out.append(E.join(["N1", "PR", payer_name]) + SEG)
    # N1 PE — payee
    out.append(E.join(["N1", "PE", "PROVIDER GROUP", "XX", "9900000001"]) + SEG)

    # LX — header for claims loop
    out.append(E.join(["LX", "1"]) + SEG)

    for c in claims:
        # CLP — claim payment
        out.append(E.join([
            "CLP",
            c["pcn"], "1",
            f"{c['billed']:.2f}", f"{c['paid']:.2f}", f"{c.get('pat_resp', 0.0):.2f}",
            "MC",                                  # claim filing indicator
            c["payer_claim_no"],
            "11",                                  # facility code (11=office)
        ]) + SEG)

        # NM1 QC — patient
        out.append(E.join([
            "NM1", "QC", "1",
            c["patient_last"], c["patient_first"],
            "", "", "",                            # middle, prefix, suffix
            "MI", c.get("patient_id", c["pcn"]),
        ]) + SEG)

        # NM1 82 — rendering provider
        out.append(E.join([
            "NM1", "82", "2", c["provider_name"], "", "", "", "",
            "XX", c["provider_npi"],
        ]) + SEG)

        # DTM 232 — claim statement period start (also serves as DOS hint)
        out.append(E.join(["DTM", "232", c["dos"].replace("-", "")]) + SEG)

        for svc in c["svc_lines"]:
            cpt_composite = "HC:" + svc["cpt"]
            if svc.get("modifier"):
                cpt_composite += ":" + svc["modifier"]
            out.append(E.join([
                "SVC", cpt_composite,
                f"{svc['billed']:.2f}", f"{svc['paid']:.2f}",
                "", str(svc.get("units", 1)),
            ]) + SEG)
            # DTM 472 — service date for the line
            out.append(E.join(["DTM", "472", c["dos"].replace("-", "")]) + SEG)
            for cas in svc.get("cas", []):
                out.append(E.join([
                    "CAS", cas["group"], cas["reason"], f"{cas['amount']:.2f}",
                ]) + SEG)

    # SE — segment count from ST through SE (inclusive). For demo files we just
    # report the actual count; OPA's parser doesn't enforce this strictly.
    segment_count = len(out) + 1 - 2  # subtract ISA + GS, add SE itself
    out.append(E.join(["SE", str(segment_count), "0001"]) + SEG)

    # GE / IEA
    out.append(E.join(["GE", "1", "1"]) + SEG)
    out.append(E.join(["IEA", "1", "000000001"]) + SEG)

    return "".join(out)


def make_payguard() -> None:
    # ERA 1 — single claim paid in full
    era1 = _x12_835(
        era_number="ERA-20260520-001",
        payment_date="20260520",
        payer_name="PENGUIN HEALTH PLAN",
        payment_total=865.00,
        claims=[{
            "pcn": "PAY-2026-0001",
            "billed": 865.00,
            "paid":   865.00,
            "pat_resp": 0.0,
            "payer_claim_no": "PHP00012345",
            "patient_last":  "Reyes",
            "patient_first": "Mildred",
            "patient_id": "MA-000007",
            "provider_name": "MIDWEST CARDIAC AND SPECIALTY GROUP",
            "provider_npi": "9900000001",
            "dos": "2026-05-15",
            "svc_lines": [
                {"cpt": "99214", "billed": 245.00, "paid": 245.00, "units": 1},
                {"cpt": "93000", "billed": 270.00, "paid": 270.00, "units": 1},
                {"cpt": "85025", "billed": 350.00, "paid": 350.00, "units": 1},
            ],
        }],
    )
    (OUT / "era_001_clean.x12").write_text(era1)
    print("  ✓ era_001_clean.x12")

    # ERA 2 — multi-claim with CAS adjustments
    era2 = _x12_835(
        era_number="ERA-20260521-007",
        payment_date="20260521",
        payer_name="PENGUIN HEALTH PLAN",
        payment_total=1410.00,
        claims=[
            {
                "pcn": "PAY-2026-0010",
                "billed": 1250.00,
                "paid":   985.00,
                "pat_resp": 0.0,
                "payer_claim_no": "PHP00098765",
                "patient_last":  "Ostrowski",
                "patient_first": "Bernard",
                "patient_id": "MA-000006",
                "provider_name": "LAKESIDE MULTI SPECIALTY ASSOCIATES",
                "provider_npi": "9900000002",
                "dos": "2026-05-18",
                "svc_lines": [
                    {"cpt": "99223", "billed": 295.00, "paid": 295.00, "units": 1},
                    # Pricing adjustment: paid less than billed.
                    {"cpt": "93306", "billed": 685.00, "paid": 490.00, "units": 1,
                     "cas": [{"group": "CO", "reason": "45", "amount": 195.00}]},
                    {"cpt": "93000", "billed": 270.00, "paid": 200.00, "units": 1,
                     "cas": [{"group": "CO", "reason": "45", "amount": 70.00}]},
                ],
            },
            {
                "pcn": "PAY-2026-0011",
                "billed": 540.00,
                "paid":   425.00,
                "pat_resp": 50.00,
                "payer_claim_no": "PHP00098766",
                "patient_last":  "Kowalski",
                "patient_first": "Evelyn",
                "patient_id": "MA-000003",
                "provider_name": "MIDWEST CARDIAC AND SPECIALTY GROUP",
                "provider_npi": "9900000001",
                "dos": "2026-05-19",
                "svc_lines": [
                    {"cpt": "99284", "billed": 540.00, "paid": 425.00, "units": 1,
                     "cas": [
                         {"group": "PR", "reason": "1",  "amount":  50.00},   # patient resp
                         {"group": "CO", "reason": "45", "amount":  65.00},   # contractual
                     ]},
                ],
            },
        ],
    )
    (OUT / "era_002_with_cas.x12").write_text(era2)
    print("  ✓ era_002_with_cas.x12")

    # Companion remittance advice (human-readable summary PDF for ERA 1)
    pdf = Doc("REMITTANCE ADVICE — Penguin Health Plan")
    pdf.heading("ERA SUMMARY")
    pdf.kv("ERA Number", "ERA-20260520-001")
    pdf.kv("Payment Date", "2026-05-20")
    pdf.kv("Payer", "Penguin Health Plan")
    pdf.kv("Total Payment", "$865.00")

    pdf.heading("CLAIM PAY-2026-0001 — Mildred Reyes (MA-000007)")
    pdf.kv("Provider", "Midwest Cardiac & Specialty Group (NPI 9900000001)")
    pdf.kv("Date of Service", "2026-05-15")
    pdf.kv("Payer Claim #", "PHP00012345")
    pdf.code_row("99214", "Office E/M, est. patient, level 4",        "$245.00")
    pdf.code_row("93000", "Electrocardiogram, complete",              "$270.00")
    pdf.code_row("85025", "CBC with automated differential",          "$350.00")
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Claim Total Billed: $865.00",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
    pdf.cell(0, 6, "Claim Total Paid:   $865.00",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
    pdf.cell(0, 6, "Patient Resp:       $0.00",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
    pdf.output(str(OUT / "era_001_remit.pdf"))
    print("  ✓ era_001_remit.pdf")

    # A supporting op-note PDF that PayGuard analysts can attach to a case
    op = Doc("OPERATIVE / PROCEDURE NOTE")
    op.heading("PATIENT")
    op.kv("Name", "Mildred Reyes")
    op.kv("DOB", "1947-06-07")
    op.kv("MRN", "MRN-2026-0501")
    op.kv("Date of Procedure", "2026-05-15")
    op.kv("Provider", "Dr. Elena Vasquez, MD")
    op.heading("INDICATION")
    op.para(
        "Patient with documented chronic systolic heart failure (LVEF 30%) "
        "presents for follow-up evaluation including 12-lead ECG and complete "
        "echocardiogram for serial assessment of cardiac function."
    )
    op.heading("PROCEDURES PERFORMED")
    op.code_row("99214", "Office E/M, established patient, level 4")
    op.code_row("93000", "Electrocardiogram, complete, with interpretation")
    op.code_row("85025", "Complete blood count with automated differential")
    op.heading("FINDINGS")
    op.para(
        "ECG: sinus rhythm, rate 78, LBBB unchanged from prior. CBC: WBC 7.2, "
        "Hgb 13.1, Plt 240. Echocardiogram (separately performed and "
        "interpreted): stable LVEF 30%, no new wall motion abnormality."
    )
    op.heading("IMPRESSION & PLAN")
    op.para(
        "Stable chronic systolic heart failure. Continue current GDMT regimen. "
        "Return in 3 months for repeat assessment."
    )
    op.heading("SIGNATURE")
    op.para("Electronically signed by Dr. Elena Vasquez, MD on 2026-05-15.")
    op.output(str(OUT / "payguard_op_note.pdf"))
    print("  ✓ payguard_op_note.pdf")


# ── Entrypoint ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("ClaimGuard test files (pre-pay):")
    make_claimguard()
    print()
    print("PayGuard test files (post-pay):")
    make_payguard()
    print()
    print(f"All files written to: {OUT}")
