"""Tool registry — OPA READ endpoints exposed as Claude tools.

Each Tool maps to one existing GET endpoint. Descriptions are written to help
the model SELECT the right tool (purpose, when to use, what it returns), in the
Charlie style. Tools are partitioned by RBAC `apps`; the agent only offers a
user the tools for apps they can access.

READ-ONLY by design: only GET endpoints are registered here. No mutation tools.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    # RBAC apps that grant this tool. Empty tuple = available to any user who
    # can reach the assistant (e.g. cross-app member/template lookups).
    apps: tuple[str, ...]
    method: str
    path: str  # template, e.g. "/api/cases/{case_id}"
    path_params: tuple[str, ...] = ()
    query_params: tuple[str, ...] = ()
    input_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})

    def anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


# ── ask_user (special, no endpoint) ───────────────────────────────────────
# Mirrors Charlie's disambiguation tool: when the request is ambiguous, the
# model calls this instead of guessing; the UI renders soft-button options.
ASK_USER = Tool(
    name="ask_user",
    description=(
        "Ask the user a clarifying question when their request is ambiguous or "
        "could match multiple things (e.g. several cases or providers). Present "
        "2-4 concise options. Do NOT guess when intent is unclear — ask."
    ),
    apps=(),
    method="",
    path="",
    input_schema={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "The clarifying question"},
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-4 short options the user can pick from",
            },
        },
        "required": ["question"],
        "additionalProperties": False,
    },
)


# ── present_view (special, no endpoint) ───────────────────────────────────
# The interactive-cockpit channel: when the request maps to a known app SCREEN,
# the model calls this instead of describing it in prose. The agent special-
# cases it (like ask_user) and emits a {"type":"directive", ...} event; the UI
# mounts the matching assistant-native view with live data. v1 views are
# PayGuard post-pay surfaces.
PRESENT_VIEW = Tool(
    name="present_view",
    description=(
        "Render an interactive in-app VIEW for the user instead of describing it "
        "in prose. Use this when the request maps to a known screen — a case "
        "worklist/queue, one specific case, or the user's personal dashboard — "
        "e.g. 'show my cases', 'open case 142', 'unassigned high-priority', "
        "'take me to my dashboard', 'pull up the recovery queue'. The UI mounts "
        "the view with live data and real action buttons, so you don't need to "
        "list the rows yourself — just give a one-line `caption`. Do NOT use this "
        "for analytical/explanatory questions ('why is this provider risky', "
        "'compare recovery to last month') — answer those in prose. Views & "
        "params: worklist {scope:'mine'|'unassigned'|'all', status?, priority?, "
        "overdue?}; case {case_id}; my_dashboard {period?}."
    ),
    apps=(),
    method="",
    path="",
    input_schema={
        "type": "object",
        "properties": {
            "view": {
                "type": "string",
                "enum": ["worklist", "case", "my_dashboard"],
                "description": "Which screen to render.",
            },
            "params": {
                "type": "object",
                "description": (
                    "View parameters. worklist: scope (mine|unassigned|all), "
                    "status, priority (HIGH|MEDIUM|LOW), overdue (bool). "
                    "case: case_id (integer). my_dashboard: period (week|month|quarter)."
                ),
                "additionalProperties": True,
            },
            "caption": {
                "type": "string",
                "description": "One short sentence introducing the view to the user.",
            },
        },
        "required": ["view"],
        "additionalProperties": False,
    },
)


# ── confirm_action (special, no endpoint) — the WRITE gate ─────────────────
# The assistant can mutate cases, but ONLY through this tool, and ONLY after the
# user explicitly confirms. The model proposes a write (action + params + a
# plain-language summary); the agent emits an {"type":"awaiting_confirmation"}
# event and STOPS. The write executes server-side only when the user confirms.
# See docs/workflow-guidance-plan.md (Amendment 2).


@dataclass(frozen=True)
class WriteAction:
    """A mutation the assistant may propose. Maps to one existing write endpoint;
    executed in-process as the user (so server-side RBAC + gates + audit apply)."""
    method: str
    path: str  # template with {case_id} / {finding_id}
    path_params: tuple[str, ...]
    body_params: tuple[str, ...] = ()       # keys pulled from params into the JSON body
    inject_analyst_id: bool = False          # set body.analyst_id = current user (take ownership)
    scope: str = "case"                      # 'case' | 'finding' — what the write affects


# action name → endpoint mapping. The model picks an action from this set.
WRITE_ACTIONS: dict[str, WriteAction] = {
    "take_ownership":  WriteAction("PATCH", "/api/cases/{case_id}/assign", ("case_id",), inject_analyst_id=True),
    "assign_case":     WriteAction("PATCH", "/api/cases/{case_id}/assign", ("case_id",), body_params=("analyst_id",)),
    "transition_case": WriteAction("POST", "/api/cases/{case_id}/transition", ("case_id",), body_params=("to_status", "reason", "recovered_amount")),
    "approve_case":    WriteAction("POST", "/api/cases/{case_id}/approve", ("case_id",), body_params=("reason",)),
    "reject_case":     WriteAction("POST", "/api/cases/{case_id}/reject", ("case_id",), body_params=("reason",)),
    "escalate_to_supervisor": WriteAction("POST", "/api/cases/{case_id}/escalate", ("case_id",), body_params=("reason",)),
    "accept_finding":  WriteAction("POST", "/api/findings/{finding_id}/accept", ("finding_id",), body_params=("reason",), scope="finding"),
    "reject_finding":  WriteAction("POST", "/api/findings/{finding_id}/reject", ("finding_id",), body_params=("reason",), scope="finding"),
    "adjust_finding":  WriteAction("POST", "/api/findings/{finding_id}/adjust", ("finding_id",), body_params=("adjusted_amount", "reason"), scope="finding"),
    "generate_provider_notice": WriteAction("POST", "/api/letters/cases/{case_id}/generate-notice", ("case_id",), body_params=("content_override",)),
}


CONFIRM_ACTION = Tool(
    name="confirm_action",
    description=(
        "Propose a WRITE to a PayGuard case and ask the user to confirm before it "
        "runs. This is the ONLY way to change case state — accepting/rejecting/adjusting "
        "a finding, taking ownership, transitioning a case, approving/rejecting a held "
        "decision, escalating, or generating a notice. NEVER claim you changed something "
        "without calling this first. Provide `action`, a one-sentence `summary` of exactly "
        "what will change (amounts/status/reason), and `params` with the ids and fields the "
        "action needs. Call it ALONE (not alongside other tools). Required fields per action: "
        "take_ownership{case_id}; assign_case{case_id,analyst_id}; "
        "transition_case{case_id,to_status,reason?}; approve_case{case_id,reason?}; "
        "reject_case{case_id,reason}; escalate_to_supervisor{case_id,reason}; "
        "accept_finding{finding_id,case_id,reason?}; reject_finding{finding_id,case_id,reason}; "
        "adjust_finding{finding_id,case_id,adjusted_amount,reason}; "
        "generate_provider_notice{case_id,content_override?}. Always include case_id so the "
        "updated case can be shown after. NOTE: Use send_notice_to_provider or "
        "send_provider_inquiry tools for email communication, not confirm_action."
    ),
    apps=("payguard",),
    method="",
    path="",
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(WRITE_ACTIONS.keys()),
                "description": "Which write to perform.",
            },
            "summary": {
                "type": "string",
                "description": "One sentence, plain language: exactly what will change. Shown to the user to confirm.",
            },
            "params": {
                "type": "object",
                "description": "Ids and fields for the action (case_id and/or finding_id, plus to_status/reason/adjusted_amount/analyst_id as required).",
                "additionalProperties": True,
            },
        },
        "required": ["action", "summary", "params"],
        "additionalProperties": False,
    },
)


def _str(desc: str) -> dict:
    return {"type": "string", "description": desc}


TOOLS: tuple[Tool, ...] = (
    # ── PayGuard (post-pay overpayment recovery) ──────────────────────────
    Tool(
        name="search_cases",
        description=(
            "Search/list PayGuard post-pay overpayment cases (the worklist). Use "
            "FIRST for any question about cases — to find cases by status, "
            "priority, detector, assignee, or free text — before fetching one "
            "case's detail. Returns a paginated list of case summaries (case "
            "number, status, priority, amount, provider). Narrow with filters; "
            "don't pull everything."
        ),
        apps=("payguard",),
        method="GET",
        path="/api/cases",
        query_params=(
            "status", "priority", "lob", "detector_code", "assignee_id",
            "search", "exclude_closed", "closed_only", "overdue_only", "page_size",
        ),
        input_schema={
            "type": "object",
            "properties": {
                "status": _str("Case status filter (e.g. new, in_review, closed)"),
                "priority": _str("Priority band: HIGH | MEDIUM | LOW"),
                "lob": _str("Line of business (e.g. MA, PPO, Medicaid)"),
                "detector_code": _str("Detector that fired, e.g. DET-01, DET-08"),
                "assignee_id": _str("Analyst user_id to filter by assignee"),
                "search": _str("Free-text search across case fields"),
                "exclude_closed": {"type": "boolean", "description": "Hide closed cases"},
                "closed_only": {"type": "boolean", "description": "Only closed cases"},
                "overdue_only": {"type": "boolean", "description": "Only overdue cases"},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 200, "default": 25},
            },
            "additionalProperties": False,
        },
    ),
    Tool(
        name="get_case",
        description=(
            "Get full detail for one PayGuard case by its numeric case id "
            "(the sequence number from search_cases). Returns claim, provider, "
            "member, findings, scores, status and timeline. Use after "
            "search_cases to drill into a specific case."
        ),
        apps=("payguard",),
        method="GET",
        path="/api/cases/{case_id}",
        path_params=("case_id",),
        input_schema={
            "type": "object",
            "properties": {
                "case_id": {"type": "integer", "description": "Numeric case id (sequence)"},
            },
            "required": ["case_id"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="get_case_guidance",
        description=(
            "Get workflow guidance for a PayGuard case by numeric case id: where "
            "it is in its lifecycle, what's blocking it, and the single recommended "
            "next action for the current user (role/owner-aware). Use when the user "
            "asks 'what's next', 'what should I do', or what's left on a case."
        ),
        apps=("payguard",),
        method="GET",
        path="/api/cases/{case_id}/guidance",
        path_params=("case_id",),
        input_schema={
            "type": "object",
            "properties": {
                "case_id": {"type": "integer", "description": "Numeric case id (sequence)"},
            },
            "required": ["case_id"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="get_case_notes",
        description=(
            "Get the analyst/supervisor notes on a PayGuard case by numeric case "
            "id. Use when the user asks what was discussed, decided, or noted on "
            "a case."
        ),
        apps=("payguard",),
        method="GET",
        path="/api/cases/{case_id}/notes",
        path_params=("case_id",),
        input_schema={
            "type": "object",
            "properties": {
                "case_id": {"type": "integer", "description": "Numeric case id"},
            },
            "required": ["case_id"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="get_payguard_dashboard",
        description=(
            "Get PayGuard operational dashboard metrics: KPIs, case aging "
            "buckets, analyst workload, recovery trend, detector stats, and "
            "status distribution. Use for portfolio/overview questions ('how "
            "many open cases', 'total at risk', 'recovery this month')."
        ),
        apps=("payguard",),
        method="GET",
        path="/api/dashboard",
    ),
    Tool(
        name="get_daily_briefing",
        description=(
            "Get your personalized daily briefing: personal stats (cases closed, "
            "dollars recovered, current workload), trends vs yesterday/last week, "
            "team comparison (your performance vs team average), and your top 5 "
            "high-value cases. Use for personal performance questions ('how am I "
            "doing', 'my stats', 'my metrics', 'briefing', 'performance review')."
        ),
        apps=("payguard",),
        method="GET",
        path="/api/dashboard/briefing",
        query_params=("period",),
        input_schema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["day", "week"],
                    "default": "day",
                    "description": "Reporting period: day (vs yesterday) or week (vs last week)",
                },
            },
            "additionalProperties": False,
        },
    ),
    Tool(
        name="list_provider_risk",
        description=(
            "List provider risk explanations (ML risk score, band, top drivers, "
            "plain-English rationale) for PayGuard. Use for 'riskiest providers' "
            "or why a provider is flagged. NOTE: restricted to supervisor/admin; "
            "may return a permission error for analysts."
        ),
        apps=("payguard",),
        method="GET",
        path="/api/provider-risk",
    ),
    # ── ClaimGuard (pre-pay claim review) ─────────────────────────────────
    Tool(
        name="list_prepay_claims",
        description=(
            "List ClaimGuard pre-pay claims under review. Filter by status or "
            "specialty. Returns claim summaries (icn, provider, patient, CPTs, "
            "ICD-10s, billed amount, status, AI summary). Use FIRST for pre-pay "
            "questions before fetching one claim's detail."
        ),
        apps=("claimguard",),
        method="GET",
        path="/api/prepay/claims",
        query_params=("status", "specialty"),
        input_schema={
            "type": "object",
            "properties": {
                "status": _str("Claim status filter"),
                "specialty": _str("Provider specialty filter"),
            },
            "additionalProperties": False,
        },
    ),
    Tool(
        name="get_prepay_claim",
        description=(
            "Get full detail for one ClaimGuard pre-pay claim by claim_id "
            "(string). Returns codes, AI findings, evidence and summary. Use "
            "after list_prepay_claims to drill into a specific claim."
        ),
        apps=("claimguard",),
        method="GET",
        path="/api/prepay/claims/{claim_id}",
        path_params=("claim_id",),
        input_schema={
            "type": "object",
            "properties": {
                "claim_id": _str("The pre-pay claim id (string)"),
            },
            "required": ["claim_id"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="get_prepay_dashboard",
        description=(
            "Get ClaimGuard pre-pay dashboard metrics: KPIs, status "
            "distribution, aging, decision trend, AI coverage, specialty mix, "
            "top providers, workload. Use for pre-pay overview questions."
        ),
        apps=("claimguard",),
        method="GET",
        path="/api/prepay/dashboard",
    ),
    # ── SIU (special investigations) ──────────────────────────────────────
    Tool(
        name="get_siu_dashboard",
        description=(
            "Get SIU (Special Investigation Unit) dashboard metrics: KPIs, "
            "case status/type/pipeline distribution, weekly volumes, outcomes, "
            "investigator workload, and FWA rule breakdown. Use for fraud/waste/"
            "abuse investigation overview questions."
        ),
        apps=("siu",),
        method="GET",
        path="/api/siu/dashboard",
    ),
    # ── Cross-app lookups ─────────────────────────────────────────────────
    Tool(
        name="search_members",
        description=(
            "Search members by name or member number. Returns matching member "
            "summaries. Use to resolve a patient/member the user names in plain "
            "language before looking up their cases or claims."
        ),
        apps=("payguard", "claimguard"),
        method="GET",
        path="/api/members",
        query_params=("search", "lob", "page_size"),
        input_schema={
            "type": "object",
            "properties": {
                "search": _str("Name or member number (partial allowed)"),
                "lob": _str("Line of business filter"),
                "page_size": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
            },
            "additionalProperties": False,
        },
    ),
    Tool(
        name="get_my_dashboard",
        description=(
            "Get the current user's personal productivity dashboard for a "
            "period (week|month|quarter): cases closed, dollars recovered/"
            "written off, average handle time, disposition breakdown, pipeline "
            "snapshot. Use for 'my' / 'how am I doing' questions."
        ),
        apps=("payguard", "claimguard"),
        method="GET",
        path="/api/dashboard/me",
        query_params=("period",),
        input_schema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["week", "month", "quarter"],
                    "default": "month",
                },
            },
            "additionalProperties": False,
        },
    ),
    # ── Email / Communication Tools ──────────────────────────────────────────
    Tool(
        name="send_notice_to_provider",
        description=(
            "Send the case's notice/letter to the provider via secure encrypted link. "
            "The notice letter must already exist (created in previous steps). "
            "The provider receives an email with a secure link; they verify their NPI "
            "to access the letter and any attachments. Access is logged and tracked. "
            "Use this when the case is ready to notify the provider of the decision."
        ),
        apps=("payguard",),
        method="POST",
        path="/api/cases/{case_id}/send-notice-to-provider",
        path_params=("case_id",),
        input_schema={
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "Case UUID or ID"},
            },
            "required": ["case_id"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="send_provider_inquiry",
        description=(
            "Send a custom inquiry or message to the provider via secure encrypted link. "
            "Content is composed by you (the assistant) or the user. The provider receives "
            "an email with a secure link; they verify their NPI to view the message. "
            "No attachment is sent. Use this for ad-hoc communication about the case "
            "(e.g., requesting additional information, clarifying findings, asking questions)."
        ),
        apps=("payguard",),
        method="POST",
        path="/api/cases/{case_id}/send-provider-inquiry",
        path_params=("case_id",),
        input_schema={
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "Case UUID or ID"},
                "inquiry_text": {
                    "type": "string",
                    "description": "The message content (plain text or HTML) to send to the provider",
                },
            },
            "required": ["case_id", "inquiry_text"],
            "additionalProperties": False,
        },
    ),
    # ── ClearLink (member clinical data) ─────────────────────────────────────
    # These tools are proxied to ClearLink's MCP server. All require member_id.
    # ClearLink must be configured via CLEARLINK_MCP_URL and CLEARLINK_MCP_API_KEY env vars.
    # Available to any authenticated user (API key authentication is checked server-side).
    Tool(
        name="list_medications",
        description=(
            "List a member's active medications from ClearLink. Use to correlate "
            "member medications with PayGuard claim diagnoses. Returns name, dosage, "
            "frequency, prescriber, start date, status."
        ),
        apps=(),  # Available to any user
        method="GET",
        path="/mcp/proxy/tools/list_medications",
        query_params=("member_id", "status"),
        input_schema={
            "type": "object",
            "properties": {
                "member_id": _str("Member ID from PayGuard (required)"),
                "status": _str("Filter: active, all, or discontinued"),
            },
            "required": ["member_id"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="list_diagnoses",
        description=(
            "List a member's diagnoses from ClearLink (ICD-10, HCC codes, RAF weights). "
            "Use to validate claim diagnoses against member's active diagnoses. "
            "Optionally filter by date."
        ),
        apps=(),
        method="GET",
        path="/mcp/proxy/tools/list_diagnoses",
        query_params=("member_id", "since", "include_inactive", "limit"),
        input_schema={
            "type": "object",
            "properties": {
                "member_id": _str("Member ID from PayGuard (required)"),
                "since": _str("Filter diagnoses from date (YYYY-MM-DD)"),
                "include_inactive": {"type": "boolean", "description": "Include inactive diagnoses"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
            },
            "required": ["member_id"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="list_dates_of_service",
        description=(
            "List a member's visits/encounters from ClearLink. Use to find relevant "
            "dates of service to correlate with claim service dates. Filter by visit "
            "type or date range."
        ),
        apps=(),
        method="GET",
        path="/mcp/proxy/tools/list_dates_of_service",
        query_params=("member_id", "visit_type", "date_from", "date_to", "limit"),
        input_schema={
            "type": "object",
            "properties": {
                "member_id": _str("Member ID from PayGuard (required)"),
                "visit_type": _str("Filter: surgery, office_visit, er, telehealth, etc."),
                "date_from": _str("Start date (YYYY-MM-DD)"),
                "date_to": _str("End date (YYYY-MM-DD)"),
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            "required": ["member_id"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="get_claims_window",
        description=(
            "Get claims for a member within a date range from ClearLink. Use to find "
            "other claims around the same service period. Requires date_from and "
            "date_to to keep results bounded."
        ),
        apps=(),
        method="GET",
        path="/mcp/proxy/tools/get_claims_window",
        query_params=("member_id", "date_from", "date_to", "limit"),
        input_schema={
            "type": "object",
            "properties": {
                "member_id": _str("Member ID from PayGuard (required)"),
                "date_from": _str("Start date (YYYY-MM-DD, required)"),
                "date_to": _str("End date (YYYY-MM-DD, required)"),
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
            },
            "required": ["member_id", "date_from", "date_to"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="get_labs_window",
        description=(
            "Get lab results for a member within a date range from ClearLink. Use to "
            "correlate abnormal labs with claim procedures. Requires date_from and date_to."
        ),
        apps=(),
        method="GET",
        path="/mcp/proxy/tools/get_labs_window",
        query_params=("member_id", "date_from", "date_to", "limit"),
        input_schema={
            "type": "object",
            "properties": {
                "member_id": _str("Member ID from PayGuard (required)"),
                "date_from": _str("Start date (YYYY-MM-DD, required)"),
                "date_to": _str("End date (YYYY-MM-DD, required)"),
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
            },
            "required": ["member_id", "date_from", "date_to"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="list_prior_authorizations",
        description=(
            "List prior authorization requests for a member from ClearLink. Use to "
            "check if procedures were pre-approved."
        ),
        apps=(),
        method="GET",
        path="/mcp/proxy/tools/list_prior_authorizations",
        query_params=("member_id", "status", "limit"),
        input_schema={
            "type": "object",
            "properties": {
                "member_id": _str("Member ID from PayGuard (required)"),
                "status": {
                    "type": "string",
                    "enum": ["pending", "auto_approved", "auto_denied", "pended_review", "approved", "denied", "cancelled"],
                    "description": "Filter by status",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
            },
            "required": ["member_id"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="get_member_demographics",
        description=(
            "Get member demographics and enrollment status from ClearLink. Use to verify "
            "member identity and check coverage dates for the claim."
        ),
        apps=(),
        method="GET",
        path="/mcp/proxy/tools/get_member_demographics",
        query_params=("member_id",),
        input_schema={
            "type": "object",
            "properties": {
                "member_id": _str("Member ID from PayGuard (required)"),
            },
            "required": ["member_id"],
            "additionalProperties": False,
        },
    ),
)


TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in (*TOOLS, ASK_USER, PRESENT_VIEW, CONFIRM_ACTION)}


def tools_for_apps(user_apps: set[str]) -> list[Tool]:
    """Return the tools available to a user with `user_apps`, plus the special
    ask_user and present_view tools (and the write-gate confirm_action for
    PayGuard users).

    A tool with no `apps` is available to anyone; otherwise the user must hold
    at least one of the tool's apps.
    """
    available = [
        t for t in TOOLS if not t.apps or (set(t.apps) & user_apps)
    ]
    specials = [ASK_USER, PRESENT_VIEW]
    if "payguard" in user_apps:
        specials.append(CONFIRM_ACTION)
    return [*available, *specials]
