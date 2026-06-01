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
