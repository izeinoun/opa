"""OPA Assistant — MCP server (stdio) for Claude Desktop / cowork.

Exposes the OPA assistant as MCP tools. `ask_opa` forwards questions to OPA's
`/api/assistant/chat` endpoint, which runs the full Claude tool_use agent loop
server-side (selecting and calling OPA's READ APIs as tools) and returns a
grounded answer. `perform_case_action` exposes the case WRITE actions (same
set as the in-app assistant / case-detail buttons: dispositions, transitions,
notes, recovery, SIU referral, letters, portal upload); writes execute as the
configured OPA user, so server-side RBAC + gates + audit apply. RBAC scopes
what the agent can see/do to the configured OPA user's apps.

This is a thin HTTP client — it does NOT import the FastAPI app or touch the DB,
so it starts fast and runs independently of the web process.

Configuration (env):
  OPA_BASE_URL   OPA backend base URL            (default http://localhost:8001)
  OPA_PASSWORD   Login password for OPA_USERNAME (the server logs in via
                 /api/auth/login to obtain a JWT; needed when REQUIRE_AUTH is on)
  OPA_USER_ID    Act as this OPA user_id         (optional)
  OPA_USERNAME   ...or resolve identity by username (optional)
  If neither USER var is set, the server auto-selects a seeded admin (so every
  app's tools are available). Identity + token are resolved once and cached.

Run (stdio):  python server/mcp_server.py
Register in Claude Desktop via claude_desktop_config.json (see MCP.md).
"""
from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

OPA_BASE_URL = os.getenv("OPA_BASE_URL", "http://localhost:8001").rstrip("/")
OPA_PASSWORD = os.getenv("OPA_PASSWORD")
OPA_USER_ID = os.getenv("OPA_USER_ID")
OPA_USERNAME = os.getenv("OPA_USERNAME")
_TIMEOUT = float(os.getenv("OPA_TIMEOUT", "120"))

mcp = FastMCP("opa-assistant")

# Resolved (user_id, role) cache — identity is stable for the server's lifetime.
_identity: tuple[str, str] | None = None
# Demo-gate token cache (when the deployment requires login).
_token: str | None = None


async def _ensure_token(client: httpx.AsyncClient) -> str | None:
    """Obtain a JWT by logging in with OPA_USERNAME + OPA_PASSWORD, cached.
    Optional — returns None when credentials aren't configured; the X-User-Id
    header then carries identity (sufficient unless REQUIRE_AUTH is on)."""
    global _token
    if _token or not (OPA_USERNAME and OPA_PASSWORD):
        return _token
    resp = await client.post(
        f"{OPA_BASE_URL}/api/auth/login",
        json={"username": OPA_USERNAME, "password": OPA_PASSWORD},
    )
    if resp.status_code == 200:
        _token = resp.json().get("access_token")
    return _token


def _headers(token: str | None, user_id: str | None = None, role: str | None = None) -> dict:
    h: dict[str, str] = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if user_id:
        h["X-User-Id"] = user_id
    if role:
        h["X-User-Role"] = role
    return h


async def _resolve_identity(client: httpx.AsyncClient) -> tuple[str, str]:
    """Determine which OPA user this server acts as. Order: OPA_USER_ID →
    OPA_USERNAME → first admin from /api/users. Returns (user_id, role)."""
    global _identity
    if _identity is not None:
        return _identity

    token = await _ensure_token(client)
    resp = await client.get(f"{OPA_BASE_URL}/api/users", headers=_headers(token))
    resp.raise_for_status()
    users = resp.json()

    chosen = None
    if OPA_USER_ID:
        chosen = next((u for u in users if u.get("id") == OPA_USER_ID), None)
        if chosen is None:
            # Honor an explicit id even if /api/users didn't list it.
            _identity = (OPA_USER_ID, "admin")
            return _identity
    elif OPA_USERNAME:
        chosen = next((u for u in users if u.get("username") == OPA_USERNAME), None)
        if chosen is None:
            raise RuntimeError(f"OPA_USERNAME '{OPA_USERNAME}' not found in OPA users")
    else:
        chosen = next((u for u in users if u.get("role") == "admin"), None) or (users[0] if users else None)
        if chosen is None:
            raise RuntimeError("No OPA users found; is the backend seeded?")

    _identity = (chosen["id"], chosen.get("role", "analyst"))
    return _identity


