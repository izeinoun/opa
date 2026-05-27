"""Per-line de-duplicated amount-at-risk calculation.

The naive `sum(f.overpayment_amount for f in findings)` double-counts any
line that's flagged by multiple detectors. This module attributes each
claim line to the *highest-priority* finding that covers it, then sums.

Priority (lower rank = higher priority):
    DET-08 (Excluded Provider) → claim-level, full paid
    DET-01 (Duplicate)         → claim-level full paid OR line-level full paid
    DET-02 (Retro Eligibility) → claim-level, full paid
    DET-04 (Fee Schedule)      → line-level, paid-minus-allowed delta
    DET-06 (NCCI/MUE)          → line-level, paid amount
    DET-09 (Coding Errors)     → line-level, distributed overpayment
"""
from __future__ import annotations

import json
from typing import Dict, Iterable, List, Tuple


PRIORITY_RANK: Dict[str, int] = {
    "DET-08": 0,
    "DET-01": 1,
    "DET-02": 2,
    "DET-04": 3,
    "DET-06": 4,
    "DET-09": 5,
}


def _parse_evidence(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _per_line_claim(finding, claim_lines: List) -> Dict[str, float]:
    """Returns {line_id: amount_claimed} for one finding.

    Claim-level findings (no line attribution in evidence) cover *all* lines
    at their full paid_amount. Line-specific findings cover only the lines
    they reference.
    """
    code = finding.detector_id
    ev = _parse_evidence(finding.evidence)

    # DET-08, DET-02, DET-01-exact: claim-level, full paid per line
    if code == "DET-08":
        return {l.claim_line_id: l.paid_amount for l in claim_lines}

    if code == "DET-02":
        return {l.claim_line_id: l.paid_amount for l in claim_lines}

    if code == "DET-01":
        # Exact duplicate has 'original_paid'; partial overlap has 'overlapping_cpts'.
        if "overlapping_cpts" in ev and "overlap_paid" in ev and "original_paid" not in ev:
            cpts = set(ev.get("overlapping_cpts") or [])
            return {l.claim_line_id: l.paid_amount for l in claim_lines if l.cpt_code in cpts}
        # Exact duplicate (or partial that also has original_paid): treat as whole-claim
        return {l.claim_line_id: l.paid_amount for l in claim_lines}

    if code == "DET-04":
        # violating_lines has line_id + overpayment (delta only — paid - allowed)
        out: Dict[str, float] = {}
        for vl in ev.get("violating_lines", []):
            line_id = vl.get("line_id")
            if line_id:
                out[line_id] = float(vl.get("overpayment", 0.0))
        return out

    if code == "DET-06":
        # Two evidence shapes:
        #   MUE:    line_id, paid_amount
        #   bundle: cpt_code_a / cpt_code_b — mutually exclusive pair
        if "line_id" in ev:
            return {ev["line_id"]: float(ev.get("paid_amount", 0.0))}
        # NCCI mutually-exclusive: detector claims min(paid_a, paid_b). Attribute
        # only the lower-paid CPT's lines — the other CPT is the one we keep.
        cpt_a = ev.get("cpt_code_a")
        cpt_b = ev.get("cpt_code_b")
        paid_a = float(ev.get("paid_a", 0.0))
        paid_b = float(ev.get("paid_b", 0.0))
        losing_cpt = cpt_a if paid_a <= paid_b else cpt_b
        return {l.claim_line_id: l.paid_amount for l in claim_lines if l.cpt_code == losing_cpt}

    if code == "DET-09":
        # affected_line_ids + a single overpayment total → distribute proportionally
        line_ids = ev.get("affected_line_ids") or []
        op = float(ev.get("overpayment", finding.overpayment_amount or 0.0))
        affected = [l for l in claim_lines if l.claim_line_id in line_ids]
        total_paid = sum(l.paid_amount for l in affected) or 1.0
        return {
            l.claim_line_id: op * (l.paid_amount / total_paid)
            for l in affected
        }

    # Unknown detector: fall back to flat overpayment over the finding's own line if any
    if getattr(finding, "claim_line_id", None):
        return {finding.claim_line_id: float(finding.overpayment_amount or 0.0)}
    return {}


def compute_at_risk_deduped(
    claim_lines: List,
    findings: Iterable,
) -> Tuple[float, Dict[str, dict]]:
    """Returns (total_at_risk, per_line_breakdown).

    per_line_breakdown[line_id] = {
        'amount': float, 'detector_id': str, 'finding_id': str,
    }
    """
    findings = list(findings)
    if not findings or not claim_lines:
        return 0.0, {}

    best_per_line: Dict[str, Tuple[int, float, str, str]] = {}
    # value: (priority_rank, amount, detector_id, finding_id)

    for f in findings:
        rank = PRIORITY_RANK.get(f.detector_id, 99)
        line_claims = _per_line_claim(f, claim_lines)
        for line_id, amt in line_claims.items():
            if amt <= 0:
                continue
            existing = best_per_line.get(line_id)
            if existing is None:
                best_per_line[line_id] = (rank, amt, f.detector_id, f.finding_id)
                continue
            # Higher priority (lower rank) wins; on ties, keep the larger claim.
            if rank < existing[0] or (rank == existing[0] and amt > existing[1]):
                best_per_line[line_id] = (rank, amt, f.detector_id, f.finding_id)

    total = sum(v[1] for v in best_per_line.values())
    breakdown = {
        line_id: {"amount": amt, "detector_id": det, "finding_id": fid}
        for line_id, (_, amt, det, fid) in best_per_line.items()
    }
    return round(total, 2), breakdown


def attribute_findings(
    claim_lines: List,
    findings: Iterable,
    line_breakdown: Dict[str, dict],
) -> Dict[str, dict]:
    """Per-finding attribution given a line breakdown from compute_at_risk_deduped.

    For each finding, walks its per-line claims and reports:
      attributed_amount: total $ that this finding contributed to at-risk
                         (lines where this finding won the dedup priority race)
      suppressed_amount: total $ this finding claimed but lost
                         (lines where a higher-priority detector also fired)
      superseded_by:     sorted list of detector_ids that won lines this
                         finding claimed but lost

    Returns: {finding_id: {attributed_amount, suppressed_amount, superseded_by}}
    """
    out: Dict[str, dict] = {}
    for f in findings:
        claims = _per_line_claim(f, claim_lines)
        attributed = 0.0
        suppressed = 0.0
        suppressors: set = set()
        for line_id, amt in claims.items():
            if amt <= 0:
                continue
            winner = line_breakdown.get(line_id)
            if winner and winner.get("finding_id") == f.finding_id:
                attributed += amt
            else:
                suppressed += amt
                if winner:
                    suppressors.add(winner["detector_id"])
        out[f.finding_id] = {
            "attributed_amount": round(attributed, 2),
            "suppressed_amount": round(suppressed, 2),
            "superseded_by": sorted(suppressors),
        }
    return out
