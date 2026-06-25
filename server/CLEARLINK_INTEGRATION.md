# ClearLink Integration with OPA Assistant

The OPA Assistant can now access ClearLink member clinical data tools through the MCP server. This enables correlation of PayGuard claims with ClearLink member health records.

## What Was Added

### 1. **clearlink_integration.py** (`app/services/assistant/`)
Handles communication with the ClearLink MCP server:
- `fetch_clearlink_tools()` — Fetch available tools from MCP (async)
- `call_clearlink_tool()` — Execute a tool on the MCP server (async, HTTP)

### 2. **tools.py** (Modified)
Added 6 new ClearLink tools available to PayGuard users:
- `list_medications` — Get member's medications
- `list_diagnoses` — Get member's diagnoses (ICD-10, HCC, RAF)
- `list_dates_of_service` — Get member's visits/encounters
- `get_claims_window` — Get member's claims in a date range
- `get_labs_window` — Get member's lab results in a date range
- `list_prior_authorizations` — Get member's prior authorizations
- `get_member_demographics` — Get member demographics

All tools require `member_id` (from PayGuard case) as input.

### 3. **agent.py** (Modified)
Updated the `_execute()` method to:
- Detect ClearLink tools (path starts with `/mcp/proxy/`)
- Route them to `call_clearlink_tool()` instead of in-process ASGI calls
- Handle HTTP responses and errors

### 4. **.env** (Modified)
Added configuration:
```env
CLEARLINK_MCP_URL=http://localhost:8010/mcp
CLEARLINK_MCP_API_KEY=test-key-dev
```

## Setup & Testing

### Prerequisites

1. **ClearLink server running** on port 8010 with MCP enabled
   ```bash
   # In /Users/issamzeinoun/claude/clearlink:
   npm start
   ```

2. **OPA server environment configured**
   - `.env` file already updated with CLEARLINK_MCP_URL and CLEARLINK_MCP_API_KEY
   - Both must match the ClearLink configuration

### Start OPA Server

```bash
cd /Users/issamzeinoun/claude/overcoding/opa/server
python -m uvicorn app.main:app --port 8001 --reload
```

### Test Via Assistant UI

1. Open Assistant at http://localhost:5179
2. Login (if required)
3. Ask about a case that includes member data:

```
"Show me case 123 and the member's active medications"
```

The assistant will:
1. Call `get_case` (OPA, in-process) → Get case details including member_id
2. Call `list_medications` (ClearLink, via MCP) → Get member's medications
3. Correlate the data and present to the user

### Example Conversation Flow

**User:** "Check if member 42's medications align with the diagnoses in case 456"

**Assistant:**
1. Calls `get_case(case_id=456)` → Gets case details, member_id = 42
2. Calls `list_diagnoses(member_id="42")` → Gets diagnoses (Diabetes, Hypertension)
3. Calls `list_medications(member_id="42")` → Gets medications (Metformin, Lisinopril)
4. Correlates: "Member's medications align with diagnoses"

**Detailed Correlation Query**

```
"For case 678, verify the claim procedure date against the member's dates of service"
```

Assistant will:
1. Get case → member_id = 98765, procedure date = 2024-03-15
2. Call `list_dates_of_service(member_id="98765", date_from="2024-03-01", date_to="2024-03-31")`
3. Find matching visit on 2024-03-15
4. Confirm procedure aligns with DOC

## Architecture

```
┌─ Assistant (React) ────────────────────┐
│  User asks: "Check member meds"       │
│  sends to POST /api/assistant/chat     │
└──────────────┬───────────────────────┘
               │
        ┌──────▼──────┐
        │ OPA Server  │
        │ agent.py    │
        └──────┬──────┘
               │
        ┌──────▴──────────┐
        │                 │
     OPA tools      ClearLink tools
     (in-process)   (/mcp/proxy/*)
        │                 │
        ├─────────────────┘
        │    calls
        │    call_clearlink_tool()
        │
        ▼ HTTP + API Key
   ClearLink MCP Server
   (port 8010/mcp)
        │
        ▼
   Database (SQLite)
   agent_tools table
   (tool definitions)
        │
        ▼
   Tool Executors
   (SQL/HTTP/Internal)
```

## Error Handling

If ClearLink is unavailable:
- Assistant continues to work with OPA tools only
- ClearLink tool calls return: `"ClearLink MCP not configured"`
- Check logs for connection errors: `logger.warning(...)`

## Adding More Tools

To add a new ClearLink tool to the assistant:

1. **Add the tool to ClearLink's `agent_tools` table**
   ```sql
   INSERT INTO agent_tools (name, description, ..., enabled)
   VALUES ('my_new_tool', 'Description...', ..., 1);
   ```

2. **Add a Tool definition to OPA's `tools.py`**
   ```python
   Tool(
       name="my_new_tool",
       description="...",
       apps=("payguard",),
       method="GET",
       path="/mcp/proxy/tools/my_new_tool",  # Must follow this format
       query_params=("member_id", "other_param"),
       input_schema={...},
   ),
   ```

3. **Restart OPA server**
   - Tool immediately available to assistant

## Monitoring

### Log Tool Calls

Check OPA server logs for ClearLink tool execution:
```
INFO assistant tool=list_medications (clearlink) user=123 ok=True dur=245ms
```

### Monitor ClearLink Calls

Check ClearLink database for tool calls:
```sql
SELECT agent_name, tool_name, ok, duration_ms
FROM agent_tool_calls
WHERE agent_name = 'MCP'
ORDER BY created_at DESC
LIMIT 20;
```

## Troubleshooting

### "ClearLink MCP not configured"

Check:
1. `.env` has `CLEARLINK_MCP_URL` and `CLEARLINK_MCP_API_KEY`
2. ClearLink server running: `curl -H "X-API-Key: test-key-dev" http://localhost:8010/mcp/health`
3. API keys match between OPA and ClearLink

### Tool Not Found

Check:
1. Tool is enabled in ClearLink: `SELECT name, enabled FROM agent_tools WHERE name = 'list_medications'`
2. Tool name in OPA matches ClearLink: `path="/mcp/proxy/tools/list_medications"`
3. Restart OPA server to reload tool definitions

### Slow Tool Execution

- Check ClearLink DB performance (query plans)
- Check network latency between OPA and ClearLink
- Consider caching frequently-accessed data

## Security Notes

- OPA forwards user identity (`X-User-Id`) to ClearLink
- ClearLink validates the API key on every request
- Tool calls are logged in both systems for audit trail
- Member data is read-only (no write tools exposed)

## Future Enhancements

1. **Caching** — Cache member data for 5 minutes to reduce API calls
2. **Batch Tools** — Get multiple members' data in one call
3. **More Tools** — Add write tools (diagnoses update, medication change, etc.)
4. **Async Prefetch** — Prefetch member data when case is opened

## Files Modified

- `app/services/assistant/agent.py` — Updated `_execute()` method
- `app/services/assistant/tools.py` — Added ClearLink Tool definitions
- `app/services/assistant/clearlink_integration.py` — New file
- `.env` — Added CLEARLINK_MCP_* configuration
