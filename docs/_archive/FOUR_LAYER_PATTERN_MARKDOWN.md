# Four-Layer Evidence Verification Pattern

## A Multi-Source Approach to Reduce False Positives

---

## The Flow

```
Layer 1: Claim-Coded Data
         ↓
Layer 2: Attached Case Documents (Local Evidence)
         ↓
Layer 3: ClearLink Member Records (External EHR Data)
         ↓
Layer 4: Confidence Reduction (Actionable Findings)
```

---

## Layer Details

### Layer 1: Claim-Coded Data (Baseline)
- CPT codes from claim submission
- Diagnosis codes on claim
- Service dates & amounts

### Layer 2: Attached Case Documents (Local Evidence)
- Surgical notes → Diagnosis extraction
- Prior authorizations → CPT code matching
- Clinical documentation → Medical justification
- Extracted text from PDFs

### Layer 3: ClearLink Member Records (External Data)
- Member medical records → Diagnoses
- Member authorizations → Prior auth lookup
- Clinical notes → Medical justification
- Live EHR data (when documents unavailable)

### Layer 4: Confidence Reduction (Final Result)
- Evidence found at any layer → Reduce false positives
- DET-18: Find diagnosis → No medical necessity finding
- DET-04: Find prior auth → Lower confidence 0.85→0.45
- DET-06: Find justification → Lower confidence 0.88→0.45
- DET-09: Find unbundling justification → Lower confidence

---

## Key Benefits

✓ **Comprehensive validation** across multiple data sources  
✓ **Fallback logic** when evidence is missing locally  
✓ **Graceful degradation** if ClearLink unavailable  
✓ **Works for both** PayGuard (post-pay) & ClaimGuard (pre-pay)  
✓ **Full audit trail** for healthcare compliance  

---

## Detectors Enabled

| Detector | Purpose |
|----------|---------|
| DET-18 | Medical Necessity → Diagnosis validation |
| DET-04 | Fee Schedule → Prior authorization lookup |
| DET-06 | NCCI/MUE → Procedure justification |
| DET-09 | Coding Errors → Unbundling justification |

---

## Design Highlights

- **Intelligent Fallback**: Document-first, then ClearLink
- **Code Verification**: Only reduces confidence if codes match
- **Pipeline Agnostic**: Works for both PayGuard and ClaimGuard
- **Production-Ready**: Error handling and logging at every layer
