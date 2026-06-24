"""Case-guidance schemas — the workflow "where am I / what's next" payload.

Computed by `services/case_guidance_service.py` from an already-assembled
CaseDetail, and consumed by BOTH the PayGuard case page and the in-app
Assistant cockpit so the two surfaces always agree on lifecycle state and the
recommended next action. See docs/workflow-guidance-plan.md (Part 1).
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


# Lifecycle step states.
#   completed — done (a prior step)
#   current   — the step the case is actively on
#   blocked   — current step but something hard-blocks advancement (needs_review)
#   upcoming  — a future step
#   skipped   — a conditional step that does not apply to this case
#               (e.g. supervisor approval when at-risk ≤ threshold)
STEP_STATES = ("completed", "current", "blocked", "upcoming", "skipped")


class LifecycleStep(BaseModel):
    key: str
    label: str
    state: str
    detail: Optional[str] = None     # short qualifier, e.g. "2 of 3 findings need review"
    conditional: bool = False        # true for the supervisor-approval gate


class NextAction(BaseModel):
    """The single recommended next thing to do on this case for the viewer."""
    kind: str                        # semantic action id (see case_guidance_service)
    label: str                       # button text, e.g. "Review DET-09 finding"
    explanation: str                 # one sentence on why / what happens
    actionable: bool = True          # false when the viewer can only wait (no CTA)
    target: Dict[str, Any] = {}      # {"view": "case", "params": {...}} deep-link


class CaseAction(BaseModel):
    """A case-level action pill for the cockpit action bar. Server-defined so the
    cockpit and chat agree on what's available in each state."""
    kind: str                        # semantic id (take_ownership, approve_recoverable, …)
    label: str                       # pill text
    style: str = "default"           # 'primary' (pink/recommended) | 'default' | 'caution'
    enabled: bool = True
    disabled_reason: Optional[str] = None    # tooltip when disabled
    needs_input: Optional[str] = None        # 'reason' | 'amount' | 'amount_reason'
    recommended: bool = False        # the single suggested next step


class Blocker(BaseModel):
    type: str                        # e.g. "needs_review"
    count: int = 0
    message: str


class RoleContext(BaseModel):
    is_owner: bool
    role: str
    supervisor_gate: bool            # at-risk > high-dollar threshold


class CaseGuidance(BaseModel):
    lifecycle: List[LifecycleStep]
    current_step: Optional[str] = None     # key of the current/blocked step (None when terminal)
    next_action: Optional[NextAction] = None
    actions: List[CaseAction] = []         # cockpit action-bar pills for this state
    blockers: List[Blocker] = []
    remaining_summary: str = ""
    role_context: RoleContext
