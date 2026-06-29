# PayGuard ↔ ClaimGuard Detector Compatibility Verification

## Status: ✅ VERIFIED - All Detectors Support Both Pipelines

---

## How It Works

### PayGuard (Post-Pay) Flow
```
Claim → Case (case_id set) → Documents attached to case
```

### ClaimGuard (Pre-Pay) Flow
```
Claim (claim_id set, case_id may be NULL) → Documents attached to claim
```

---

## Code Pattern Used (All Detectors)

Every detector uses this dual-path logic:

```python
# Check both case_id and claim_id
if not claim.case_id and not claim.claim_id:
    return set()  # No attachments possible

# Query documents linked to EITHER the case OR the claim
from sqlalchemy import or_
result = await db_session.execute(
    select(Document).where(
        or_(
            Document.case_id == claim.case_id if claim.case_id else False,
            Document.claim_id == claim.claim_id if claim.claim_id else False,
        )
    )
)
documents = result.scalars().all()
```

This pattern is used in:
- ✅ DET-18 `_extract_diagnoses_from_case_documents()` — lines 208-211
- ✅ DET-04 `_check_for_auth_approval()` — lines 110-113  
- ✅ DET-06 `_check_for_medical_justification()` — lines 131-134
- ✅ DET-09 `_check_for_unbundling_justification()` — lines 328-331

---

## Per-Detector Verification

### DET-18 (Medical Necessity)
**PayGuard:** ✅ Queries documents on case  
**ClaimGuard:** ✅ Queries documents on claim (pre-case)  
**ClearLink:** ✅ Member-based, works for both  

**Query handles:**
- Claims with case_id (post-pay)
- Claims without case_id (pre-pay, pre-case)

---

### DET-04 (Fee Schedule Variance)
**PayGuard:** ✅ Finds prior auth in case documents  
**ClaimGuard:** ✅ Finds prior auth in claim documents  
**ClearLink:** ✅ Member authorization lookup, works for both

**Query handles:**
- Claims with case_id (post-pay)
- Claims without case_id (pre-pay, pre-case)

---

### DET-06 (NCCI/MUE Violation)
**PayGuard:** ✅ Finds medical justification in case documents  
**ClaimGuard:** ✅ Finds medical justification in claim documents  
**ClearLink:** ✅ Clinical notes lookup, works for both

**Query handles:**
- Claims with case_id (post-pay)
- Claims without case_id (pre-pay, pre-case)

---

### DET-09 (Coding Errors - Unbundling)
**PayGuard:** ✅ Finds unbundling justification in case documents  
**ClaimGuard:** ✅ Finds unbundling justification in claim documents  
**ClearLink:** ✅ Clinical notes lookup, works for both

**Query handles:**
- Claims with case_id (post-pay)
- Claims without case_id (pre-pay, pre-case)

---

## Document Attachment Scenarios

### Scenario 1: PayGuard (Post-Pay with Case)
```
PayGuard Claim → Case Created → Documents attached to case_id
                                ↓
                         Detectors query case documents ✅
                         Detectors also query ClearLink ✅
```

### Scenario 2: ClaimGuard (Pre-Pay, Pre-Case)
```
ClaimGuard Claim → NO CASE YET → Documents attached to claim_id
                                  ↓
                           Detectors query claim documents ✅
                           Detectors also query ClearLink ✅
```

### Scenario 3: ClaimGuard (Pre-Pay, Post-Case)
```
ClaimGuard Claim → Case Created → Documents on both claim_id and case_id
                                   ↓
                        Detectors query both sources ✅
                        Detectors also query ClearLink ✅
```

---

## ClearLink Integration (Member-Based)

**Independent of pipeline mode:**
- ✅ DET-18 searches by `claim.member_id`
- ✅ DET-04 searches by `claim.member_id`
- ✅ DET-06 searches by `claim.member_id`
- ✅ DET-09 searches by `claim.member_id`

Member ID is available in both PayGuard and ClaimGuard claims, so ClearLink queries work identically.

---

## Backward Compatibility

If ClearLink is not configured (`CLEARLINK_MCP_API_KEY` not set):
- ✅ All detectors silently fall back to document-only checks
- ✅ No errors raised
- ✅ No change in behavior

---

## Summary

| Component | PayGuard | ClaimGuard |
|-----------|----------|-----------|
| **Attached Documents** | ✅ Case-based | ✅ Claim-based |
| **ClearLink Fallback** | ✅ Member-based | ✅ Member-based |
| **DET-18** | ✅ Works | ✅ Works |
| **DET-04** | ✅ Works | ✅ Works |
| **DET-06** | ✅ Works | ✅ Works |
| **DET-09** | ✅ Works | ✅ Works |
| **Graceful Degradation** | ✅ Yes | ✅ Yes |

---

## Conclusion

**All four detectors are production-ready for both PayGuard (post-pay) and ClaimGuard (pre-pay) pipelines.**

The dual-path query pattern (`or_(case_id, claim_id)`) ensures:
1. Documents attached at any stage are found
2. Pre-case ClaimGuard claims are not blocked
3. Post-case ClaimGuard claims can find documents on both paths
4. PayGuard cases continue to work as before
5. ClearLink provides fallback data when documents are unavailable

✨ **No additional changes needed.** ✨
