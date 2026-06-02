# OPA Assistant — MCP server for Claude Desktop / cowork

Exposes the OPA read-only assistant to Claude Desktop as a single MCP tool,
**`ask_opa`**. When Claude Desktop calls it, the question is forwarded to OPA's
`/api/assistant/chat` endpoint, which runs the full Claude tool_use agent loop
server-side (selecting and calling OPA's READ APIs as tools) and returns a
grounded answer. RBAC scopes what the agent can see to the configured user's apps.

- Server script: [`server/mcp_server.py`](./server/mcp_server.py)
- Transport: **stdio** (Claude Desktop launches the process)
- It's a thin HTTP client — it does **not** import the FastAPI app or touch the
  DB, so it starts instantly and runs independently of the web process.

## Prerequisites

1. The OPA backend must be running and reachable (default `http://localhost:8001`):
   ```bash
   cd server && /Users/issamzeinoun/claude/overcoding/.venv/bin/uvicorn app.main:app --port 8001
   ```
2. `ANTHROPIC_API_KEY` set in `server/.env` (the agent loop calls Claude).
3. `mcp` installed in the venv (`pip install -r server/requirements.txt`).

## Install in Claude Desktop

Already wired into `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "opa-assistant": {
      "command": "/Users/issamzeinoun/claude/overcoding/.venv/bin/python",
      "args": ["/Users/issamzeinoun/claude/overcoding/opa/server/mcp_server.py"],
      "env": { "OPA_BASE_URL": "http://localhost:8001" }
    }
  }
}
```

**Restart Claude Desktop** to pick it up. Then ask, e.g., *"Use OPA to tell me how
many high-priority cases are open."* — Claude Desktop will call `ask_opa`.

## Configuration (env in the config block)

| Var | Default | Purpose |
|-----|---------|---------|
| `OPA_BASE_URL` | `http://localhost:8001` | OPA backend base URL |
| `OPA_PASSWORD` | — | Demo-gate password (required when the deployment sets `DEMO_PASSWORD`; the server logs in to get a token) |
| `OPA_USER_ID` | — | Act as this OPA user_id (RBAC scopes tools to their apps) |
| `OPA_USERNAME` | — | …or resolve identity by username (e.g. `rachel.burns`) |
| `OPA_TIMEOUT` | `120` | Per-request timeout (seconds) |

### Pointing at the deployed (gated) instance

To use the published site instead of localhost, set both in the config `env`:

```json
"env": {
  "OPA_BASE_URL": "https://payment-integrity.penguinai.studio",
  "OPA_PASSWORD": "<the deployment's DEMO_PASSWORD>"
}
```

The local config installed by default points at `http://localhost:8001` (the
ungated dev server), so it needs no password.

If neither `OPA_USER_ID` nor `OPA_USERNAME` is set, the server auto-selects a
seeded **admin** (so every app's tools are available). To act as, say, a
PayGuard+ClaimGuard analyst, add `"OPA_USERNAME": "ana.chen"` to the `env` block.

## Remote MCP server (Claude Cowork / hosted clients) — granular tools

`server/mcp_server.py` above is **stdio** and exposes one coarse `ask_opa` tool
(OPA runs its own agent loop). For **Claude Cowork** (a hosted surface that
connects to MCP servers by URL) there's a second server,
[`server/mcp_remote.py`](./server/mcp_remote.py), that:

- exposes **each OPA READ endpoint as its own MCP tool** — `search_cases`,
  `get_case`, `get_payguard_dashboard`, `get_prepay_*`, `get_siu_dashboard`,
  `search_members`, … (11 tools) — generated from the assistant tool registry
  (`app.services.assistant.tools.TOOLS`), so Cowork's *own* agent selects and
  orchestrates them;
- serves over **streamable-HTTP** at `/mcp` (a URL clients connect to), not stdio;
- stays a thin HTTP client (no app/DB import); each call hits the OPA backend as
  a configured OPA user (RBAC scopes what that user can read).

### Run

```bash
cd server
OPA_BASE_URL=http://localhost:8001 MCP_PORT=8090 \
  /Users/issamzeinoun/claude/overcoding/.venv/bin/python mcp_remote.py
# clients connect to:  http://localhost:8090/mcp
```

Verified end-to-end: an MCP client connects, lists all 11 tools, and calls them
against live data.

### Configuration (env)

| Var | Default | Purpose |
|-----|---------|---------|
| `OPA_BASE_URL` | `http://localhost:8001` | OPA backend base URL |
| `OPA_PASSWORD` | — | Demo-gate password (when the deployment sets `DEMO_PASSWORD`) |
| `OPA_USER_ID` / `OPA_USERNAME` | first admin | Which OPA user the server acts as (RBAC scope) |
| `MCP_BEARER_TOKEN` | — | If set, `/mcp` requires `Authorization: Bearer <token>` (shared-secret gate) |
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `$PORT` or `8090` | Bind address |

### Connecting Cowork

Point Cowork's MCP connector at the server URL (`https://<host>/mcp`) and, if
`MCP_BEARER_TOKEN` is set, supply that bearer. Deploy it as its own Railway
service (e.g. `mcp.penguinai.studio`) running `python mcp_remote.py`, or mount it
under the backend host.

> **Auth caveat / open item:** `MCP_BEARER_TOKEN` is a single shared secret and
> identity is a single configured OPA user — fine for a demo/service-account
> model. Per-user identity over MCP (so Cowork callers act as *themselves*) and
> OAuth-style auth are the production upgrade; wire them once Cowork's connector
> auth model is confirmed.

## Security note

OPA currently identifies users by the dev `X-User-Id` header (no API tokens).
That's fine for local desktop use, but a real deployment needs proper
token-based auth before exposing this beyond localhost. The tool is **read-only**
(it can retrieve/analyze, never mutate).

## Troubleshooting

- **"Could not reach the OPA backend"** → start uvicorn on the configured port.
- **403 / "lacks access"** → the configured user has no app access; set
  `OPA_USERNAME`/`OPA_USER_ID` to a user who does.
- **Tool not appearing** → fully quit and reopen Claude Desktop; confirm the JSON
  is valid and the `command` path points at the shared venv's python.
- **Inspect logs** → Claude Desktop writes MCP logs under
  `~/Library/Logs/Claude/`.
