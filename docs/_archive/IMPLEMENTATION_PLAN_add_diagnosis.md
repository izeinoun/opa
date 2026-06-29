# Implementation Plan: Add Diagnosis Tool to ClearLink MCP

## Overview
Enable the Assistant to suggest and add new diagnoses to ClearLink member records when they're found in claims but not in the medical records.

## Architecture
- **Database**: ClearLink's `agent_tools` table stores tool metadata
- **Execution**: ClearLink's `toolExecutor.js` routes tool calls to endpoints or SQL templates
- **MCP**: Tools are exposed via `/mcp/tools` endpoint
- **OPA Integration**: Assistant calls tools via `/mcp/proxy/` endpoint

---

## Phase 1: ClearLink Database & Tools Setup

### 1.1 Ensure agent_tools Table Exists
**File**: `server/db/migrations/016_agent_config_tools.sql` (verify/update)

```sql
-- Verify this table has all required columns
CREATE TABLE IF NOT EXISTS agent_tools (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  name                  TEXT NOT NULL UNIQUE,
  description           TEXT,
  kind                  TEXT NOT NULL DEFAULT 'http',  -- 'http', 'sql', 'mock'
  endpoint_url          TEXT,                           -- For HTTP tools
  http_method           TEXT DEFAULT 'POST',
  auth_header_name      TEXT,
  auth_header_format    TEXT,
  api_key               TEXT,
  additional_headers    TEXT,
  sql_template          TEXT,                           -- For SQL tools
  input_schema          TEXT,                           -- JSON schema
  mock_enabled          INTEGER DEFAULT 0,
  mock_response         TEXT,
  enabled               INTEGER NOT NULL DEFAULT 1,
  created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 1.2 Add New "add_diagnosis" Tool Definition
**File**: Create `server/db/migrations/023_add_diagnosis_tool.sql`

```sql
-- Add tool for adding new diagnoses to member records
INSERT OR REPLACE INTO agent_tools (
  name,
  description,
  kind,
  endpoint_url,
  http_method,
  input_schema,
  enabled
) VALUES (
  'add_diagnosis',
  'Add a new diagnosis to a member''s medical record. Use when a diagnosis is found in a claim but not in the member''s active diagnoses. Requires analyst confirmation before adding. Returns the newly added diagnosis record.',
  'http',
  'http://localhost:8001/api/clearlink/add-diagnosis',  -- OPA endpoint that proxies to ClearLink
  'POST',
  '{
    "type": "object",
    "properties": {
      "member_id": {
        "type": "string",
        "description": "Member ID"
      },
      "icd10_code": {
        "type": "string",
        "description": "ICD-10 diagnosis code (e.g., M79.3)"
      },
      "description": {
        "type": "string",
        "description": "Diagnosis description"
      },
      "source": {
        "type": "string",
        "description": "Source of diagnosis (e.g., claim number, visit date)"
      },
      "date_diagnosed": {
        "type": "string",
        "description": "Date diagnosis was identified (YYYY-MM-DD)"
      },
      "requires_verification": {
        "type": "boolean",
        "description": "Flag this diagnosis for analyst verification before activation",
        "default": true
      }
    },
    "required": ["member_id", "icd10_code", "date_diagnosed"]
  }',
  1
);
```

---

## Phase 2: ClearLink Endpoint Implementation

### 2.1 Create Endpoint in ClearLink
**File**: `server/routes/mcpTools.js` (new file or add to existing)

```javascript
import express from 'express';
import db from '../db/database.js';

const router = express.Router();

// Add new diagnosis to member record
router.post('/add-diagnosis', (req, res) => {
  const {
    member_id,
    icd10_code,
    description,
    source,
    date_diagnosed,
    requires_verification = true
  } = req.body;

  // Validate inputs
  if (!member_id || !icd10_code || !date_diagnosed) {
    return res.status(400).json({
      success: false,
      error: 'Missing required fields: member_id, icd10_code, date_diagnosed'
    });
  }

  try {
    // Find member
    const member = db.prepare('SELECT id FROM members WHERE member_id = ?').get(member_id);
    if (!member) {
      return res.status(404).json({
        success: false,
        error: `Member not found: ${member_id}`
      });
    }

    // Check if diagnosis already exists
    const existing = db.prepare(`
      SELECT id FROM diagnoses 
      WHERE member_id = ? AND icd10_code = ? AND status = 'active'
    `).get(member.id, icd10_code);

    if (existing) {
      return res.status(409).json({
        success: false,
        error: `Diagnosis ${icd10_code} already exists for this member`
      });
    }

    // Insert new diagnosis
    const result = db.prepare(`
      INSERT INTO diagnoses (
        member_id,
        icd10_code,
        description,
        source,
        date_diagnosed,
        status,
        requires_verification,
        created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    `).run(
      member.id,
      icd10_code,
      description || '',
      source || '',
      date_diagnosed,
      requires_verification ? 'pending_verification' : 'active',
      requires_verification ? 1 : 0
    );

    // Return newly added diagnosis
    res.json({
      success: true,
      data: {
        id: result.lastID,
        member_id,
        icd10_code,
        description,
        source,
        date_diagnosed,
        status: requires_verification ? 'pending_verification' : 'active',
        created_at: new Date().toISOString()
      }
    });

  } catch (err) {
    console.error('Error adding diagnosis:', err);
    res.status(500).json({
      success: false,
      error: err.message
    });
  }
});

