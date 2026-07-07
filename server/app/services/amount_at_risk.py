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


def _per_line_claim(finding, claim_lines: List, pre_pay: bool = False) -> Dict[str, float]:
    """Returns {line_id: amount_claimed} for one finding.

    Post-pay: the amount is the overpayment already made (paid-based), attributed
    only for the overpayment detectors that carry dollar logic.
    Pre-pay: nothing is paid yet, so ANY finding that touches a line puts that
    line's full ``billed_amount`` at risk (the exposure we'd avoid by denying /
    reducing the claim before adjudication).
    """
    if pre_pay:
        return _per_line_claim_prepay(finding, claim_lines)
    return _per_line_claim_paid(finding, claim_lines)


def _per_line_claim_prepay(finding, claim_lines: List) -> Dict[str, float]:
    """Pre-pay billed-exposure coverage for one finding.

    A finding's referenced lines are at risk at their full billed amount. Findings
    with no specific line reference are claim-level (excluded provider, credential
    fraud, bill-type, etc.) and put the whole claim at risk. Informational findings
    ($0, e.g. coding-suboptimal warnings) carry no exposure.
    """
    ev = _parse_evidence(finding.evidence)
    if ev.get("financial_impact") is False:
        return {}

    def billed(l) -> float:
        return float(getattr(l, "billed_amount", 0.0) or 0.0)

    # Explicit multi-line references
    line_ids = ev.get("affected_line_ids") or ev.get("line_ids")
    if line_ids:
        return {l.claim_line_id: billed(l) for l in claim_lines if l.claim_line_id in line_ids}
    # Single line reference (evidence line_id or the finding's own line)
    single = ev.get("line_id") or getattr(finding, "claim_line_id", None)
    if single:
        return {l.claim_line_id: billed(l) for l in claim_lines if l.claim_line_id == single}
    # CPT-scoped coverage (e.g. NCCI pair, duplicate overlap)
    cpts = set(ev.get("overlapping_cpts") or [])
    if cpts:
        return {l.claim_line_id: billed(l) for l in claim_lines if l.cpt_code in cpts}
    # Claim-level finding → whole claim at risk
    return {l.claim_line_id: billed(l) for l in claim_lines}


def _per_line_claim_paid(finding, claim_lines: List) -> Dict[str, float]:
    """Post-pay per-line overpayment attribution (paid-based). See _per_line_claim."""
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
        # paid_amount is nullable on pre-pay lines (no payment yet) — coerce None → 0.
        total_paid = sum((l.paid_amount or 0.0) for l in affected) or 1.0
        return {
            l.claim_line_id: op * ((l.paid_amount or 0.0) / total_paid)
            for l in affected
        }

    # Unknown detector: fall back to flat overpayment over the finding's own line if any
    if getattr(finding, "claim_line_id", None):
        return {finding.claim_line_id: float(finding.overpayment_amount or 0.0)}
    return {}


def finding_standalone_at_risk(
    finding, claim_lines: List, pipeline_mode: str | None = None
) -> float:
    """One finding's own at-risk dollars, NOT deduped against other findings.

    Post-pay: its overpayment. Pre-pay: the billed exposure of the lines it covers.
    Used for per-finding display + severity (each finding shows what *it* flags),
    which is distinct from the deduped case total from compute_at_risk_deduped.
    """
    pre_pay = (
        pipeline_mode == "pre_pay"
        if pipeline_mode is not None
        else bool(claim_lines) and all(getattr(l, "paid_amount", None) is None for l in claim_lines)
    )
    return round(sum(_per_line_claim(finding, claim_lines, pre_pay=pre_pay).values()), 2)


def compute_at_risk_deduped(
    claim_lines: List,
    findings: Iterable,
    pipeline_mode: str | None = None,
    tier_by_finding: Dict[str, int] | None = None,
) -> Tuple[float, Dict[str, dict]]:
    """Returns (total_at_risk, per_line_breakdown).

    per_line_breakdown[line_id] = {
        'amount': float, 'detector_id': str, 'finding_id': str,
    }

    pipeline_mode: 'pre_pay' values flagged lines at their billed exposure
    (nothing is paid yet). If None, inferred: a claim whose every line has a
    null paid_amount is treated as pre-pay.

    tier_by_finding: optional {finding_id: tier} for the attribution race —
    a LOWER tier wins a line outright regardless of detector priority. Used
    to let analyst-validated (accepted/adjusted) findings take their lines'
    recovery amount over undispositioned automation defaults. Within a tier,
    detector priority (then larger claim) decides, as before. Findings not
    in the dict default to tier 0, so passing None preserves the original
    priority-only behavior.
    """
    findings = list(findings)
    if not findings or not claim_lines:
        return 0.0, {}

    pre_pay = (
        pipeline_mode == "pre_pay"
        if pipeline_mode is not None
        else all(getattr(l, "paid_amount", None) is None for l in claim_lines)
    )
    tiers = tier_by_finding or {}

    best_per_line: Dict[str, Tuple[Tuple[int, int], float, str, str]] = {}
    # value: ((tier, priority_rank), amount, detector_id, finding_id)

    for f in findings:
        key = (tiers.get(f.finding_id, 0), PRIORITY_RANK.get(f.detector_id, 99))
        line_claims = _per_line_claim(f, claim_lines, pre_pay=pre_pay)
        for line_id, amt in line_claims.items():
            if amt <= 0:
                continue
            existing = best_per_line.get(line_id)
            if existing is None:
                best_per_line[line_id] = (key, amt, f.detector_id, f.finding_id)
                continue
            # Lower (tier, rank) wins; on ties, keep the larger claim.
            if key < existing[0] or (key == existing[0] and amt > existing[1]):
                best_per_line[line_id] = (key, amt, f.detector_id, f.finding_id)

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
    pipeline_mode: str | None = None,
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
    pre_pay = (
        pipeline_mode == "pre_pay"
        if pipeline_mode is not None
        else all(getattr(l, "paid_amount", None) is None for l in claim_lines)
    )
    out: Dict[str, dict] = {}
    for f in findings:
        claims = _per_line_claim(f, claim_lines, pre_pay=pre_pay)
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
