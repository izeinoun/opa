"""Case Guidance Engine — lifecycle + next-action computation.

Pure function over a hand-built CaseDetail + viewing user; no LLM, no DB. Proves
the gates from docs/analyst-supervisor-workflow.md are reflected in guidance:
  * the DET-09 needs_review hard block,
  * the high-dollar supervisor gate (settings.high_dollar_threshold),
  * role/owner-aware next actions.
"""
from types import SimpleNamespace

from app.config import settings
from app.schemas.case_schemas import (
    CaseDetail, DetectorResultRead, ClaimFindingRead, UserRead,
)
from app.services.case_guidance_service import compute_guidance


def _user(uid, role="analyst"):
    return SimpleNamespace(user_id=uid, role=role)


def _detail(status, amount, assignee_id=None, findings=None):
    return CaseDetail(
        id=1, case_number="OPA-1", status=status, priority="HIGH", priority_score=80,
        likelihood_score=0.7, amount_at_risk=amount, is_active=True, opened_at="now",
        lob="COMMERCIAL",
        assignee=UserRead(
            id=assignee_id, username="a", full_name="A", email="", role="analyst",
            is_active=True,
        ) if assignee_id else None,
        detector_results=findings or [],
    )


def _finding(det, conf, disposition):
    return DetectorResultRead(
        detector_id=det, detector_name=det, fired=True,
        finding=ClaimFindingRead(
            id="f1", detector_code=det, finding_type="HIGH", description="x",
            overpayment_amount=100.0, confidence_score=conf, evidence_json="{}",
            created_at="now", disposition_status=disposition,
        ),
    )


HI = settings.high_dollar_threshold + 1000      # over the gate
LO = settings.high_dollar_threshold - 1000       # under the gate


def test_new_unassigned_suggests_take_ownership():
    g = compute_guidance(_detail("new", LO), _user("ana"))
    assert g.next_action.kind == "take_ownership"
    assert g.current_step == "assign"
    assert g.role_context.supervisor_gate is False


def test_owner_of_assigned_starts_review():
    g = compute_guidance(_detail("assigned", LO, assignee_id="ana"), _user("ana"))
    assert g.next_action.kind == "start_review"
    assert g.role_context.is_owner is True


def test_needs_review_blocks_and_points_at_the_finding():
    g = compute_guidance(
        _detail("in_review", HI, "ana",
                [_finding("DET-09", 0.72, "needs_review"),
                 _finding("DET-04", 0.9, "accepted")]),
        _user("ana"),
    )
    assert g.next_action.kind == "disposition_finding"
    assert "DET-09" in g.next_action.label
    assert g.next_action.target["params"]["finding_id"] == "f1"
    assert g.current_step == "review_findings"
    review = next(s for s in g.lifecycle if s.key == "review_findings")
    assert review.state == "blocked"
    assert g.blockers and g.blockers[0].type == "needs_review"


def test_resolved_high_dollar_warns_about_supervisor_gate():
    g = compute_guidance(
        _detail("in_review", HI, "ana", [_finding("DET-04", 0.9, "accepted")]),
        _user("ana"),
    )
    assert g.next_action.kind == "submit_decision"
    assert "supervisor" in g.next_action.explanation.lower()
    assert g.role_context.supervisor_gate is True


def test_resolved_low_dollar_no_supervisor_mention():
    g = compute_guidance(
        _detail("in_review", LO, "ana", [_finding("DET-04", 0.9, "accepted")]),
        _user("ana"),
    )
    assert g.next_action.kind == "submit_decision"
    assert "supervisor" not in g.next_action.explanation.lower()
    # supervisor step is skipped when under the gate
    sup = next(s for s in g.lifecycle if s.key == "supervisor")
    assert sup.state == "skipped"


def test_pending_supervisor_is_role_aware():
    pending = _detail("pending_supervisor", HI, "ana")
    g_analyst = compute_guidance(pending, _user("ana"))
    assert g_analyst.next_action.kind == "awaiting_supervisor"
    assert g_analyst.next_action.actionable is False

    g_sup = compute_guidance(pending, _user("sarah", "supervisor"))
    assert g_sup.next_action.kind == "supervisor_decision"


