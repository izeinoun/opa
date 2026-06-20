"""Lightweight X12 837 (Health Care Claim) parser.

The 837 carries a *submitted* claim. In the File Intake flow an 837 is never
used to create a case — it's matched to an existing ERA-based case on member +
service date and attached as supporting evidence. So this parser only extracts
what matching needs: the subscriber/patient member identifier, the patient
name + DOB, every service date on the claim, and the billed CPT/HCPCS codes.

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


@dataclass
class ServiceLine837:
    """One 2400 service line: a procedure code paired with its own date of
    service (the line-level DTP*472, or the claim's single service date when the
    line carries no explicit DTP)."""
    cpt: str
    service_date: Optional[str] = None        # YYYY-MM-DD


@dataclass
class Parsed837:
    member_number: Optional[str] = None
    patient_first: str = ""
    patient_last: str = ""
    dob: Optional[str] = None                 # YYYY-MM-DD
    service_dates: List[str] = field(default_factory=list)   # all DTP dates, YYYY-MM-DD, sorted
    cpts: List[str] = field(default_factory=list)
    service_lines: List[ServiceLine837] = field(default_factory=list)  # per-line (cpt, dos)


def _fmt_d8(raw: str) -> Optional[str]:
    """CCYYMMDD -> YYYY-MM-DD; returns None if not 8 digits."""
    raw = raw.strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return None


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


def parse_837(raw_edi: str) -> Parsed837:
    """Parse a raw X12 837 string into a Parsed837 (member + dates + CPTs)."""
    normalized = normalize_835(raw_edi)
    raw = normalized.replace("\n", "")
    elem_sep = raw[3]
    seg_term = raw[105]
    segments = [s.strip() for s in re.split(re.escape(seg_term), raw) if s.strip()]

    result = Parsed837()
    dates: set[str] = set()
    # Track the open 2400 service line so we can pair its DTP*472 to its SV1/SV2.
    current: Optional[ServiceLine837] = None
    lines: List[ServiceLine837] = []

    for seg in segments:
        elems = seg.split(elem_sep)
        seg_id = elems[0].strip().upper()

        if seg_id == "NM1":
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
            if seg_id == "SV1":
                composite = elems[1] if len(elems) > 1 else ""
            else:  # SV2 — procedure is in the 2nd composite element
                composite = elems[2] if len(elems) > 2 else ""
            parts = composite.split(":")
            # HC:99213 -> code is parts[1]; bare 99213 -> parts[0]
            code = (parts[1] if len(parts) > 1 else composite).strip()
            if code:
                if code not in result.cpts:
                    result.cpts.append(code)
                # Open a new service line (finalizing the previous one).
                if current is not None:
                    lines.append(current)
                current = ServiceLine837(cpt=code)

    if current is not None:
        lines.append(current)

    result.service_dates = sorted(dates)

    # Backfill lines that carried no explicit DTP*472 with the claim's single
    # service date (common for one-encounter professional claims). Multi-date
    # claims keep each line's own date; if the date is ambiguous, leave it null.
    if len(dates) == 1:
        only = next(iter(dates))
        for ln in lines:
            if ln.service_date is None:
                ln.service_date = only

    result.service_lines = lines
    return result