async def _ask(question: str) -> str:
    """Core: send `question` to OPA's assistant and return the answer text."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            user_id, role = await _resolve_identity(client)
            token = await _ensure_token(client)
            resp = await client.post(
                f"{OPA_BASE_URL}/api/assistant/chat",
                headers=_headers(token, user_id, role),
                json={"messages": [{"role": "user", "content": question}]},
            )
    except httpx.ConnectError:
        return (
            f"Could not reach the OPA backend at {OPA_BASE_URL}. "
            "Is the server running (uvicorn on :8001)?"
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return (
                "OPA requires login. Set OPA_USERNAME + OPA_PASSWORD (a valid OPA "
                "login) in the MCP server config."
            )
        return f"OPA error (HTTP {e.response.status_code})."
    except Exception as e:  # pragma: no cover
        return f"OPA request failed: {e}"

    if resp.status_code == 401:
        return (
            "OPA requires login. Set OPA_USERNAME + OPA_PASSWORD (a valid OPA "
            "login) in the MCP server config."
        )
    if resp.status_code == 403:
        return "The configured OPA user lacks access. Set OPA_USER_ID/OPA_USERNAME to a user with app access."
    if resp.status_code >= 400:
        return f"OPA error (HTTP {resp.status_code}): {resp.text[:500]}"

    data = resp.json()
    kind = data.get("type")
    if kind == "final":
        answer = data.get("message", "(no answer)")
        used = [t.get("tool") for t in data.get("trace", []) if t.get("tool")]
        if used:
            answer += "\n\n_(OPA tools used: " + ", ".join(used) + ")_"
        return answer
    if kind == "awaiting_user":
        opts = data.get("options") or []
        q = data.get("question", "Clarification needed.")
        extra = ("\nOptions: " + "; ".join(opts)) if opts else ""
        return f"OPA needs clarification: {q}{extra}\n\nRe-ask with your choice included."
    return f"OPA could not answer: {data.get('error', 'unknown error')}"


@mcp.tool()
async def ask_opa(question: str) -> str:
    """Ask the OPA payment-integrity platform a question and get a grounded,
    read-only answer from live data.

    OPA covers overpayment cases (PayGuard post-pay), pre-pay claim review
    (ClaimGuard), provider risk, recovery/pipeline metrics, members, and SIU
    fraud investigations. Use this for ANY question about those — e.g.:
      • "How many high-priority open cases are there?"
      • "What's the recovery pipeline looking like this month?"
      • "Tell me about case OPA-2026-00015"
      • "Which providers are riskiest and why?"
      • "Pre-pay claims pending for cardiology?"

    Read-only: it can retrieve and analyze, never modify. Ask one clear
    question per call; if OPA needs clarification it will say so.
    """
    return await _ask(question)


@mcp.tool()
async def send_email(
    template: str,
    to_email: str,
    to_name: str | None = None,
    template_params: dict | None = None,
) -> str:
    """Send a transactional email via EmailJS.

    Used by the external portal agent to notify analysts on delivery success/failure.

    Args:
        template: Email template type — 'secure_link', 'otp', or 'notify_payer'
        to_email: Recipient email address
        to_name: Recipient display name (optional)
        template_params: Template variables as JSON object

    Returns:
        Success message or error description.
    """
    import json
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            token = await _ensure_token(client)
            resp = await client.post(
                f"{OPA_BASE_URL}/api/email/send",
                headers=_headers(token),
                json={
                    "template": template,
                    "to_email": to_email,
                    "to_name": to_name,
                    "template_params": template_params or {},
                },
            )
            if resp.status_code >= 400:
                return f"Email send failed (HTTP {resp.status_code}): {resp.text}"
            return "Email sent successfully."
    except Exception as e:
        return f"Email send error: {str(e)}"


async def _get(path: str, params: dict | None = None) -> str:
    """Authenticated GET against the OPA backend. Returns response text."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        user_id, role = await _resolve_identity(client)
        token = await _ensure_token(client)
        resp = await client.get(
            f"{OPA_BASE_URL}{path}",
            params=params,
            headers=_headers(token, user_id, role),
        )
    if resp.status_code >= 400:
        return f"OPA error (HTTP {resp.status_code}): {resp.text[:500]}"
    return resp.text


@mcp.tool()
async def search_claimguard_claims(
    status: str | None = None,
    specialty: str | None = None,
) -> str:
    """List ClaimGuard pre-pay claims currently under review.

    Returns claim summaries: ICN, provider, patient, CPT/ICD-10 codes, billed
    amount, status, and AI summary. Optionally filter by status or specialty.

    Args:
        status: Claim status filter (e.g. pending_review, approved, denied)
        specialty: Provider specialty (e.g. cardiology, orthopedics)
    """
    params = {}
    if status:
        params["status"] = status
    if specialty:
        params["specialty"] = specialty
    return await _get("/api/prepay/claims", params or None)


