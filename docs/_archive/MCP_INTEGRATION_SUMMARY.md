# MCP Server Integration Summary

**Added by:** Another Claude Code instance  
**Date:** 2026-06-24  
**Scope:** Backend server only (no client-side impact)

---

## What Was Added

### 1. ClearLink MCP Integration

**New File:** `server/app/services/assistant/clearlink_integration.py`

Allows the OPA Assistant to call tools from a ClearLink MCP server:
- Fetches available tools from ClearLink at startup
- Executes tools via HTTP to ClearLink MCP endpoint
- Passes member clinical data lookups through the assistant

**Configuration:**
```env
CLEARLINK_MCP_URL=http://localhost:8010/mcp
CLEARLINK_MCP_API_KEY=<secret key>
```

### 2. Assistant Tool Execution Updated

**Modified:** `server/app/services/assistant/agent.py`

Added MCP tool routing:
- Tools with path `/mcp/proxy/...` are routed to ClearLink
- Tools without `/mcp/` prefix continue to run in-process (OPA tools)
- Maintains backward compatibility

### 3. Remote MCP Server Configuration

**File:** `railway.mcp.toml`

Separate Railway service configuration for a remote MCP server:
- Runs `server/mcp_remote.py`
- Exposes OPA tools over HTTP
- Allows external systems to query OPA via MCP protocol

### 4. MCP Server Files (Backend Infrastructure)

```
server/mcp_server.py          — stdio-based MCP server for Claude Desktop
server/mcp_remote.py          — HTTP-based remote MCP server
server/app/mcp_mount.py       — MCP tool mounting/registration
server/app/mcp_format.py      — Tool definition format conversion
railway.mcp.toml              — Railway deployment config for remote MCP
```

---

## Impact on Phase 1 Persistent Drawer Work

✅ **NO CONFLICTS**

- MCP integration is entirely **server-side**
- Client-side drawer implementation is **unaffected**
- Different components of the system
- Independent deployment and configuration

---

## Architecture After MCP Integration

```
┌─ OPA Web App ─────────────────────┐
│  Browser                          │
│  ┌─ PayGuard Client (React) ──┐  │
│  │ • Persistent drawer ✅      │  │
│  │ • Collapsible nav ✅        │  │
│  │ • Two-mode width ✅         │  │
│  └─ (This Phase 1 work) ──────┘  │
│                ↓ HTTP               │
│  ┌─ FastAPI Backend ──────────┐  │
│  │ • Assistant service        │  │
│  │ • Tool execution           │  │
│  │ ├─ OPA tools (in-process)  │  │
│  │ └─ ClearLink tools (MCP)   │  │ ← Added by other instance
│  └────────────────────────────┘  │
└───────────────────────────────────┘
         ↓ HTTP                ↓ HTTP
    [OPA Database]     [ClearLink MCP]
```

---

## What Works Together

1. **Phase 1 Persistent Drawer** (This session)
   - Users see assistant on right side
   - Can collapse/expand nav and assistant
   - Context updates automatically

2. **MCP Tool Integration** (Other session)
   - When user asks assistant a question
   - Assistant can now call ClearLink tools (via MCP)
   - Or call OPA tools (in-process)
   - Results streamed back to user in drawer

---

## Configuration Needed (If Using ClearLink)

To enable ClearLink MCP integration:

```bash
# In your .env or deployment config:
export CLEARLINK_MCP_URL=http://localhost:8010/mcp
export CLEARLINK_MCP_API_KEY=your-secret-key

# Restart the OPA backend
make backend
```

If `CLEARLINK_MCP_API_KEY` is not set, ClearLink tools are skipped (graceful degradation).

---

## Testing MCP Integration (Optional)

```bash
# 1. Start ClearLink MCP server on port 8010
cd ../clearlink
npm run dev  # or equivalent

# 2. Start OPA backend with ClearLink configured
export CLEARLINK_MCP_URL=http://localhost:8010/mcp
export CLEARLINK_MCP_API_KEY=test-key
cd server && python -m uvicorn app.main:app --reload --port 8001

# 3. Ask assistant a question that requires member lookup
# "What's the clinical history for member ABC123?"
# Assistant should call ClearLink tool and return results
```

---

## No Client-Side Changes Needed

✅ PayGuard client doesn't need to know about MCP  
✅ MCP is backend infrastructure  
✅ Client only sees responses via existing API  
✅ Phase 1 persistent drawer works independently  

---

## Future Integrations

If additional MCP servers are added:
1. Create new integration file (e.g., `siu_integration.py`)
2. Add tool path routing (e.g., `/mcp/siu/...`)
3. Add env config for URL + API key
4. Tools automatically appear in assistant

---

## Files Affected by MCP Changes

**New:**
- `server/app/services/assistant/clearlink_integration.py`
- `server/mcp_server.py` (already existed, likely enhanced)
- `server/mcp_remote.py` (already existed)

**Modified:**
- `server/app/services/assistant/agent.py` (added MCP routing logic)
- Possibly `server/app/services/assistant/tools.py` (tool registration)

**Deployed separately:**
- `railway.mcp.toml` (separate Railway service, not web app)

---

## Summary

✅ **Phase 1 Persistent Drawer:** Complete and unaffected  
✅ **MCP Integration:** Complete, server-side only  
✅ **No conflicts:** Both can coexist and work together  
✅ **User experience:** Enhanced (assistant can now call more tools)

---

Generated: 2026-06-24
