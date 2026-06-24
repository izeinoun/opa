"""OPA Assistant — MCP server (stdio) for Claude Desktop / cowork.

Exposes the OPA read-only assistant as a single MCP tool, `ask_opa`. The tool
forwards the question to OPA's `/api/assistant/chat` endpoint, which runs the
full Claude tool_use agent loop server-side (selecting and calling OPA's READ
APIs as tools) and returns a grounded answer. RBAC scopes what the agent can
see to the configured OPA user's apps.

This is a thin HTTP client — it does NOT import the FastAPI app or touch the DB,
so it starts fast and runs independently of the web process.

Configuration (env):
  OPA_BASE_URL   OPA backend base URL            (default http://localhost:8001)
  OPA_PASSWORD   Demo-gate password (required when the deployment sets
                 DEMO_PASSWORD; the server logs in to obtain a token)
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
    """Obtain a demo-gate token via OPA_PASSWORD, cached. Returns None when no
    password is configured (gate disabled / local dev)."""
    global _token
    if _token or not OPA_PASSWORD:
        return _token
    resp = await client.post(f"{OPA_BASE_URL}/api/auth/login", json={"password": OPA_PASSWORD})
    if resp.status_code == 200:
        _token = resp.json().get("token")
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
                "OPA requires the demo login. Set OPA_PASSWORD (the deployment's "
                "DEMO_PASSWORD) in the MCP server config."
            )
        return f"OPA error (HTTP {e.response.status_code})."
    except Exception as e:  # pragma: no cover
        return f"OPA request failed: {e}"

    if resp.status_code == 401:
        return (
            "OPA requires the demo login. Set OPA_PASSWORD (the deployment's "
            "DEMO_PASSWORD) in the MCP server config."
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


if __name__ == "__main__":
    mcp.run()  # stdio transport (what Claude Desktop launches)
