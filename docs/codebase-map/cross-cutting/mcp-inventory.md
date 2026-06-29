# MCP Inventory — all servers, tools, transports, auth

> Two MCP servers in the suite: **OPA** (Python, FastAPI-mounted + standalone stdio/HTTP) and **ClearLink** (Node, in-process at `/mcp`). OPA is also an MCP *client* of ClearLink. No frontend is an MCP client — all MCP traffic is server-side.

## Servers & transports

| Server | Transport | Mount/entry | Auth | Code |
|--------|-----------|-------------|------|------|
| OPA granular | HTTP, mounted on FastAPI | `/mcp` | inherits OPA auth chain | `server/app/mcp_mount.py`, `mcp_format.py` |
| OPA standalone | stdio (Claude Desktop/Cowork) | `server/mcp_server.py` | local | `mcp_server.py` |
| OPA remote | HTTP | `server/mcp_remote.py` | API key | `mcp_remote.py` |
| ClearLink | HTTP JSON-RPC, in-process | `/mcp` (shares main :8010) | `X-API-Key` == `MCP_API_KEY` | `clearlink/server/mcp/mcpServer.js`, `toolProvider.js`, `toolExecutor.js` |

## OPA tools — granular `/mcp` (≈25, from `server/app/services/assistant/tools.py`)

All map to **READ** routes/services. The ONLY write path is the 3 UI tools.

| Tool | Backs | Type |
|------|-------|------|
| `search_cases` | case search route | read |
| `get_case` / `get_case_guidance` | case detail/guidance | read |
| dashboard tools (worklist, my_dashboard, briefing) | dashboard routes | read |
| `list_prepay_claims` | prepay claims list | read |
| `get_member_360` | member aggregate | read |
| provider-risk tools | provider scoring | read |
| ClearLink proxy tools | forwarded to ClearLink MCP | read (proxied) |
| `ask_user` | UI prompt | **WRITE-gate** |
| `present_view` | UI navigation directive | **WRITE-gate** |
| `confirm_action` | UI confirm before mutation | **WRITE-gate** |

**Write rule:** the agent cannot mutate state except by routing through `ask_user`/`present_view`/`confirm_action`, which require human confirmation in the UI. Preserve this invariant when adding tools.

## OPA tools — standalone stdio (`server/mcp_server.py`)

`ask_opa`, `send_email`, `search_claimguard_claims`, `get_member_360`.

## ClearLink tools — `agent_tools` registry rows (≈11)

Tools are **DB-driven**: each row in `agent_tools` defines `kind` (http|sql|internal), `sql_template`, `endpoint_url`, `input_schema`, `mock_*`, `for_agents`. `toolProvider.js` discovers enabled rows; `toolExecutor.js` dispatches.

| Tool | kind | Backing |
|------|------|---------|
| `add_diagnosis` | http | → ClearLink `/api/clearlink/add-diagnosis` route |
| `explain_pcmh_tier` | internal | RAF/PCMH trace |
| `get_member_demographics` | sql | members table |
| `list_diagnoses` | sql | diagnoses |
| `list_medications` | sql | medications |
| `list_dates_of_service` | sql | DOS |
| `get_claims_window` | sql | claims |
| `get_labs_window` | sql | labs |
| `get_provider_messages` | sql | provider msgs |
| `list_prior_authorizations` | sql | prior auths |
| `get_socioeconomic_profile` | http | external demo HTTP |
| `search_members` | (LLM fuzzy) | ✅ CALLABLE (Phase 0 verified): enabled `agent_tools` row (`kind=sql`) IS present; MCP-listed via `toolProvider.js` (special-cased line 68); `toolExecutor.js:115` intercepts the name → runs LLM `fuzzySearchMembers` (`toolExecutor.js:11`) regardless of the `sql` kind. |

## OPA ↔ ClearLink MCP client edge

OPA consumes ClearLink's clinical/diagnosis tools via `server/app/services/assistant/clearlink_integration.py:21` + `clearlink_proxy.py:48`. Dynamic discovery: OPA fetches ClearLink's tool list at runtime (see commit `0818c3d` "dynamic ClearLink tool discovery"). Env: `CLEARLINK_MCP_URL` (default localhost:8010), `CLEARLINK_MCP_API_KEY`.

## MCP audit / tracking

- ClearLink logs every tool call to `agent_tool_calls` (agent_name, tool_name, input_json, output_json, ok, duration_ms). **BUG:** `mcpTools.js:143` passes args object-vs-positional mismatched to `auditLog` → MCP audit rows dropped. Fix before relying on MCP audit trail.
- OPA: MCP identity-resolution logic is **duplicated** between `mcp_mount.py` and `mcp_server.py` — consolidate.

## Gaps / risks (MCP-specific)

1. ~~ClearLink `search_members` uncallable~~ → ❌ PHANTOM (Phase 0): it IS callable via LLM fuzzy. Minor: registry row says `kind=sql` while executor runs LLM — cosmetic mismatch, harmless.
2. ClearLink `add-diagnosis` REST route has no auth even though `requireApiKey` is imported.
3. ClearLink MCP audit dropped (signature bug above).
4. Two Claude clients in ClearLink with conflicting model defaults (axios sonnet-4-6 vs SDK opus-4-8) — MCP fuzzy/extraction calls may use a different model than expected.
5. OPA write-gate (`ask_user`/`confirm_action`) is the security boundary — any new write tool must respect it.