async def _request(method: str, path: str, json_body: dict | None = None) -> str:
    """Authenticated request against the OPA backend. Returns response text."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        user_id, role = await _resolve_identity(client)
        token = await _ensure_token(client)
        resp = await client.request(
            method,
            f"{OPA_BASE_URL}{path}",
            json=json_body,
            headers=_headers(token, user_id, role),
        )
    if resp.status_code >= 400:
        return f"OPA error (HTTP {resp.status_code}): {resp.text[:500]}"
    return resp.text


# Case write actions — mirrors the in-app assistant's WRITE_ACTIONS registry
# (app/services/assistant/tools.py). Kept self-contained: this file must not
# import the FastAPI app. action → (method, path template, body keys).
_CASE_WRITE_ACTIONS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "take_ownership": ("PATCH", "/api/cases/{case_id}/assign", ("analyst_id",)),
    "assign_case": ("PATCH", "/api/cases/{case_id}/assign", ("analyst_id",)),
    "transition_case": ("POST", "/api/cases/{case_id}/transition", ("to_status", "reason", "recovered_amount")),
    "approve_case": ("POST", "/api/cases/{case_id}/approve", ("reason",)),
    "reject_case": ("POST", "/api/cases/{case_id}/reject", ("reason",)),
    "escalate_to_supervisor": ("POST", "/api/cases/{case_id}/escalate", ("reason",)),
    "accept_finding": ("POST", "/api/findings/{finding_id}/accept", ("reason",)),
    "reject_finding": ("POST", "/api/findings/{finding_id}/reject", ("reason",)),
    "adjust_finding": ("POST", "/api/findings/{finding_id}/adjust", ("adjusted_amount", "reason")),
    "generate_provider_notice": ("POST", "/api/letters/cases/{case_id}/generate-notice", ()),
    "reevaluate_rules": ("POST", "/api/cases/{case_id}/reevaluate-rules", ()),
    "send_notice_to_provider": ("POST", "/api/cases/{case_id}/send-notice-to-provider", ()),
    "send_provider_inquiry": ("POST", "/api/cases/{case_id}/send-provider-inquiry", ("inquiry_text",)),
    "reopen_case": ("POST", "/api/cases/{case_id}/reopen", ("reason",)),
    "adjudicate_without_claim": ("POST", "/api/cases/{case_id}/adjudicate-without-claim", ()),
    "override_case_amount": ("PATCH", "/api/cases/{case_id}/override-amount", ("amount", "reason")),
    "add_case_note": ("POST", "/api/cases/{case_id}/notes", ("body",)),
    "record_recovery": ("POST", "/api/cases/{case_id}/recoupments", ("amount", "method", "reference_number", "notes")),
    "escalate_to_siu": ("POST", "/api/siu/escalate", ("case_id", "escalation_reason", "investigation_type")),
    "generate_recoupment_letter": ("POST", "/api/cases/{case_id}/recoupment-letter", ()),
    "upload_to_provider_portal": ("POST", "/api/provider-portal/upload-recoup-notice?case_id={case_id}", ()),
}


async def _resolve_finding_id(case_id: str, detector_code: str) -> str:
    """Look up a finding id on a case by its detector code (e.g. DET-04, MED-001).
    Returns the finding id, or an error message starting with 'ERROR:'."""
    import json as _json
    raw = await _get(f"/api/cases/{case_id}")
    try:
        detail = _json.loads(raw)
    except ValueError:
        return f"ERROR: could not load case {case_id}: {raw[:300]}"
    findings = (detail.get("claim") or {}).get("findings") or detail.get("findings") or []
    matches = [f for f in findings
               if (f.get("detector_code") or "").upper() == detector_code.upper()]
    if not matches:
        codes = sorted({f.get("detector_code") for f in findings if f.get("detector_code")})
        return f"ERROR: no {detector_code} finding on case {case_id}. Findings present: {codes or 'none'}"
    if len(matches) > 1:
        ids = [(f.get("id"), f.get("overpayment_amount")) for f in matches]
        return (f"ERROR: {len(matches)} {detector_code} findings on case {case_id} — "
                f"pass finding_id explicitly. Candidates (id, amount): {ids}")
    return matches[0]["id"]


@mcp.tool()
async def perform_case_action(
    action: str,
    case_id: str,
    finding_id: str | None = None,
    detector_code: str | None = None,
    reason: str | None = None,
    adjusted_amount: float | None = None,
    amount: float | None = None,
    to_status: str | None = None,
    analyst_id: str | None = None,
    inquiry_text: str | None = None,
    body: str | None = None,
    method: str | None = None,
    reference_number: str | None = None,
    notes: str | None = None,
    escalation_reason: str | None = None,
    investigation_type: str | None = None,
    recovered_amount: float | None = None,
) -> str:
    """Perform a WRITE action on a PayGuard case — everything the case-detail
    buttons can do. Executes as the configured OPA user; server-side RBAC,
    gates, and audit logging all apply (role-gated actions may be refused).

    ALWAYS confirm with the user before calling this — it changes case state.

    Actions (with their required args beyond case_id):
      take_ownership; assign_case(analyst_id); transition_case(to_status, reason?);
      approve_case; reject_case(reason); escalate_to_supervisor(reason);
      accept_finding(finding_id|detector_code); reject_finding(finding_id|detector_code, reason);
      adjust_finding(finding_id|detector_code, adjusted_amount, reason) — update the
        recoup amount on a rule finding;
      generate_provider_notice; reevaluate_rules; send_notice_to_provider;
      send_provider_inquiry(inquiry_text); reopen_case(reason) [supervisor];
      adjudicate_without_claim; override_case_amount(amount, reason) [supervisor];
      add_case_note(body); record_recovery(amount, method, reference_number?, notes?)
        with method one of adjustment|check|credit_balance|eft|other;
      escalate_to_siu(escalation_reason, investigation_type?);
      generate_recoupment_letter; upload_to_provider_portal.

    Args:
        action: One of the actions listed above.
        case_id: Case sequence number (e.g. 16) or case UUID.
        finding_id: Finding UUID for finding actions; or pass detector_code instead.
        detector_code: Rule code (e.g. DET-04, MED-001) — resolved to the case's
            finding automatically when finding_id is not given.
        reason: Audit reason — required for reject/adjust/reopen/override actions.
        adjusted_amount: New recoup amount for adjust_finding.
        amount: Amount for override_case_amount / record_recovery.
        Remaining args are per-action fields (see list above).
    """
    spec = _CASE_WRITE_ACTIONS.get(action)
    if spec is None:
        return f"Unknown action '{action}'. Valid: {sorted(_CASE_WRITE_ACTIONS)}"
    http_method, path, body_keys = spec

    if "{finding_id}" in path and not finding_id:
        if not detector_code:
            return "ERROR: finding actions need finding_id or detector_code."
        resolved = await _resolve_finding_id(case_id, detector_code)
        if resolved.startswith("ERROR:"):
            return resolved
        finding_id = resolved

    if action == "take_ownership" and not analyst_id:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            analyst_id, _ = await _resolve_identity(client)

    provided = {
        "reason": reason, "adjusted_amount": adjusted_amount, "amount": amount,
        "to_status": to_status, "analyst_id": analyst_id, "inquiry_text": inquiry_text,
        "body": body, "method": method, "reference_number": reference_number,
        "notes": notes, "escalation_reason": escalation_reason,
        "investigation_type": investigation_type, "recovered_amount": recovered_amount,
        "case_id": case_id,
    }
    json_body = {k: provided[k] for k in body_keys if provided.get(k) is not None}
    path = path.replace("{case_id}", str(case_id)).replace("{finding_id}", str(finding_id or ""))
    result = await _request(http_method, path, json_body or None)
    if result.startswith("OPA error"):
        return result
    return f"Done — '{action}' applied. Response: {result[:800]}"


@mcp.tool()
async def get_member_360(member_id: str) -> str:
    """Get a full cross-system member profile in one call.

    Fetches and combines:
    • Member demographics and coverage from the OPA member registry
    • PayGuard post-pay overpayment recovery cases
    • ClaimGuard pre-pay claims under review
    • ClearLink eligibility / demographics (when ClearLink is configured)

    Use this for any question that asks for a full picture of a member across
    multiple systems — e.g. "show me everything on John Doe", "cross-system
    member view", "what cases and claims does this member have".

    Args:
        member_id: Member UUID from a search_members or ask_opa result
    """
    return await _get(f"/api/members/{member_id}/360")


if __name__ == "__main__":
    mcp.run()  # stdio transport (what Claude Desktop launches)
