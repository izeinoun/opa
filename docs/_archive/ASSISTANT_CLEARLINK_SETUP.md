# Assistant ↔ ClearLink Integration Complete ✅

The OPA Assistant now has full access to ClearLink member clinical data tools via the MCP server.

## What Was Done

### Files Created
1. **`server/app/services/assistant/clearlink_integration.py`** (104 lines)
   - Handles HTTP communication with ClearLink MCP server
   - Async functions for fetching and executing ClearLink tools

### Files Modified
1. **`server/app/services/assistant/tools.py`** (+140 lines)
   - Added 7 new ClearLink tools to the `TOOLS` tuple
   - Tools available to PayGuard users only
   - All require `member_id` parameter

2. **`server/app/services/assistant/agent.py`** (+8 lines)
   - Imported `call_clearlink_tool` from clearlink_integration
   - Updated `_execute()` method to detect and route ClearLink tools
   - ClearLink tools detected by `/mcp/proxy/` path prefix

3. **`server/.env`** (+4 lines)
   - Added CLEARLINK_MCP_URL
   - Added CLEARLINK_MCP_API_KEY

### Documentation Created
- `server/CLEARLINK_INTEGRATION.md` — Full technical documentation
- This file — Quick start guide

## New Tools Available to Assistant

All tools require `member_id` from the PayGuard case:

| Tool | Purpose | Inputs |
|------|---------|--------|
| `list_medications` | Get active medications | member_id, status |
| `list_diagnoses` | Get diagnoses (ICD-10, HCC, RAF) | member_id, since, include_inactive |
| `list_dates_of_service` | Get visits/encounters | member_id, visit_type, date_from, date_to |
| `get_claims_window` | Get claims in date range | member_id, date_from, date_to |
| `get_labs_window` | Get lab results in date range | member_id, date_from, date_to |
| `list_prior_authorizations` | Get prior auth requests | member_id, status |
| `get_member_demographics` | Get member info | member_id |

## Quick Start (2 Steps)

### Step 1: Verify ClearLink is Running

```bash
# Check ClearLink MCP health
curl -H "X-API-Key: test-key-dev" http://localhost:8010/mcp/health

# Expected response:
# {"status":"ok","mcp_server":"online"}
```

### Step 2: Restart OPA Server

```bash
cd /Users/issamzeinoun/claude/overcoding/opa/server
python -m uvicorn app.main:app --port 8001 --reload
```

## Test It

### Via Assistant UI

Open http://localhost:5179 and ask:

```
"In case 123, what medications is the member taking?"
```

Or:

```
"For case 456, verify the procedure date against the member's visit history"
```

### Via API (curl)

```bash
curl -X POST http://localhost:8001/api/assistant/chat/stream \
  -H "Content-Type: application/json" \
  -H "Cookie: auth_token=..." \
  -d '{
    "messages": [
      {"role": "user", "content": "Show me medications for member 42"}
    ],
    "context": {"active_case_id": 123}
  }'
```

## How It Works

1. **User asks** → "What meds is member 42 on?"
2. **Assistant has context** → member_id = 42 (from active case)
3. **Assistant calls** → `list_medications(member_id="42")`
4. **Agent routes** → Detects `/mcp/proxy/` path, calls `call_clearlink_tool()`
5. **HTTP call** → POST to http://localhost:8010/mcp/tools/list_medications/call
6. **ClearLink executes** → Queries DB, returns results
7. **Assistant receives** → JSON with medications
8. **Assistant presents** → User sees formatted response

## Architecture Diagram

```
┌──────────────────────────────────┐
│   Assistant UI (React)           │
│   http://localhost:5179          │
└────────────────┬─────────────────┘
                 │ POST /api/assistant/chat/stream
                 │
        ┌────────▼─────────┐
        │   OPA Server     │
        │   :8001          │
        └────────┬─────────┘
                 │
        ┌────────▴──────────────┐
        │                       │
     OPA Tools            ClearLink Tools
  (PayGuard data)       (member data)
  in-process calls      HTTP calls
        │                       │
        │                  calls_clearlink_tool()
        │                       │
        └───────────────────────┤
                                │
                    ┌───────────▼──────┐
                    │  ClearLink MCP   │
                    │  :8010/mcp       │
                    └───────────┬──────┘
                                │
                        ┌───────▴──────┐
                        │              │
                    ClearLink DB   OPA Agent Executor
                    member data    (SQL/HTTP/Internal)
```

## Configuration Files

### ClearLink (.env)
```env
MCP_API_KEY=test-key-dev
```

### OPA (.env)
```env
CLEARLINK_MCP_URL=http://localhost:8010/mcp
CLEARLINK_MCP_API_KEY=test-key-dev
```

Both must have matching API keys and correct URLs.

## Verify Integration

### Check if tools are registered:

Open http://localhost:8001 and call:
```bash
curl -X GET http://localhost:8001/api/assistant/tools \
  -H "Cookie: auth_token=..." | jq '.tools[] | select(.apps | contains(["payguard"])) | .name'
```

You should see all 7 ClearLink tools listed.

### Check logs when a tool is called:

Look for in OPA server output:
```
INFO assistant tool=list_medications (clearlink) user=123 ok=True dur=245ms
```

Look for in ClearLink:
```
SELECT * FROM agent_tool_calls WHERE agent_name='MCP' ORDER BY created_at DESC;
```

## Common Scenarios

### Scenario 1: Validate Medical Necessity
```
User: "Is the claimed procedure medically necessary for this member?"