# Re-evaluate Rules Tool Implementation

## Overview

Added a **reevaluate-rules** tool that the Assistant can call to refresh all findings for a case from scratch. Essential when diagnosis codes change (e.g., 837 enrichment updates primary diagnosis).

## Implementation

### 1. New Endpoint
**File**: `server/app/routes/rules_evaluation.py`

```
POST /api/cases/{case_id}/reevaluate-rules
```

**What it does:**
- Deletes all existing findings for the case
- Re-runs all detectors against current claim
- Recalculates likelihood and priority scores
- Logs re-evaluation to audit trail
- Returns summary of findings before/after

**Response:**
```json
{
  "case_id": "...",
  "case_number": "OPA-2026-00027",
  "previous_finding_count": 3,
  "new_finding_count": 2,
  "new_findings": [
    {"detector_id": "DET-01", "title": "...", "overpayment_amount": 100, "confidence": 0.95}
  ],
  "updated_likelihood": 0.65,
  "updated_priority": 72,
  "message": "Rules re-evaluated: 2 finding(s) identified (was 3)"
}
```

### 2. Tool Registration

**File**: `server/app/services/assistant/tools.py`

Added to WRITE_ACTIONS:
```python
"reevaluate_rules": WriteAction("POST", "/api/cases/{case_id}/reevaluate-rules", ("case_id",), scope="case"),
```

**This enables:**
- The Assistant to call this as a write action
- User confirmation gate (analyst must confirm before running)
- Audit logging of who triggered the re-evaluation

### 3. System Prompt Update

**File**: `server/app/services/assistant/prompt.py`

Added guidance section:
```
RULES RE-EVALUATION (reevaluate_rules)
When diagnosis codes change (e.g., 837 enrichment updates the primary diagnosis from 
Z99.9 placeholder to real diagnosis), old findings may be stale. Call confirm_action with 
action="reevaluate_rules" to re-run all detectors from scratch against the current claim.
```

**When Assistant should suggest it:**
- User asks to "re-evaluate", "re-check", "refresh", "validate" rules
- Diagnosis codes just changed (837 enrichment)
- New diagnosis information is available
- Rules/detectors were updated

### 4. Router Registration

**File**: `server/app/main.py`

- Imported `rules_evaluation` module
- Registered router: `app.include_router(rules_evaluation.router)`

## Workflow

```
User: "Refresh the findings for case OPA-2026-00027 now that we have the real diagnosis"
     ↓
Assistant: "Should I re-evaluate the rules? This will delete current findings and run all detectors again."
     ↓
User: Confirm
     ↓
Tool executes:
  1. GET case + claim
  2. DELETE old findings
  3. RUN DetectorService.run_for_case()
  4. CREATE new findings
  5. RECALCULATE likelihood/priority
  6. LOG audit entry
     ↓
Response: "Rules re-evaluated: 2 findings identified (was 3)"
```

## Use Cases

### Robert Hargrove Case (OPA-2026-00027)

**Before:** M79.3 (Panniculitis) in claim, generates stale findings with Z99.9 placeholder diagnosis

**After 837 enrichment:** Primary diagnosis updated to I50.00 (Heart failure) or E11.9 (Diabetes)

**Then:** Assistant suggests re-evaluation → findings refresh to match real diagnosis

### Stacy Truman Case (OPA-2026-00026)

**Before:** Z99.9 placeholder from 835 creates invalid findings

**After 837 enrichment:** E11.9 (Diabetes) from medical records

**Then:** Assistant re-evaluates → Z99.9-dependent findings clear, real findings emerge

## Integration with add_diagnosis Tool

These tools work together:

1. **Assistant finds diagnosis in claim not in records** (e.g., M79.3)
2. **Suggests adding it** via `add_diagnosis` tool
3. **Analyst confirms** → Diagnosis added to ClearLink with verification flag
4. **Back in OPA, suggests re-evaluation** via `reevaluate_rules`
5. **Analyst confirms** → Findings refresh with new diagnosis data
6. **Result:** Clean, evidence-based findings for analyst review

## Implementation Notes

- Requires analyst or admin role (enforced by `require_role` dependency)
- Uses existing `DetectorService.run_for_case()` which already handles:
  - Deleting old findings
  - Running detectors
  - Handling dx_pending logic
  - Updating likelihood scores
- All mutations logged via AuditLogDAO
- Response includes before/after finding counts for transparency

## Git Commit

```
commit e98487e
feat: reevaluate-rules tool for refreshing findings when diagnosis changes
```

## Files Modified

1. `server/app/routes/rules_evaluation.py` (new)
2. `server/app/main.py` (imported + registered router)
3. `server/app/services/assistant/tools.py` (added to WRITE_ACTIONS)
4. `server/app/services/assistant/prompt.py` (added guidance section)
