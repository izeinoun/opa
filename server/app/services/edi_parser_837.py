"""Lightweight X12 837 (Health Care Claim) parser.

The 837 carries a *submitted* claim. In the File Intake flow an 837 is never
used to create a case — it's matched to an existing ERA-based (835) case on
member + service date and attached as supporting evidence.

Unlike the 835 remittance, the 837 DOES carry diagnoses (the 2300 HI segment:
principal ABK/BK + other ABF/BF, with line-level pointers in SV1). So besides
the matching keys (member id, name/DOB, service dates, CPTs) this parser also
extracts the diagnoses and the claim form type (837P → CMS-1500 professional,
837I → UB-04 institutional, with care setting / bill type / DRG). On link, the
case-creation service writes these onto the awaiting claim and re-runs the
diagnosis-dependent detectors.

Reuses the envelope normalization from edi_parser (the ISA/segment handling is
transaction-set agnostic). Tolerant of element-count variation like parse_835.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .edi_parser import _find_id, normalize_835

# Entity identifier qualifiers we treat as "the member" in 2010BA/2010CA loops:
#   IL = insured / subscriber, QC = patient.
_MEMBER_ENTITY_QUALIFIERS = {"IL", "QC"}

# DTP date qualifiers that denote a service / statement date.
#   472 = service date, 434/435 = statement (admit/discharge) dates,
#   096 = discharge hour (ignored — not D8), 090/091 = report period.
_SERVICE_DATE_QUALIFIERS = {"472", "434", "435", "090", "091"}

# HI diagnosis qualifiers. Principal first (ABK/BK), then other (ABF/BF). The
# institutional admitting (ABJ/BJ) and PoA variants are treated as "other".
_PRINCIPAL_DX_QUALIFIERS = {"ABK", "BK"}
_OTHER_DX_QUALIFIERS = {"ABF", "BF", "ABJ", "BJ"}
_DRG_QUALIFIERS = {"DR"}


@dataclass
class ServiceLine837:
    """One 2400 service line: a procedure code paired with its own date of
    service and the diagnosis codes pointed at by SV1's diagnosis-code-pointer
    composite (resolved against the claim's HI diagnosis list)."""
    cpt: str
    service_date: Optional[str] = None        # YYYY-MM-DD
    diagnoses: List[str] = field(default_factory=list)   # dotted ICD-10, in pointer order
    revenue_code: Optional[str] = None        # institutional (SV2) revenue code


@dataclass
class Parsed837:
    member_number: Optional[str] = None
    patient_first: str = ""
    patient_last: str = ""
    dob: Optional[str] = None                 # YYYY-MM-DD
    service_dates: List[str] = field(default_factory=list)   # all DTP dates, YYYY-MM-DD, sorted
    cpts: List[str] = field(default_factory=list)
    service_lines: List[ServiceLine837] = field(default_factory=list)  # per-line (cpt, dos, dx)
    # Diagnoses (dotted ICD-10), principal first then other, in HI order.
    diagnoses: List[str] = field(default_factory=list)
    principal_dx: Optional[str] = None
    # Claim-form metadata derived from the transaction variant.
    claim_type: str = "professional"          # professional | institutional
    claim_form_type: Optional[str] = None     # CMS-1500 | UB-04
    care_setting: Optional[str] = None        # Inpatient | Outpatient
    bill_type: Optional[str] = None           # UB-04 type-of-bill (e.g. 111)
    drg: Optional[str] = None


def _fmt_d8(raw: str) -> Optional[str]:
    """CCYYMMDD -> YYYY-MM-DD; returns None if not 8 digits."""
    raw = raw.strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return None


def _norm_icd(raw: str) -> Optional[str]:
    """Normalize an X12 ICD-10 code (no decimal point) to the dotted form the
    reference tables use: the decimal always falls after the 3rd character.
      M1711 -> M17.11 ; E119 -> E11.9 ; I10 -> I10 ; G43909 -> G43.909
    Accepts already-dotted input unchanged."""
    code = raw.strip().upper()
    if not code:
        return None
    if "." in code:
        return code
    if len(code) > 3:
        return f"{code[:3]}.{code[3:]}"
    return code


def _parse_dtp_dates(elems: List[str]) -> List[str]:
    """Pull YYYY-MM-DD dates from a DTP segment value.

    DTP*472*D8*20240115        -> ['2024-01-15']
    DTP*434*RD8*20240115-20240118 -> ['2024-01-15', '2024-01-18']
    """
    if len(elems) < 4:
        return []
    fmt = elems[2].strip().upper()
    value = elems[3].strip()
    out: List[str] = []
    if fmt == "RD8":
        for part in value.split("-"):
            d = _fmt_d8(part)
            if d:
                out.append(d)
    else:  # D8 (or anything else that looks like CCYYMMDD)
        d = _fmt_d8(value)
        if d:
            out.append(d)
    return out


def _parse_hi(elems: List[str]) -> tuple[list[str], list[str], Optional[str]]:
    """Parse an HI segment into (principal_dx_codes, other_dx_codes, drg).

    Each HI element is a composite 'qualifier:code[:...]'. We key on the
    qualifier to bucket principal vs other diagnoses (and pull a DRG if present).
    """
    principal: list[str] = []
    other: list[str] = []
    drg: Optional[str] = None
    for comp in elems[1:]:
        parts = comp.split(":")
        if len(parts) < 2:
            continue
        qual = parts[0].strip().upper()
        value = parts[1].strip()
        if not value:
            continue
        if qual in _DRG_QUALIFIERS:
            drg = value
        elif qual in _PRINCIPAL_DX_QUALIFIERS:
            icd = _norm_icd(value)
            if icd:
                principal.append(icd)
        elif qual in _OTHER_DX_QUALIFIERS:
            icd = _norm_icd(value)
            if icd:
                other.append(icd)
    return principal, other, drg


def _dx_pointers(elems: List[str]) -> List[int]:
    """SV1's diagnosis-code-pointer composite is SV1-07 (1-based element 7):
    'SV1*HC:99213*230*UN*1*11**2:1' -> [2, 1]. Returns the integer pointers."""
    if len(elems) < 8:
        return []
    out: List[int] = []
    for p in elems[7].split(":"):
        p = p.strip()
        if p.isdigit():
            out.append(int(p))
    return out


def parse_837(raw_edi: str) -> Parsed837:
    """Parse a raw X12 837 string into a Parsed837 (member + dates + CPTs + Dx)."""
    normalized = normalize_835(raw_edi)
    raw = normalized.replace("\n", "")
    elem_sep = raw[3]
    seg_term = raw[105]
    segments = [s.strip() for s in re.split(re.escape(seg_term), raw) if s.strip()]

    result = Parsed837()
    dates: set[str] = set()
    diagnoses: List[str] = []          # principal first, then other, HI order
    is_institutional = False
    bill_type: Optional[str] = None
    # Track the open 2400 service line so we can pair its DTP*472 / dx pointers.
    current: Optional[ServiceLine837] = None
    current_ptrs: List[int] = []
    lines: List[ServiceLine837] = []
    line_ptrs: List[List[int]] = []

    def _close_current() -> None:
        if current is not None:
            lines.append(current)
            line_ptrs.append(current_ptrs)

    for seg in segments:
        elems = seg.split(elem_sep)
        seg_id = elems[0].strip().upper()

        if seg_id in ("ST", "GS"):
            # Implementation convention reference: X222 = professional (837P),
            # X223 = institutional (837I / UB-04). Appears in ST03 or GS08.
            if any("X223" in e.upper() for e in elems):
                is_institutional = True

        elif seg_id == "NM1":
            qualifier = elems[1].strip().upper() if len(elems) > 1 else ""
            if qualifier in _MEMBER_ENTITY_QUALIFIERS:
                last = elems[3].strip() if len(elems) > 3 else ""
                first = elems[4].strip() if len(elems) > 4 else ""
                member_id = _find_id(elems)
                # QC (patient) wins over IL (subscriber) when both present, since
                # the claim's member of service is the patient. Don't clobber a
                # found member_number with an empty one.
                if member_id and (qualifier == "QC" or not result.member_number):
                    result.member_number = member_id
                if last and (qualifier == "QC" or not result.patient_last):
                    result.patient_last = last
                    result.patient_first = first

        elif seg_id == "DMG":
            # DMG*D8*19800101*M  → patient DOB
            if len(elems) > 2 and not result.dob:
                result.dob = _fmt_d8(elems[2])

        elif seg_id == "CLM":
            # CLM05 composite: facility-code : facility-qualifier : frequency.
            # For institutional this yields the type-of-bill (facility + freq).
            if is_institutional and len(elems) > 5:
                comp = elems[5].split(":")
                facility = comp[0].strip() if comp else ""
                freq = comp[2].strip() if len(comp) > 2 else ""
                if facility:
                    bill_type = (facility + freq)[:4]

        elif seg_id == "HI":
            principal, other, drg = _parse_hi(elems)
            for d in principal + other:
                if d not in diagnoses:
                    diagnoses.append(d)
            if drg and not result.drg:
                result.drg = drg

        elif seg_id == "DTP":
            qualifier = elems[1].strip() if len(elems) > 1 else ""
            parsed = _parse_dtp_dates(elems)
            for d in parsed:
                dates.add(d)
            # A line-level service date (DTP*472) belongs to the open service line.
            if qualifier == "472" and current is not None and current.service_date is None and parsed:
                current.service_date = parsed[0]

        elif seg_id in ("SV1", "SV2"):
            # SV1*HC:99213*... (professional) ; SV2*revcode*HC:99213*... (institutional)
            composite = ""
            ptrs: List[int] = []
            rev_code: Optional[str] = None
            if seg_id == "SV1":
                composite = elems[1] if len(elems) > 1 else ""
                ptrs = _dx_pointers(elems)
            else:  # SV2 — revenue code in element 1, procedure in the 2nd composite
                rev_code = elems[1].strip() if len(elems) > 1 else None
                composite = elems[2] if len(elems) > 2 else ""
                is_institutional = True
            parts = composite.split(":")
            # HC:99213 -> code is parts[1]; bare 99213 -> parts[0]
            code = (parts[1] if len(parts) > 1 else composite).strip()
            if code:
                if code not in result.cpts:
                    result.cpts.append(code)
                _close_current()            # finalize the previous line
                current = ServiceLine837(cpt=code, revenue_code=rev_code)
                current_ptrs = ptrs

    _close_current()

    result.service_dates = sorted(dates)
    result.diagnoses = diagnoses
    result.principal_dx = diagnoses[0] if diagnoses else None

    # Resolve each line's diagnoses from its SV1 pointers (1-based into the HI
    # list); fall back to the principal diagnosis when a line has no pointers.
    for ln, ptrs in zip(lines, line_ptrs):
        resolved = [diagnoses[i - 1] for i in ptrs if 0 < i <= len(diagnoses)]
        if not resolved and result.principal_dx:
            resolved = [result.principal_dx]
        ln.diagnoses = resolved

    # Backfill lines that carried no explicit DTP*472 with the claim's single
    # service date (common for one-encounter professional claims).
    if len(dates) == 1:
        only = next(iter(dates))
        for ln in lines:
            if ln.service_date is None:
                ln.service_date = only

    result.service_lines = lines

    # Claim-form metadata.
    if is_institutional:
        result.claim_type = "institutional"
        result.claim_form_type = "UB-04"
        result.bill_type = bill_type
        # Type-of-bill first two digits 11 = inpatient hospital → Inpatient.
        result.care_setting = "Inpatient" if (bill_type or "").startswith("11") else "Outpatient"
    else:
        result.claim_type = "professional"
        result.claim_form_type = "CMS-1500"
        result.care_setting = "Outpatient"

    return result
