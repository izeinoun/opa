"""Case Guidance Engine — computes the workflow "where am I / what's next"
payload for a case, shared by the PayGuard case page and the Assistant cockpit.

Pure computation over an already-assembled CaseDetail plus the viewing user —
no extra DB queries. It encodes the gates from docs/analyst-supervisor-workflow.md:

  * the DET-09 `needs_review` hard block (a case can't advance to a recoupment
    letter while any finding is unresolved), and
  * the high-dollar supervisor gate (read from settings.high_dollar_threshold —
    the SAME source the enforcement path uses, so the UI can never disagree).

See docs/workflow-guidance-plan.md (Part 1).
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from ..config import settings
from ..schemas.case_schemas import CaseDetail
from ..schemas.guidance import (
    CaseGuidance,
    LifecycleStep,
    NextAction,
    CaseAction,
    Blocker,
    RoleContext,
)

# Ordered analyst-centric lifecycle. SIU escalation is a side-branch (rendered
# as a chip elsewhere), not a main step; intake/837 folds into the assign step.
_ORDER: List[Tuple[str, str]] = [
    ("assign", "Assign"),
    ("review_findings", "Review findings"),
    ("submit_decision", "Submit decision"),
    ("supervisor", "Supervisor approval"),
    ("notice", "Recoupment letter"),
    ("recovery", "Recovery & close"),
]
_KEYS = [k for k, _ in _ORDER]
_IDX = {k: i for i, k in enumerate(_KEYS)}
_SUPERVISOR_IDX = _IDX["supervisor"]

_PRE_ASSIGN = {"awaiting_837", "new", "identified"}
_RECOVERY_ACTIVE = {"notice_sent", "provider_responded", "reconciling"}


def _is_terminal(status: str) -> bool:
    return status.startswith("closed")


def _blocking_findings(detail: CaseDetail) -> list:
    """needs_review findings currently on the case, highest-confidence first."""
    out = []
    for dr in detail.detector_results or []:
        f = dr.finding
        if f is not None and f.disposition_status == "needs_review":
            out.append(f)
    out.sort(key=lambda f: f.confidence_score, reverse=True)
    return out


def _current_index(detail: CaseDetail, has_blockers: bool) -> int:
    """Index into _KEYS of the step the case is actively on. Terminal → len(_KEYS)."""
    s = detail.status
    if _is_terminal(s):
        return len(_KEYS)
    if s in _PRE_ASSIGN:
        return _IDX["assign"]
    if s == "assigned":
        return _IDX["review_findings"]
    if s == "in_review":
        return _IDX["review_findings"] if has_blockers else _IDX["submit_decision"]
    if s == "ready_for_notice":
        return _IDX["notice"]
    if s == "pending_supervisor":
        return _IDX["supervisor"]
    if s in _RECOVERY_ACTIVE:
        return _IDX["recovery"]
    # Unknown active status: treat like in_review — on submit once findings clear.
    return _IDX["review_findings"] if has_blockers else _IDX["submit_decision"]


def _build_lifecycle(
    detail: CaseDetail, current_idx: int, has_blockers: bool, gate: bool
) -> List[LifecycleStep]:
    terminal = _is_terminal(detail.status)
    recovered = detail.status == "closed_recovered"
    steps: List[LifecycleStep] = []
    for i, (key, label) in enumerate(_ORDER):
        conditional = key == "supervisor"
        detail_text = None

        if terminal:
            # assign/review/submit are always considered done once closed.
            if i <= _IDX["submit_decision"]:
                state = "completed"
            elif key == "supervisor":
                state = "completed" if gate else "skipped"
            else:  # notice, recovery
                state = "completed" if recovered else "skipped"
        elif i < current_idx:
            # A passed conditional step that didn't apply reads as skipped.
            state = "skipped" if (conditional and not gate) else "completed"
        elif i == current_idx:
            state = "blocked" if (key == "review_findings" and has_blockers) else "current"
        else:  # upcoming
            state = "skipped" if (conditional and not gate) else "upcoming"

        if key == "review_findings" and has_blockers and state in ("blocked", "current"):
            n = len(_blocking_findings(detail))
            detail_text = f"{n} finding{'s' if n != 1 else ''} need review"

        steps.append(
            LifecycleStep(
                key=key, label=label, state=state, detail=detail_text, conditional=conditional
            )
        )
    return steps


def _next_action(
    detail: CaseDetail, role: str, is_owner: bool, gate: bool,
    has_blockers: bool, blocking: list,
) -> Optional[NextAction]:
    s = detail.status
    cid = detail.id
    threshold = settings.high_dollar_threshold
    is_supervisor = role in ("supervisor", "admin")

    def _case_target(**params):
        return {"view": "case", "params": {"case_id": cid, **params}}

    if _is_terminal(s):
        return None

    if s == "awaiting_837":
        return NextAction(
            kind="adjudicate_without_837",
            label="Adjudicate without 837",
            explanation="Diagnosis-dependent detectors are deferred until the 837 links — link it or override to proceed.",
            target=_case_target(),
        )

    if s in ("new", "identified"):
        if not is_owner:
            return NextAction(
                kind="take_ownership", label="Take ownership",
                explanation="This case is unassigned — self-assign to start working it.",
                target=_case_target(),
            )
        return NextAction(
            kind="start_review", label="Start review",
            explanation="You own this case — open it and begin reviewing the findings.",
            target=_case_target(),
        )

    if s == "assigned":
        if is_owner:
            return NextAction(
                kind="start_review", label="Start review",
                explanation="Begin reviewing the detector findings on this case.",
                target=_case_target(),
            )
        return NextAction(
            kind="view_case", label="Open case",
            explanation="This case is assigned to another analyst; open it to review.",
            target=_case_target(),
        )

    if s == "in_review":
        if has_blockers:
            f = blocking[0]
            det = f.detector_code
            conf = f.confidence_score or 0.0
            return NextAction(
                kind="disposition_finding",
                label=f"Review {det} finding",
                explanation=(
                    f"{det} is at {conf:.0%} confidence and must be accepted, rejected, "
                    "or adjusted before a recoupment letter can be sent."
                ),
                target=_case_target(tab="findings", finding_id=f.id),
            )
        extra = (
            f" Because at-risk is over ${threshold:,.0f}, it will be held for supervisor approval."
            if gate else ""
        )
        return NextAction(
            kind="submit_decision", label="Submit a decision",
            explanation="All findings are resolved — submit a recoup or not-for-recoup decision." + extra,
            target=_case_target(),
        )

    if s == "ready_for_notice":
        return NextAction(
            kind="send_notice", label="Preview & send notice",
            explanation="Review is complete — generate and send the recoupment letter.",
            target=_case_target(),
        )

    if s == "pending_supervisor":
        if is_supervisor:
            return NextAction(
                kind="supervisor_decision", label="Approve or reject",
                explanation="An analyst submitted a high-dollar decision — re-check the findings and amount, then approve or reject.",
                target=_case_target(),
            )
        return NextAction(
            kind="awaiting_supervisor", label="Awaiting supervisor approval",
            explanation="This case is held for supervisor sign-off — no action is needed from you until it's approved or returned.",
            actionable=False, target={},
        )

    if s in _RECOVERY_ACTIVE:
        return NextAction(
            kind="record_recovery", label="Record recovery",
            explanation="The notice is out — record provider payments until the overpayment is fully recovered.",
            target=_case_target(),
        )

    return None


def _build_actions(
    detail: CaseDetail, role: str, is_owner: bool, has_blockers: bool,
    n_block: int, suggested: Optional[str],
) -> List[CaseAction]:
    """The cockpit action-bar pills for this case state. Recommended pills render
    pink (style='primary'); a write that needs free input declares needs_input."""
    s = detail.status
    is_sup = role in ("supervisor", "admin")
    frozen = bool(getattr(detail, "siu_frozen", False))
    actions: List[CaseAction] = []

    def add(kind, label, *, style="default", enabled=True, disabled_reason=None,
            needs_input=None, recommended=False):
        rec = recommended and enabled
        actions.append(CaseAction(
            kind=kind, label=label, style="primary" if rec else style,
            enabled=enabled, disabled_reason=disabled_reason,
            needs_input=needs_input, recommended=rec,
        ))

    if _is_terminal(s):
        if is_sup:
            add("reopen", "Reopen case", needs_input="reason")
        return actions

    if frozen:
        # Evidence is read-only while SIU holds the case — no write pills.
        return actions

    # The submit-decision pills — shown whenever the owner is working the case so
    # the "how do I submit" step is always discoverable; disabled (with a reason)
    # until review is started and all findings are resolved.
    def add_decision(*, enabled: bool, why: Optional[str] = None):
        add("approve_recoverable", "Submit — recoverable", enabled=enabled, disabled_reason=why,
            recommended=(enabled and suggested == "recoup"))
        add("set_not_recoverable", "Submit — not recoverable", style="caution", enabled=enabled,
            disabled_reason=why, needs_input="reason", recommended=(enabled and suggested == "not_for_recoup"))

    # ── Primary step pills by status ──────────────────────────────────────
    if s == "awaiting_837":
        add("adjudicate_without_837", "Adjudicate without 837", recommended=True)
    elif s in ("new", "identified", "assigned"):
        if not is_owner:
            add("take_ownership", "Take ownership", recommended=True)
        else:
            add("start_review", "Start review", recommended=True)
            add_decision(enabled=False, why="Start review and resolve findings first")
    elif s == "ready_for_notice":
        add("send_notice", "Send recoup notice", recommended=True)
    elif s == "pending_supervisor":
        if is_sup:
            add("supervisor_approve", "Approve", recommended=True)
            add("supervisor_reject", "Reject", style="caution", needs_input="reason")
        # analyst: case is locked — no action pills
    elif s in _RECOVERY_ACTIVE:
        add("record_recovery", "Record recovery", needs_input="amount", recommended=True)
    else:
        # in_review and any other active "working" status: offer the submit
        # decision, disabled until findings are resolved.
        if has_blockers:
            add_decision(enabled=False, why=f"Resolve {n_block} finding{'s' if n_block != 1 else ''} first")
        else:
            add_decision(enabled=True)

    # ── Always-on pair: Escalate + Send to SIU (gated) ────────────────────
    esc_active = bool(getattr(detail, "escalation", None) and getattr(detail.escalation, "is_active", False))
    if s == "pending_supervisor":
        add("escalate", "Escalate", style="caution", enabled=False, disabled_reason="Already awaiting supervisor", needs_input="reason")
    elif esc_active:
        add("escalate", "Escalate", style="caution", enabled=False, disabled_reason="Already escalated", needs_input="reason")
    else:
        add("escalate", "Escalate", style="caution", needs_input="reason")
    add("send_to_siu", "Send to SIU", style="caution", needs_input="reason")

    return actions


def compute_guidance(detail: CaseDetail, user) -> CaseGuidance:
    """Compute lifecycle + next-action guidance for `detail` as seen by `user`.

    `user` is an OpaUser (needs `.user_id`, `.role`). Pure function — safe to
    call anywhere a CaseDetail is in hand.
    """
    role = getattr(user, "role", "analyst") or "analyst"
    user_id = getattr(user, "user_id", None)
    assignee_id = detail.assignee.id if detail.assignee else None
    is_owner = bool(user_id) and user_id == assignee_id

    amount = detail.amount_at_risk or 0.0
    gate = amount > settings.high_dollar_threshold

    blocking = _blocking_findings(detail)
    has_blockers = len(blocking) > 0

    current_idx = _current_index(detail, has_blockers)
    lifecycle = _build_lifecycle(detail, current_idx, has_blockers, gate)

    current_step = None
    for step in lifecycle:
        if step.state in ("current", "blocked"):
            current_step = step.key
            break

    blockers: List[Blocker] = []
    if has_blockers:
        n = len(blocking)
        blockers.append(
            Blocker(
                type="needs_review", count=n,
                message=f"{n} finding{'s' if n != 1 else ''} need analyst review (accept, reject, or adjust) before this case can advance.",
            )
        )

    next_action = _next_action(detail, role, is_owner, gate, has_blockers, blocking)

    suggested = getattr(getattr(detail, "suggested_decision", None), "recommendation", None)
    actions = _build_actions(detail, role, is_owner, has_blockers, len(blocking), suggested)

    remaining_labels = [s.label for s in lifecycle if s.state in ("current", "blocked", "upcoming")]
    if not remaining_labels:
        remaining_summary = "Case closed — no further action."
    else:
        remaining_summary = "Remaining: " + " → ".join(remaining_labels) + "."

    return CaseGuidance(
        lifecycle=lifecycle,
        current_step=current_step,
        next_action=next_action,
        actions=actions,
        blockers=blockers,
        remaining_summary=remaining_summary,
        role_context=RoleContext(is_owner=is_owner, role=role, supervisor_gate=gate),
    )
