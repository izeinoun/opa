# Assistant Output Sanitization - Safe Guards

## Problem Solved

Assistant responses were showing internal markup that shouldn't be visible to users:
- ``` ... ``` code block fences  
- @@FOLLOWUPS@@ [...] suggestion markers

## Solution: Defense-in-Depth

### Backend (Primary Layer)

**File**: `/server/app/services/assistant/agent.py`

Two functions clean the response before sending to frontend:

#### 1. `_strip_code_fence()` (line 81)
Removes wrapping markdown code fences that the LLM sometimes adds:
```python
def _strip_code_fence(text: str) -> str:
    """Remove wrapping ```html … ``` code fence"""
    t = (text or "").strip()
    if not t.startswith("```"):
        return text
    t = re.sub(r"^```[A-Za-z0-9]*[ \t]*\r?\n?", "", t)   # leading ```lang
    t = re.sub(r"\r?\n?```$", "", t.rstrip())            # trailing ```
    return t.strip()
```

#### 2. `_split_followups()` (line 67)
Removes internal follow-up suggestion markers:
```python
def _split_followups(text: str) -> tuple[str, list[str]]:
    """Split trailing @@FOLLOWUPS@@ ["q1","q2","q3"] out of text"""
    m = _FOLLOWUPS_RE.search(text or "")
    if not m:
        return text, []
    try:
        arr = json.loads(m.group(1))
        sugg = [str(s).strip() for s in arr if str(s).strip()][:4] if isinstance(arr, list) else []
    except Exception:
        sugg = []
    return text[: m.start()].rstrip(), sugg
```

**Applied at**: Line 338-339
```python
blk["text"] = _strip_code_fence(blk["text"])
blk["text"], sugg = _split_followups(blk["text"])
```

### Frontend (Safety Net)

Created new utility functions in both assistants to catch anything that slips through:

#### OPA Assistant Standalone
**File**: `/assistant/frontend/src/lib/sanitizeAssistantOutput.ts`

#### PayGuard's Assistant
**File**: `/client/src/lib/sanitizeAssistantOutput.ts`

Both implement:
```typescript
export function sanitizeAssistantOutput(text: string): string {
  // Remove markdown code blocks (``` ... ```)
  let cleaned = text.replace(/```[\s\S]*?```/g, '')

  // Remove @@FOLLOWUPS@@ markup and its JSON array
  cleaned = cleaned.replace(/@@FOLLOWUPS@@\s*\[[\s\S]*?\]/g, '')

  // Clean up excessive whitespace
  cleaned = cleaned.replace(/\n\n\n+/g, '\n\n')

  return cleaned.trim()
}
```

**Applied in AssistantBubble components**:
```typescript
function AssistantBubble({ text }: { text: string }) {
  const cleanedText = sanitizeAssistantOutput(text)
  
  return (
    <div className="...">
      <ReactMarkdown ...>{cleanedText}</ReactMarkdown>
    </div>
  )
}
```

---

## Files Updated

### Backend (Already had sanitization, verified)
- ✅ `/server/app/services/assistant/agent.py`
  - `_strip_code_fence()` — removes code fences
  - `_split_followups()` — removes @@FOLLOWUPS@@ markers
  - Applied at lines 338-339

### Frontend (New sanitization added)
- ✅ `/assistant/frontend/src/lib/sanitizeAssistantOutput.ts` — Created
- ✅ `/assistant/frontend/src/components/AssistantChat.tsx` — Updated
  - Added import
  - Applied to AssistantBubble component

- ✅ `/client/src/lib/sanitizeAssistantOutput.ts` — Created
- ✅ `/client/src/components/assistant/AssistantPanel.tsx` — Updated
  - Added import
  - Applied to AssistantBubble component

---

## How It Works

### User sees:
```
How many high-priority cases are open?

Based on the current metrics, there are 12 high-priority cases...
```

### Without sanitization (before):
```
How many high-priority cases are open?

```html
Based on the current metrics, there are 12 high-priority cases...
```
@@FOLLOWUPS@@ ["Show worklist", "What's next?"]
```

### After sanitization (now):
✅ Code fences removed
✅ @@FOLLOWUPS@@ removed  
✅ Only clean prose visible to user

---

## Robustness

**Defense-in-depth approach**:
1. **Backend removes markup** (primary) — most reliable, happens before network
2. **Frontend removes markup** (safety net) — catches any edge cases

If backend removal fails or code changes, frontend will still prevent markup display.

---

## Testing

To verify it works:

1. **Open OPA Assistant** (`localhost:5179`)
2. **Ask a question** — e.g., "How many cases are in the worklist?"
3. **Verify response** shows only clean prose, no:
   - ✅ No ``` code blocks
   - ✅ No @@FOLLOWUPS@@ markers
   - ✅ No JSON arrays

---

## Future Improvements

- [ ] Add logging to track if frontend sanitization is ever needed (indicates backend issue)
- [ ] Add metrics to monitor markup escape rate
- [ ] Consider adding HTML/script sanitization layer if needed

For now, both layers work together to ensure clean assistant output.