export default router;
```

### 2.2 Register Endpoint
**File**: `server/index.js` (or main app file)

```javascript
import mcpToolsRouter from './routes/mcpTools.js';

app.use('/api/clearlink', mcpToolsRouter);
```

---

## Phase 3: OPA Backend Integration

### 3.1 Add Proxy Endpoint in OPA
**File**: `server/app/routes/clearlink_proxy.py` (new file)

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import require_role
from ..models.workflow import OpaUser

router = APIRouter(prefix="/api/clearlink", tags=["clearlink"])

@router.post("/add-diagnosis")
async def proxy_add_diagnosis(
    payload: dict,
    user: OpaUser = Depends(require_role("analyst", "admin")),
    db: AsyncSession = Depends(get_db)
):
    """Proxy add_diagnosis tool call to ClearLink MCP server."""
    
    import httpx
    import os
    
    CLEARLINK_URL = os.getenv("CLEARLINK_MCP_URL", "http://localhost:8010")
    API_KEY = os.getenv("CLEARLINK_API_KEY", "test-key-dev")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{CLEARLINK_URL}/api/clearlink/add-diagnosis",
                json=payload,
                headers={"X-API-Key": API_KEY},
                timeout=10
            )
            
            result = response.json()
            
            # Log audit trail
            await db.execute(text(f"""
                INSERT INTO audit_logs (
                    actor_user_id, action, created_at
                ) VALUES (
                    '{user.user_id}',
                    'Added diagnosis {payload.get("icd10_code")} to member {payload.get("member_id")}',
                    CURRENT_TIMESTAMP
                )
            """))
            await db.commit()
            
            return result
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add diagnosis: {str(e)}"
        )
```

### 3.2 Add Route to Main App
**File**: `server/app/main.py`

```python
from .routes import clearlink_proxy

app.include_router(clearlink_proxy.router)
```

---

## Phase 4: Assistant Integration

### 4.1 Update Assistant Tools Configuration
The tool will automatically be available via the MCP proxy once it's in the agent_tools table.

### 4.2 Update Assistant System Prompt
**File**: `server/app/services/assistant/agent.py` (update system prompt or tool instructions)

Add guidance for when to suggest adding diagnoses:

```
When analyzing a claim against a member's medical records:
- If you find a diagnosis in the claim that is NOT in the member's active diagnoses
- Check if it's a NEW diagnosis (recent date)
- If YES, offer to add it: "I found diagnosis [CODE] in the claim dated [DATE]. 
  Should I add this to the member's medical records?"
- Use the add_diagnosis tool to add it WITH requires_verification=true
- This creates a pending_verification status for analyst review
```

---

## Phase 5: Testing

### 5.1 Test Case: Robert Hargrove
```
Scenario: Claim has M79.3 (Panniculitis) not in member's records
Expected: Assistant identifies it, asks analyst, adds it with verification flag
Result: Record added to ClearLink with pending_verification status
```

### 5.2 Analyst Workflow
```
1. Assistant suggests: "Found new diagnosis M79.3 in claim CLM-2024-ROBERT-001"
2. Analyst reviews: "Yes, add it" OR "No, incorrect coding"
3. If yes: Tool adds it with pending_verification=true
4. Analyst later verifies and activates it in ClearLink UI
```

---

## Success Criteria

✅ ClearLink has "add_diagnosis" tool in agent_tools table
✅ Endpoint accepts POST requests with diagnosis data
✅ Tool validates member exists and diagnosis doesn't duplicate
✅ New diagnoses are marked "pending_verification" by default
✅ OPA proxy forwards requests correctly
✅ Assistant knows about tool and suggests using it
✅ Audit trail logs all additions with analyst user ID
✅ Robert's M79.3 can be added and reviewed by analyst

---

## Files to Create/Modify

| File | Type | Action |
|------|------|--------|
| `clearlink/server/db/migrations/023_add_diagnosis_tool.sql` | Create | Add tool definition |
| `clearlink/server/routes/mcpTools.js` | Create | Endpoint implementation |
| `clearlink/server/index.js` | Modify | Register route |
| `opa/server/app/routes/clearlink_proxy.py` | Create | OPA proxy |
| `opa/server/app/main.py` | Modify | Include router |