def test_recovery_phase():
    g = compute_guidance(_detail("notice_sent", HI, "ana"), _user("ana"))
    assert g.next_action.kind == "record_recovery"
    assert g.current_step == "recovery"


def test_terminal_recovered_all_complete_no_action():
    g = compute_guidance(_detail("closed_recovered", HI, "ana"), _user("ana"))
    assert g.next_action is None
    assert g.current_step is None
    assert all(s.state == "completed" for s in g.lifecycle)
    assert "closed" in g.remaining_summary.lower()


def test_terminal_not_for_recoup_skips_notice_and_recovery():
    g = compute_guidance(_detail("closed_not_for_recoup", LO, "ana"), _user("ana"))
    assert g.next_action is None
    states = {s.key: s.state for s in g.lifecycle}
    assert states["submit_decision"] == "completed"
    assert states["notice"] == "skipped"
    assert states["recovery"] == "skipped"


# ── Action-bar pills ────────────────────────────────────────────────────────
def _actions(g):
    return {a.kind: a for a in g.actions}


def test_actions_always_include_escalate_and_siu_when_active():
    g = compute_guidance(_detail("in_review", LO, "ana", [_finding("DET-04", 0.9, "accepted")]), _user("ana"))
    a = _actions(g)
    assert "escalate" in a and "send_to_siu" in a
    assert a["escalate"].enabled and a["send_to_siu"].enabled
    assert a["escalate"].needs_input == "reason"


def test_actions_decision_disabled_while_findings_block():
    g = compute_guidance(
        _detail("in_review", HI, "ana", [_finding("DET-09", 0.72, "needs_review")]),
        _user("ana"),
    )
    a = _actions(g)
    assert a["approve_recoverable"].enabled is False
    assert "Resolve" in a["approve_recoverable"].disabled_reason
    assert a["set_not_recoverable"].enabled is False


def test_actions_decision_recommends_from_suggested_decision():
    g = compute_guidance(_detail("in_review", LO, "ana", [_finding("DET-04", 0.9, "accepted")]), _user("ana"))
    a = _actions(g)
    # default _detail has no suggested_decision → neither recommended, both enabled
    assert a["approve_recoverable"].enabled and a["set_not_recoverable"].enabled
    assert a["set_not_recoverable"].needs_input == "reason"


def test_actions_owned_assigned_shows_disabled_submit():
    g = compute_guidance(_detail("assigned", LO, "ana"), _user("ana"))
    a = _actions(g)
    assert a["start_review"].recommended is True
    # Submit pills are visible but disabled until review starts.
    assert "approve_recoverable" in a and a["approve_recoverable"].enabled is False
    assert "Start review" in a["approve_recoverable"].disabled_reason
    assert a["approve_recoverable"].label.startswith("Submit")


def test_actions_take_ownership_for_unowned_new_case():
    g = compute_guidance(_detail("new", LO), _user("ana"))
    a = _actions(g)
    assert a["take_ownership"].recommended is True
    assert a["take_ownership"].style == "primary"


def test_actions_supervisor_gate_role_aware():
    pending = _detail("pending_supervisor", HI, "ana")
    a_an = _actions(compute_guidance(pending, _user("ana")))
    assert "supervisor_approve" not in a_an          # analyst can't approve
    assert a_an["escalate"].enabled is False          # already awaiting supervisor
    a_sup = _actions(compute_guidance(pending, _user("sarah", "supervisor")))
    assert a_sup["supervisor_approve"].recommended is True
    assert a_sup["supervisor_reject"].needs_input == "reason"


def test_actions_terminal_only_reopen_for_supervisor():
    a_an = _actions(compute_guidance(_detail("closed_recovered", HI, "ana"), _user("ana")))
    assert a_an == {}
    a_sup = _actions(compute_guidance(_detail("closed_recovered", HI, "ana"), _user("s", "supervisor")))
    assert "reopen" in a_sup and a_sup["reopen"].needs_input == "reason"


def test_actions_siu_frozen_has_no_write_pills():
    d = _detail("in_review", HI, "ana", [_finding("DET-04", 0.9, "accepted")])
    d.siu_frozen = True
    g = compute_guidance(d, _user("ana"))
    assert g.actions == []
