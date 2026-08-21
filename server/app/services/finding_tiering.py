"""Finding tiering — split a claim's fired findings into a primary "Key issues"
group and a secondary "Other signals" group, and decide which findings count
toward the headline evidence/recommendation math.

Motivation: when a claim trips many rules, showing every card at once reads as
noise ("this claim is littered") and buries the issues that actually matter. We
instead surface the most *material* findings and demote the rest, while stating
the full count in a one-line summary so nothing is hidden.

Two reasons a finding is demoted to "Other signals":
  • low_confidence — confidence at/under CONFIDENCE_FLOOR, UNLESS a safety-valve
    (high severity or high dollars) keeps it up. Confidence answers "how sure a
    problem exists", not "how costly" — so a low-confidence but high-$ finding
    must NOT be hidden.
  • overflow — material, but ranked outside the top KEY_ISSUES_CAP.
  • informational — $0 findings (financial_impact False); never material.

Only *material* findings (above the floor or safety-valved) count toward the
evidence score and recommendation, so the headline reconciles with what's shown:
overflow material findings still count (that's why the summary can read "12
material, showing top 10"), but low-confidence demoted ones never inflate it.

Pure/deterministic — no LLM, no DB. The LLM cross-check runs separately over
the returned `key` set.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..services.case_service import (
    _is_informational_finding,
    _finding_at_risk,
    finding_display_severity,
)

# Findings with confidence strictly greater than this are "material" on
# confidence alone. Detectors emit "heuristic" findings at exactly 0.50, so the
# strict `>` deliberately routes those to Other signals. Operator-tunable knob.
CONFIDENCE_FLOOR = 0.50

# Max findings shown in the primary "Key issues" tab. The cap only bites on a
# claim that trips a pile of checks; most claims show all their findings.
KEY_ISSUES_CAP = 10

# Safety-valve: a finding at/under the confidence floor is STILL treated as
# material (kept eligible for the primary tab and counted in the math) when it
# is high-severity or puts real dollars at risk. Prevents "we hid the $38k flag
# because the rule was only 45% sure."
SAFETY_VALVE_AMOUNT = 1000.0
SAFETY_VALVE_SEVERITIES = {"critical"}   # normalized display severity

_SEVERITY_RANK = {
    "critical": 2, "high": 2,
    "warning": 1, "medium": 1,
    "ok": 0, "low": 0,
}


@dataclass
class TieredFindings:
    # Primary tab, ranked by materiality, length ≤ KEY_ISSUES_CAP.
    key: List = field(default_factory=list)
    # Everything demoted, each as (finding, reason).
    other: List = field(default_factory=list)
    # Findings that count toward evidence/recommendation (key + material overflow).
    material: List = field(default_factory=list)
    # finding_id -> (group, reason): group in {"key","other"};
    # reason in {None,"low_confidence","overflow","informational"}.
    assignment: dict = field(default_factory=dict)
    total: int = 0
    summary_text: Optional[str] = None


def _normalize_sev(raw: str) -> str:
    return (raw or "").strip().lower()


def _is_material(finding, lines, pipeline_mode) -> bool:
    """Above the confidence floor, or safety-valved by severity/dollars."""
    if _is_informational_finding(finding):
        return False
    conf = finding.confidence or 0.0
    if conf > CONFIDENCE_FLOOR:
        return True
    sev = _normalize_sev(finding_display_severity(finding, lines, pipeline_mode))
    if sev in SAFETY_VALVE_SEVERITIES:
        return True
    if (_finding_at_risk(finding, lines, pipeline_mode) or 0.0) >= SAFETY_VALVE_AMOUNT:
        return True
    return False


def _materiality_key(finding, lines, pipeline_mode) -> tuple:
    """Sort key (descending): severity band, then dollars, then confidence."""
    sev = _normalize_sev(finding_display_severity(finding, lines, pipeline_mode))
    return (
        _SEVERITY_RANK.get(sev, 0),
        _finding_at_risk(finding, lines, pipeline_mode) or 0.0,
        finding.confidence or 0.0,
    )


def _build_summary(total: int, key_n: int, other_n: int) -> Optional[str]:
    if other_n <= 0:
        return None
    sig = "signal" if other_n == 1 else "signals"
    return (
        f"{total} findings fired on this claim. Showing the {key_n} most "
        f"material; {other_n} lower-priority or lower-confidence {sig} moved to "
        f"Other signals."
    )


def tier_findings(findings: List, lines: List, pipeline_mode: str) -> TieredFindings:
    """Partition findings into key/other and identify the material set.

    `findings` is the full set of fired Finding rows for the claim.
    Returns a TieredFindings; callers use `.material` for the headline math,
    `.key` for the cross-check, and `.assignment` to label each AIFindingOut.
    """
    result = TieredFindings(total=len(findings))

    material: List = []
    demoted_reason: dict = {}          # finding_id -> reason for non-material
    for f in findings:
        if _is_material(f, lines, pipeline_mode):
            material.append(f)
        elif _is_informational_finding(f):
            demoted_reason[f.finding_id] = "informational"
        else:
            demoted_reason[f.finding_id] = "low_confidence"

    # Rank material findings; top-N is the primary tab, the rest overflow.
    material.sort(key=lambda f: _materiality_key(f, lines, pipeline_mode), reverse=True)
    key = material[:KEY_ISSUES_CAP]
    overflow = material[KEY_ISSUES_CAP:]

    result.material = material
    result.key = key

    for f in key:
        result.assignment[f.finding_id] = ("key", None)
    for f in overflow:
        result.assignment[f.finding_id] = ("other", "overflow")
        result.other.append((f, "overflow"))
    for f in findings:
        if f.finding_id in demoted_reason:
            reason = demoted_reason[f.finding_id]
            result.assignment[f.finding_id] = ("other", reason)
            result.other.append((f, reason))

    result.summary_text = _build_summary(
        total=result.total, key_n=len(key), other_n=len(result.other)
    )
    return result
