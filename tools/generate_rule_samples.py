"""Generate matched X12 835 / 837 sample pairs that exercise OPA's post-pay rules.

Workflow modelled (Phase 1):
  - The 835 (remittance, no diagnoses) creates a case in `awaiting_837` state.
    Only dx-INDEPENDENT rules run (DET-01/02/04/06/08); dx-dependent rules
    (DET-09/13/18/19, FWA LLM) are deferred.
  - The matching 837 (the claim) carries the diagnoses (HI segment) and the form
    type (837P → CMS-1500, 837I → UB-04). On link, OPA copies the Dx + claim-form
    metadata onto the claim, clears the gate, and re-runs the FULL suite — so the
    deferred rules now fire against real diagnoses.

All identifiers are REAL rows in the seeded demo DB. ICDs are written in X12 form
(no decimal point); OPA's parser normalizes them to the dotted reference form.

Run:  python tools/generate_rule_samples.py    →  tools/sample_x12/{835,837}_*.x12
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent / "sample_x12"

E = "*"      # element separator
SEG = "~"    # segment terminator


def _isa(date8: str) -> str:
    """Standard 106-char ISA so the parser's fixed offsets line up
    (elem sep at index 3, segment terminator at index 105)."""
    return E.join([
        "ISA",
        "00", " " * 10,
        "00", " " * 10,
        "ZZ", "PENGUIN".ljust(15),
        "ZZ", "PROVIDER".ljust(15),
        date8[2:], "1200", "U", "00501", "000000001", "0", "P", ":",
    ]) + SEG


# ── 835 builder (remittance — no diagnoses) ──────────────────────────────────

def build_835(*, era_number: str, payment_date: str, payer_name: str, claim: dict) -> str:
    total_paid = sum(s["paid"] for s in claim["svc_lines"])
    total_billed = sum(s["billed"] for s in claim["svc_lines"])
    out: list[str] = [_isa(payment_date)]
    out.append(E.join(["GS", "HP", "PENGUIN", "PROVIDER", payment_date, "1200", "1", "X", "005010X221A1"]) + SEG)
    out.append(E.join(["ST", "835", "0001"]) + SEG)
    out.append(E.join(["BPR", "C", f"{total_paid:.2f}", "C", "ACH", "CCP",
                       "01", "999999999", "DA", "1234567",
                       "1234567890", "", "01", "999999999", "DA", "9876543", payment_date]) + SEG)
    out.append(E.join(["TRN", "1", era_number, "1234567890"]) + SEG)
    out.append(E.join(["DTM", "405", payment_date]) + SEG)
    out.append(E.join(["N1", "PR", payer_name]) + SEG)
    out.append(E.join(["N1", "PE", "PROVIDER GROUP", "XX", "9900000001"]) + SEG)
    out.append(E.join(["LX", "1"]) + SEG)
    dos8 = claim["dos"].replace("-", "")
    out.append(E.join(["CLP", claim["pcn"], "1", f"{total_billed:.2f}", f"{total_paid:.2f}",
                       "0.00", "MC", claim["payer_claim_no"], "11"]) + SEG)
    out.append(E.join(["NM1", "QC", "1", claim["patient_last"], claim["patient_first"],
                       "", "", "", "MI", claim["member_number"]]) + SEG)
    out.append(E.join(["NM1", "82", "2", claim["provider_name"], "", "", "", "",
                       "XX", claim["provider_npi"]]) + SEG)
    out.append(E.join(["DTM", "232", dos8]) + SEG)
    for svc in claim["svc_lines"]:
        out.append(E.join(["SVC", "HC:" + svc["cpt"], f"{svc['billed']:.2f}", f"{svc['paid']:.2f}",
                           "", str(svc.get("units", 1))]) + SEG)
        out.append(E.join(["DTM", "472", dos8]) + SEG)
    out.append(E.join(["SE", str(len(out)), "0001"]) + SEG)
    out.append(E.join(["GE", "1", "1"]) + SEG)
    out.append(E.join(["IEA", "1", "000000001"]) + SEG)
    return "".join(out)


# ── 837 builder (the claim — carries diagnoses + form type) ──────────────────

def build_837(*, claim: dict, dob: str) -> str:
    inst = claim.get("institutional", False)
    dos8 = claim["dos"].replace("-", "")
    dob8 = dob.replace("-", "") if dob else ""
    version = "005010X223A2" if inst else "005010X222A1"
    out: list[str] = [_isa(dos8)]
    out.append(E.join(["GS", "HC", "PENGUIN", "PROVIDER", dos8, "1200", "1", "X", version]) + SEG)
    out.append(E.join(["ST", "837", "0001", version]) + SEG)
    out.append(E.join(["BHT", "0019", "00", claim["pcn"], dos8, "1200", "CH"]) + SEG)
    out.append(E.join(["NM1", "41", "2", "PROVIDER GROUP", "", "", "", "", "46", "PROVIDER"]) + SEG)
    out.append(E.join(["NM1", "40", "2", "PENGUIN HEALTH PLAN", "", "", "", "", "46", "PENGUIN"]) + SEG)
    out.append(E.join(["NM1", "85", "2", claim["provider_name"], "", "", "", "",
                       "XX", claim["provider_npi"]]) + SEG)
    out.append(E.join(["NM1", "IL", "1", claim["patient_last"], claim["patient_first"],
                       "", "", "", "MI", claim["member_number"]]) + SEG)
    if dob8:
        out.append(E.join(["DMG", "D8", dob8, "U"]) + SEG)
    billed_total = sum(s["billed"] for s in claim["svc_lines"])
    # CLM05 facility-code composite: institutional → "11:A:1" (type-of-bill 111);
    # professional → "11:B:1" (office).
    clm05 = "11:A:1" if inst else "11:B:1"
    out.append(E.join(["CLM", claim["pcn"], f"{billed_total:.2f}", "", "", clm05, "Y", "A", "Y", "Y"]) + SEG)
    # HI diagnoses: principal (ABK) then other (ABF); DRG (DR) for institutional.
    dx = claim["diagnoses"]
    hi = ["HI", "ABK:" + dx[0]] + ["ABF:" + d for d in dx[1:]]
    if inst and claim.get("drg"):
        hi.append("DR:" + claim["drg"])
    out.append(E.join(hi) + SEG)
    out.append(E.join(["DTP", "434", "D8", dos8]) + SEG)
    for i, svc in enumerate(claim["svc_lines"], start=1):
        out.append(E.join(["LX", str(i)]) + SEG)
        if inst:
            out.append(E.join(["SV2", svc.get("revenue_code", "0510"), "HC:" + svc["cpt"],
                               f"{svc['billed']:.2f}", "UN", str(svc.get("units", 1))]) + SEG)
        else:
            ptr = ":".join(str(p) for p in svc.get("dx_ptr", [1]))
            out.append(E.join(["SV1", "HC:" + svc["cpt"], f"{svc['billed']:.2f}", "UN",
                               str(svc.get("units", 1)), "11", "", ptr]) + SEG)
        out.append(E.join(["DTP", "472", "D8", dos8]) + SEG)
    out.append(E.join(["SE", str(len(out)), "0001"]) + SEG)
    out.append(E.join(["GE", "1", "1"]) + SEG)
    out.append(E.join(["IEA", "1", "000000001"]) + SEG)
    return "".join(out)


# ── Samples ──────────────────────────────────────────────────────────────────

EXCLUDED_NPI = "1972902351"
MIDWEST = ("MIDWEST CARDIAC AND SPECIALTY GROUP", "1111111111")
LAKESIDE = ("LAKESIDE MULTI SPECIALTY ASSOCIATES", "2222222222")
NORTHSHORE = ("NORTH SHORE REHABILITATION NETWORK", "3333333331")

SAMPLES = [
    {"id": "01_det08_excluded", "rule": "DET-08 excluded provider", "auto_837": True, "dob": "1955-08-19",
     "claim": {"pcn": "PAY-RS-0001", "payer_claim_no": "PHP-RS-0001", "member_number": "MA-000009",
               "patient_last": "Nakamura", "patient_first": "Gertrude",
               "provider_name": "EXCLUDED RENDERING PROVIDER", "provider_npi": EXCLUDED_NPI,
               "dos": "2026-06-10", "diagnoses": ["I10"],
               "svc_lines": [{"cpt": "99213", "billed": 95.00, "paid": 80.00, "dx_ptr": [1]}]}},

    {"id": "02_det04_feeschedule", "rule": "DET-04 fee overpay; 837 dx (M17.11) → DET-18 necessity MET",
     "auto_837": True, "dob": "1949-01-31",
     "claim": {"pcn": "PAY-RS-0002", "payer_claim_no": "PHP-RS-0002", "member_number": "MA-000010",
               "patient_last": "Benson", "patient_first": "Raymond",
               "provider_name": MIDWEST[0], "provider_npi": MIDWEST[1],
               "dos": "2026-06-11", "diagnoses": ["M1711"],
               "svc_lines": [{"cpt": "27447", "billed": 9800.00, "paid": 9300.00, "dx_ptr": [1]}]}},

    {"id": "03_det01_dup_a", "rule": "DET-01 duplicate — first", "auto_837": False, "dob": "1951-04-06",
     "claim": {"pcn": "PAY-RS-0003", "payer_claim_no": "PHP-RS-0003", "member_number": "MA-000016",
               "patient_last": "Frazier", "patient_first": "Herman",
               "provider_name": LAKESIDE[0], "provider_npi": LAKESIDE[1],
               "dos": "2026-06-20", "diagnoses": ["R079"],
               "svc_lines": [{"cpt": "99285", "billed": 250.00, "paid": 225.00, "dx_ptr": [1]}]}},

    {"id": "04_det01_dup_b", "rule": "DET-01 duplicate — second (fires)", "auto_837": False, "dob": "1951-04-06",
     "claim": {"pcn": "PAY-RS-0004", "payer_claim_no": "PHP-RS-0004", "member_number": "MA-000016",
               "patient_last": "Frazier", "patient_first": "Herman",
               "provider_name": LAKESIDE[0], "provider_npi": LAKESIDE[1],
               "dos": "2026-06-20", "diagnoses": ["R079"],
               "svc_lines": [{"cpt": "99285", "billed": 250.00, "paid": 225.00, "dx_ptr": [1]}]}},

    {"id": "05_det02_retro", "rule": "DET-02 retro-eligibility (service after coverage term)",
     "auto_837": True, "dob": "1946-05-23",
     "claim": {"pcn": "PAY-RS-0005", "payer_claim_no": "PHP-RS-0005", "member_number": "MA-000011",
               "patient_last": "Lorenz", "patient_first": "Agnes",
               "provider_name": MIDWEST[0], "provider_npi": MIDWEST[1],
               "dos": "2024-01-15", "diagnoses": ["I10"],
               "svc_lines": [{"cpt": "99213", "billed": 95.00, "paid": 80.00, "dx_ptr": [1]}]}},

    {"id": "06_det06_ncci", "rule": "DET-06 NCCI pair (97110+97112)", "auto_837": False, "dob": "2001-04-20",
     "claim": {"pcn": "PAY-RS-0006", "payer_claim_no": "PHP-RS-0006", "member_number": "MCD-000001",
               "patient_last": "Washington", "patient_first": "Destiny",
               "provider_name": NORTHSHORE[0], "provider_npi": NORTHSHORE[1],
               "dos": "2026-06-13", "diagnoses": ["M1711"],
               "svc_lines": [{"cpt": "97110", "billed": 60.00, "paid": 48.00, "dx_ptr": [1]},
                             {"cpt": "97112", "billed": 60.00, "paid": 48.00, "dx_ptr": [1]}]}},

    {"id": "07_det06_mue", "rule": "DET-06 MUE (97110 ×8)", "auto_837": True, "dob": "1974-05-07",
     "claim": {"pcn": "PAY-RS-0007", "payer_claim_no": "PHP-RS-0007", "member_number": "PPO-000011",
               "patient_last": "Thornton", "patient_first": "Eric",
               "provider_name": NORTHSHORE[0], "provider_npi": NORTHSHORE[1],
               "dos": "2026-06-14", "diagnoses": ["M1711"],
               "svc_lines": [{"cpt": "97110", "billed": 480.00, "paid": 396.00, "units": 8, "dx_ptr": [1]}]}},

    {"id": "08_det18_llm_fallback", "rule": "DET-18 LLM fallback (29881) w/ real dx M23.200",
     "auto_837": True, "dob": "1998-11-09",
     "claim": {"pcn": "PAY-RS-0008", "payer_claim_no": "PHP-RS-0008", "member_number": "MCD-000002",
               "patient_last": "Crawford", "patient_first": "Jaylen",
               "provider_name": NORTHSHORE[0], "provider_npi": NORTHSHORE[1],
               "dos": "2026-06-15", "diagnoses": ["M23200"],
               "svc_lines": [{"cpt": "29881", "billed": 1000.00, "paid": 900.00, "dx_ptr": [1]}]}},

    {"id": "09_det19_upcoding", "rule": "DET-19 LLM upcoding (99215 for I10 only)",
     "auto_837": True, "dob": "1991-02-25",
     "claim": {"pcn": "PAY-RS-0009", "payer_claim_no": "PHP-RS-0009", "member_number": "PPO-000012",
               "patient_last": "Vickers", "patient_first": "Amanda",
               "provider_name": LAKESIDE[0], "provider_npi": LAKESIDE[1],
               "dos": "2026-06-16", "diagnoses": ["I10"],
               "svc_lines": [{"cpt": "99215", "billed": 230.00, "paid": 200.00, "dx_ptr": [1]}]}},

    {"id": "10_combo", "rule": "Combo: DET-04 + DET-06 MUE + DET-09 unbundling + DET-19 + DET-18",
     "auto_837": False, "dob": "2005-07-14",
     "claim": {"pcn": "PAY-RS-0010", "payer_claim_no": "PHP-RS-0010", "member_number": "MCD-000003",
               "patient_last": "Monroe", "patient_first": "Aaliyah",
               "provider_name": MIDWEST[0], "provider_npi": MIDWEST[1],
               "dos": "2026-06-17", "diagnoses": ["M1711", "I10"],
               "svc_lines": [{"cpt": "27447", "billed": 5500.00, "paid": 5000.00, "dx_ptr": [1]},
                             {"cpt": "99215", "billed": 230.00, "paid": 200.00, "dx_ptr": [2]},
                             {"cpt": "99213", "billed": 300.00, "paid": 240.00, "units": 3, "dx_ptr": [2]}]}},

    {"id": "11_inst_ub04_det09", "rule": "837I → UB-04 Inpatient: DET-09 LLM (prof CPTs on facility bill)",
     "auto_837": True, "dob": "1995-03-02",
     "claim": {"pcn": "PAY-RS-0011", "payer_claim_no": "PHP-RS-0011", "member_number": "MCD-000004",
               "patient_last": "Tucker", "patient_first": "Isaiah",
               "provider_name": MIDWEST[0], "provider_npi": MIDWEST[1],
               "dos": "2026-06-18", "diagnoses": ["I2510"], "institutional": True,
               "bill_type": "111", "drg": "247",
               "svc_lines": [{"cpt": "93458", "billed": 1080.00, "paid": 1029.60, "revenue_code": "0481"},
                             {"cpt": "99233", "billed": 180.00, "paid": 160.00, "revenue_code": "0510"}]}},
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for s in SAMPLES:
        c = s["claim"]
        (OUT / f"835_{s['id']}.x12").write_text(build_835(
            era_number=f"ERA-RS-{s['id'][:2]}", payment_date=c["dos"].replace("-", ""),
            payer_name="PENGUIN HEALTH PLAN", claim=c))
        (OUT / f"837_{s['id']}.x12").write_text(build_837(claim=c, dob=s["dob"]))
        tag = "auto-load 837" if s["auto_837"] else "manual 837"
        form = "837I/UB-04" if c.get("institutional") else "837P"
        print(f"  ✓ {s['id']}  [{tag}, {form}]  dx={c['diagnoses']}  — {s['rule']}")
    print(f"\nWrote {len(SAMPLES)} pairs to {OUT}")


if __name__ == "__main__":
    main()
