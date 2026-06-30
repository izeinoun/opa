"""In-process mount of the granular MCP server onto the main FastAPI app.

Serves streamable-HTTP at **/mcp on the SAME service** as the web app + API, so a
single Railway service hosts both — clients (e.g. Claude Cowork) connect to
`https://<backend-host>/mcp`. Each MCP tool maps to one OPA READ endpoint
(generated from `services.assistant.tools.TOOLS`) and executes **in-process**
against this app (httpx ASGITransport), forwarding a configured OPA identity as
the X-User-Id header — no self-HTTP, no OPA_BASE_URL/OPA_PASSWORD needed.

This is the mounted counterpart to the standalone `server/mcp_remote.py`; use
one or the other (mounted here = one service; standalone = its own service).

Env:
  MCP_BEARER_TOKEN  If set, /mcp requires `Authorization: Bearer <token>`.
  OPA_USERNAME      Act as this OPA user (default: first admin → all apps).
"""
from __future__ import annotations

import os

import httpx
import mcp.types as types
from fastapi import FastAPI
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from .config import MCP_BEARER_TOKEN
from .mcp_format import MD_TOOLS, format_markdown
from .services.assistant.tools import TOOLS

OPA_USERNAME = os.getenv("OPA_USERNAME")
MAX_TOOL_RESULT_CHARS = 24_000

_app: FastAPI | None = None
_identity: tuple[str, str] | None = None


def init(app: FastAPI) -> None:
    """Give the mount the app to make in-process calls against."""
    global _app
    _app = app


def _new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app),
        base_url="http://mcp.internal",
    )


async def _resolve_identity() -> tuple[str, str]:
    """Which OPA user the MCP server acts as: OPA_USERNAME → first admin.
    Resolved directly from the DB in-process, so it needs no self-HTTP or auth
    (and therefore works under the REQUIRE_AUTH gate)."""
    global _identity
    if _identity is not None:
        return _identity
    from sqlalchemy import select
    from .database import AsyncSessionLocal
    from .models.workflow import OpaUser
    async with AsyncSessionLocal() as db:
        if OPA_USERNAME:
            user = (await db.execute(
                select(OpaUser).where(OpaUser.username == OPA_USERNAME)
            )).scalar_one_or_none()
            if user is None:
                raise RuntimeError(f"OPA_USERNAME '{OPA_USERNAME}' not found")
        else:
            user = (await db.execute(
                select(OpaUser).where(OpaUser.role == "admin").limit(1)
            )).scalar_one_or_none() or (await db.execute(
                select(OpaUser).limit(1)
            )).scalar_one_or_none()
            if user is None:
                raise RuntimeError("No OPA users found; is the backend seeded?")
    _identity = (user.user_id, user.role or "analyst")
    return _identity


async def _call_endpoint(name: str, arguments: dict) -> str:
    tool = next((t for t in TOOLS if t.name == name), None)
    if tool is None or not tool.method:
        return f"Unknown tool: {name}"
    path = tool.path
    for p in tool.path_params:
        path = path.replace("{" + p + "}", str(arguments.get(p, "")))
    params = {k: arguments[k] for k in tool.query_params if arguments.get(k) is not None}
    user_id, role = await _resolve_identity()
    async with _new_client() as client:
        headers = {"X-User-Id": user_id, "X-User-Role": role}
        r = await client.request(tool.method, path, params=params, headers=headers)
    if r.status_code >= 400:
        body = r.text
        if len(body) > MAX_TOOL_RESULT_CHARS:
            body = body[:MAX_TOOL_RESULT_CHARS] + "\n…[truncated]"
        return f"OPA error (HTTP {r.status_code}): {body}"
    # Structured tools → clean Markdown (Claude renders tables/cards faithfully).
    if name in MD_TOOLS:
        try:
            md = format_markdown(name, r.json())
        except Exception:
            md = None
        if md:
            return md
    body = r.text
    if len(body) > MAX_TOOL_RESULT_CHARS:
        body = body[:MAX_TOOL_RESULT_CHARS] + "\n…[truncated]"
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
    return [types.TextContent(type="text", text=await _call_endpoint(name, arguments or {}))]


# StreamableHTTPSessionManager.run() is entered by the app's lifespan.
session_manager = StreamableHTTPSessionManager(app=server, stateless=True)


async def mount_app(scope, receive, send):
    """ASGI app mounted at /mcp. Optional shared-secret bearer guard, then the
    streamable-HTTP handler."""
    if scope["type"] == "http" and MCP_BEARER_TOKEN:
        headers = dict(scope.get("headers") or [])
        if headers.get(b"authorization", b"").decode() != f"Bearer {MCP_BEARER_TOKEN}":
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"Unauthorized"})
            return
    await session_manager.handle_request(scope, receive, send)
