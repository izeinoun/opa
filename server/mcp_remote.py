"""OPA tools — remote MCP server (streamable-HTTP) for Claude Cowork / hosted clients.

Unlike `mcp_server.py` (stdio, single coarse `ask_opa` tool), this server exposes
each OPA READ endpoint as its OWN MCP tool, generated from the assistant's tool
registry (`app.services.assistant.tools.TOOLS`). A connecting agent (e.g. Cowork)
sees `search_cases`, `get_payguard_dashboard`, `get_case`, … and orchestrates
them itself.

It's a thin HTTP client — it does NOT import the FastAPI app or touch the DB. It
forwards each call to the OPA backend over HTTP, acting as a configured OPA user
(RBAC scopes what that user can read). Transport is streamable-HTTP, served at
`/mcp`, so a hosted client connects by URL.

Configuration (env):
  OPA_BASE_URL      OPA backend base URL            (default http://localhost:8001)
  OPA_PASSWORD      Login password for OPA_USERNAME (logs in via /api/auth/login
                    for a JWT; needed when REQUIRE_AUTH is on)
  OPA_USER_ID       Act as this OPA user_id         (optional)
  OPA_USERNAME      ...or resolve identity by username (optional)
                    If neither is set, auto-selects a seeded admin (all apps).
  MCP_BEARER_TOKEN  If set, /mcp requires `Authorization: Bearer <token>` —
                    a simple shared-secret gate for the remote endpoint.
  MCP_HOST          Bind host                        (default 0.0.0.0)
  MCP_PORT          Bind port                        (default $PORT or 8090)

Run:  python server/mcp_remote.py
Client connects to:  http(s)://<host>:<port>/mcp
"""
from __future__ import annotations

import contextlib
import os

import httpx
import mcp.types as types
import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount

from app.services.assistant.tools import TOOLS

OPA_BASE_URL = os.getenv("OPA_BASE_URL", "http://localhost:8001").rstrip("/")
OPA_PASSWORD = os.getenv("OPA_PASSWORD")
OPA_USER_ID = os.getenv("OPA_USER_ID")
OPA_USERNAME = os.getenv("OPA_USERNAME")
MCP_BEARER_TOKEN = os.getenv("MCP_BEARER_TOKEN")
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", os.getenv("PORT", "8090")))
_TIMEOUT = float(os.getenv("OPA_TIMEOUT", "120"))
MAX_TOOL_RESULT_CHARS = 24_000

# Resolved identity + gate token caches (stable for the server's lifetime).
_identity: tuple[str, str] | None = None
_token: str | None = None


async def _ensure_token(client: httpx.AsyncClient) -> str | None:
    """Obtain a JWT via OPA_USERNAME + OPA_PASSWORD login, cached. Optional —
    None when not configured; X-User-Id then carries identity."""
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
    if OPA_USER_ID:
        _identity = (OPA_USER_ID, "admin")
        return _identity
    resp = await client.get(f"{OPA_BASE_URL}/api/users", headers=_headers(token))
    resp.raise_for_status()
    users = resp.json()
    if OPA_USERNAME:
        chosen = next((u for u in users if u.get("username") == OPA_USERNAME), None)
        if chosen is None:
            raise RuntimeError(f"OPA_USERNAME '{OPA_USERNAME}' not found in OPA users")
    else:
        chosen = next((u for u in users if u.get("role") == "admin"), None) or (users[0] if users else None)
        if chosen is None:
            raise RuntimeError("No OPA users found; is the backend seeded?")
    _identity = (chosen["id"], chosen.get("role", "analyst"))
    return _identity


async def _call_endpoint(tool_name: str, arguments: dict) -> str:
    """Map an MCP tool call to its OPA GET endpoint and return the response text."""
    tool = next((t for t in TOOLS if t.name == tool_name), None)
    if tool is None or not tool.method:
        return f"Unknown tool: {tool_name}"

    path = tool.path
    for p in tool.path_params:
        path = path.replace("{" + p + "}", str(arguments.get(p, "")))
    params = {k: arguments[k] for k in tool.query_params if arguments.get(k) is not None}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            user_id, role = await _resolve_identity(client)
            token = await _ensure_token(client)
            r = await client.request(
                tool.method, f"{OPA_BASE_URL}{path}",
                params=params, headers=_headers(token, user_id, role),
            )
    except httpx.ConnectError:
        return f"Could not reach the OPA backend at {OPA_BASE_URL}."
    except Exception as e:  # pragma: no cover
        return f"OPA request failed: {e}"

    body = r.text
    if len(body) > MAX_TOOL_RESULT_CHARS:
        body = body[:MAX_TOOL_RESULT_CHARS] + "\n…[truncated]"
    if r.status_code >= 400:
        return f"OPA error (HTTP {r.status_code}): {body}"
    return body


# ── MCP server (low-level, so each tool keeps its own JSON schema) ─────────
server = Server("opa-tools")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name=t.name, description=t.description, inputSchema=t.input_schema)
        for t in TOOLS
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.ContentBlock]:
    text = await _call_endpoint(name, arguments or {})
    return [types.TextContent(type="text", text=text)]


# ── Streamable-HTTP transport, served at /mcp ──────────────────────────────
_session_manager = StreamableHTTPSessionManager(app=server, stateless=True)


def _bearer_guard(asgi_app):
    """Optional shared-secret gate: when MCP_BEARER_TOKEN is set, require it."""
    async def wrapped(scope, receive, send):
        if scope["type"] == "http" and MCP_BEARER_TOKEN:
            headers = dict(scope.get("headers") or [])
            auth = headers.get(b"authorization", b"").decode()
            if auth != f"Bearer {MCP_BEARER_TOKEN}":
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"Unauthorized"})
                return
        await asgi_app(scope, receive, send)
    return wrapped


async def _handle_mcp(scope, receive, send):
    await _session_manager.handle_request(scope, receive, send)


@contextlib.asynccontextmanager
async def _lifespan(_app: Starlette):
    async with _session_manager.run():
        yield


app = Starlette(
    routes=[Mount("/mcp", app=_bearer_guard(_handle_mcp))],
    lifespan=_lifespan,
)


if __name__ == "__main__":
    # proxy_headers/forwarded_allow_ips: correct client info behind Railway's proxy.
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT,
                proxy_headers=True, forwarded_allow_ips="*")
