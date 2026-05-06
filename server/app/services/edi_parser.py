"""Lightweight X12 835 Health Care Claim Payment/Advice parser.

Extracts only the fields needed to create an OPA case.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

# Fixed widths for each of the 16 ISA data elements (ISA01–ISA16)
_ISA_WIDTHS = [2, 10, 2, 10, 2, 15, 2, 15, 6, 4, 1, 5, 9, 1, 1, 1]


@dataclass
class ParsedSvcLine:
    cpt_code: str
    modifier: Optional[str]
    billed_amount: float
    paid_amount: float
    units: int = 1
    service_date: Optional[str] = None
    adjustment_reason_code: Optional[str] = None
    adjustment_amount: float = 0.0


@dataclass
class ParsedClaim:
    patient_control_number: str
    billed: float
    paid: float
    patient_responsibility: float
    payer_claim_number: Optional[str]
    patient_first: str = ""
    patient_last: str = ""
    patient_id: Optional[str] = None        # member_number
    rendering_npi: Optional[str] = None
    rendering_name: Optional[str] = None
    service_date: Optional[str] = None
    svc_lines: List[ParsedSvcLine] = field(default_factory=list)


@dataclass
class Parsed835:
    era_number: str
    payer_name: str
    payment_amount: float
    payment_date: str                        # YYYY-MM-DD
    claims: List[ParsedClaim] = field(default_factory=list)


# ── Normalizer ────────────────────────────────────────────────────────────────

def normalize_835(raw_edi: str) -> str:
    """
    Normalize a raw X12 835 into clean, properly-padded single-line format.

    Handles:
    - Multi-line paste where each segment ends with ~\\n
    - Newline-only delimited files (no ~ at all)
    - Windows (\\r\\n), Unix (\\n), and Mac (\\r) line endings
    - ISA elements that are under-padded (truncated sender/receiver IDs)
    - Segment IDs in mixed case
    """
    text = raw_edi.strip()
    if not text:
        raise ValueError("EDI text is empty")

    # Determine if ~ is used as segment terminator
    has_tilde = '~' in text

    if has_tilde:
        # Newlines are only for readability — strip them all
        text = text.replace('\r\n', '').replace('\r', '').replace('\n', '')
        if len(text) < 106:
            raise ValueError("EDI text is too short to contain a valid ISA envelope")
        elem_sep = text[3]
        seg_term = text[105]
        raw_segs = [s.strip() for s in re.split(re.escape(seg_term), text) if s.strip()]
    else:
        # Each line is its own segment; standardize terminator to ~
        lines = [ln.strip() for ln in re.split(r'\r?\n|\r', text) if ln.strip()]
        if not lines:
            raise ValueError("EDI text is empty after stripping whitespace")
        first = lines[0]
        if len(first) < 4:
            raise ValueError("First line too short to detect element separator")
        elem_sep = first[3]
        seg_term = '~'
        raw_segs = lines

    out: List[str] = []
    for seg in raw_segs:
        elems = seg.split(elem_sep)
        seg_id = elems[0].strip().upper()
        elems[0] = seg_id

        if seg_id == 'ISA':
            # Rebuild ISA with every element padded to its exact fixed width
            padded = ['ISA']
            for idx, width in enumerate(_ISA_WIDTHS, start=1):
                raw_val = elems[idx].strip() if idx < len(elems) else ''
                if idx == 13:
                    # ISA13: interchange control number — zero-pad on the left
                    padded.append(raw_val.zfill(width)[:width])
                else:
                    # All other fields — space-pad on the right
                    padded.append(raw_val.ljust(width)[:width])
            out.append(elem_sep.join(padded))
        else:
            out.append(elem_sep.join(elems))

    return '~\n'.join(out) + '~\n'


# ── Safe float conversion ─────────────────────────────────────────────────────

def _f(s: str, default: float = 0.0) -> float:
    """Convert EDI element to float; empty strings and non-numeric values → default."""
    try:
        return float(s.strip()) if s.strip() else default
    except ValueError:
        return default


# ── NPI extraction helper ─────────────────────────────────────────────────────

def _find_id(elems: List[str]) -> Optional[str]:
    """
    Find the ID value in an NM1 segment regardless of element count.

    Standard layout: NM108 = qualifier (XX / SY / MI / MB …), NM109 = value.
    Fallback: scan positions 7–10 for a value that looks like a 10-digit NPI.
    """
    id_qualifiers = {'XX', 'SY', 'EI', 'MI', 'MB', 'NI', 'PI', 'XV'}
    for i, e in enumerate(elems[:-1]):
        if e.strip().upper() in id_qualifiers:
            val = elems[i + 1].strip()
            if val:
                return val
    # Fallback: any 10-digit number in the later positions
    for i in range(7, min(len(elems), 11)):
        val = elems[i].strip()
        if re.match(r'^\d{10}$', val):
            return val
    return None


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_835(raw_edi: str) -> Parsed835:
    """Parse a raw X12 835 string into a structured Parsed835 object."""
    # Normalize first so all separator detection is reliable
    normalized = normalize_835(raw_edi)
    raw = normalized.replace('\n', '')          # strip the pretty-print newlines

    elem_sep = raw[3]
    seg_term = raw[105]

    segments = [s.strip() for s in re.split(re.escape(seg_term), raw) if s.strip()]

    era_number = "ERA-IMPORT"
    payer_name = "Unknown Payer"
    payment_amount = 0.0
    payment_date = date.today().isoformat()
    claims: List[ParsedClaim] = []

    current_claim: Optional[ParsedClaim] = None
    current_svc: Optional[ParsedSvcLine] = None

    def _flush_svc() -> None:
        nonlocal current_svc
        if current_svc is not None and current_svc.cpt_code and current_claim is not None:
            current_claim.svc_lines.append(current_svc)
            current_svc = None

    def _flush_claim() -> None:
        nonlocal current_claim
        _flush_svc()
        if current_claim is not None:
            claims.append(current_claim)
            current_claim = None

    def _parse_date(raw_dt: str) -> Optional[str]:
        raw_dt = raw_dt.strip()
        if len(raw_dt) == 8:
            return f"{raw_dt[:4]}-{raw_dt[4:6]}-{raw_dt[6:]}"
        return None

    for seg in segments:
        elems = seg.split(elem_sep)
        seg_id = elems[0].upper()

        if seg_id == "BPR":
            if len(elems) > 2:
                try:
                    payment_amount = float(elems[2])
                except ValueError:
                    pass

        elif seg_id == "TRN":
            if len(elems) > 2:
                era_number = elems[2]

        elif seg_id == "DTM":
            if len(elems) > 2:
                qualifier = elems[1]
                parsed_date = _parse_date(elems[2])
                if parsed_date:
                    if qualifier in ("405", "036"):
                        payment_date = parsed_date
                    elif qualifier == "472" and current_svc is not None:
                        current_svc.service_date = parsed_date
                        if current_claim and not current_claim.service_date:
                            current_claim.service_date = parsed_date

        elif seg_id == "N1":
            if len(elems) > 2 and elems[1] == "PR":
                payer_name = elems[2]

        elif seg_id == "CLP":
            _flush_claim()
            billed = _f(elems[3]) if len(elems) > 3 else 0.0
            paid   = _f(elems[4]) if len(elems) > 4 else 0.0
            pat_r  = _f(elems[5]) if len(elems) > 5 else 0.0
            current_claim = ParsedClaim(
                patient_control_number=elems[1] if len(elems) > 1 else "PCN-UNKNOWN",
                billed=billed,
                paid=paid,
                patient_responsibility=pat_r,
                payer_claim_number=elems[7] if len(elems) > 7 else None,
            )

        elif seg_id == "NM1":
            qualifier = elems[1] if len(elems) > 1 else ""
            if current_claim:
                if qualifier == "QC":
                    current_claim.patient_last  = elems[3] if len(elems) > 3 else ""
                    current_claim.patient_first = elems[4] if len(elems) > 4 else ""
                    current_claim.patient_id    = _find_id(elems)
                elif qualifier in ("82", "77"):
                    npi   = _find_id(elems)
                    last  = elems[3] if len(elems) > 3 else ""
                    first = elems[4] if len(elems) > 4 else ""
                    current_claim.rendering_npi  = npi
                    current_claim.rendering_name = (
                        f"{first} {last}".strip() or f"Provider-{npi}"
                    )

        elif seg_id == "SVC":
            _flush_svc()
            composite = elems[1] if len(elems) > 1 else ""
            parts = composite.split(":")
            cpt      = parts[1] if len(parts) > 1 else composite
            modifier = parts[2] if len(parts) > 2 else None
            billed    = _f(elems[2]) if len(elems) > 2 else 0.0
            paid      = _f(elems[3]) if len(elems) > 3 else 0.0
            raw_units = elems[5] if len(elems) > 5 else "1"
            try:
                units = int(float(raw_units)) if raw_units.strip() else 1
            except (ValueError, IndexError):
                units = 1
            current_svc = ParsedSvcLine(
                cpt_code=cpt.strip(),
                modifier=modifier,
                billed_amount=billed,
                paid_amount=paid,
                units=units,
            )

        elif seg_id == "CAS":
            if current_svc and len(elems) > 3:
                try:
                    adj = float(elems[3])
                except ValueError:
                    adj = 0.0
                current_svc.adjustment_reason_code = f"{elems[1]}-{elems[2]}"
                current_svc.adjustment_amount = adj

    _flush_claim()

    for c in claims:
        if not c.service_date:
            c.service_date = payment_date

    return Parsed835(
        era_number=era_number,
        payer_name=payer_name,
        payment_amount=payment_amount,
        payment_date=payment_date,
        claims=claims,
    )
