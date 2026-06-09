"""Seed initial rule prompts for LLM-assisted detectors.

Each row is version 1 of a rule prompt, activated by default.
Only one version per rule_id may be active — subsequent edits via the
admin API create a new row (incrementing version) and deactivate the old one.
"""
import json
import sqlite3
from datetime import datetime
from uuid import uuid4

_NOW = datetime.utcnow().isoformat()

RULE_PROMPTS = [
    {
        "rule_id": "DET-09",
        "version": 1,
        "model": "claude-sonnet-4-6",
        "temperature": 0.0,
        "notes": "v8: UB-04 inpatient CPT-on-DRG scope; REMOVE/CORRECT/RETAIN dispositions; NEC code guidance; completeness instruction.",
        "output_schema": json.dumps({
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "One sentence stating what was found"},
                "policy_basis": {"type": "string", "description": "2-3 sentences citing specific CMS policy (IOM Pub 100-04, CMS-1450 FL instructions)"},
                "code_dispositions": {
                    "type": "array",
                    "description": "One entry per flagged code — every code must be represented",
                    "items": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "revenue_code": {"type": "string"},
                            "disposition": {"type": "string", "enum": ["REMOVE", "CORRECT", "RETAIN"]},
                            "reason": {"type": "string", "description": "Specific reason citing CMS policy or billing rule"},
                            "corrective_action": {"type": "string", "description": "Exactly what the biller must do"},
                            "correct_code": {"type": ["string", "null"], "description": "Replacement code if disposition is CORRECT, otherwise null"},
                        },
                        "required": ["code", "revenue_code", "disposition", "reason", "corrective_action", "correct_code"],
                    },
                },
                "corrective_action_summary": {"type": "string", "description": "Overall what the biller must do to correct the claim before resubmission — specific enough that no further research is needed"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1, "description": "Proportion of dispositions backed by a specific CMS citation; lower when revenue code context is ambiguous"},
            },
            "required": ["summary", "policy_basis", "code_dispositions", "corrective_action_summary", "confidence"],
        }),
        "prompt_template": """\
SCOPE: This prompt evaluates CPT_ON_INPATIENT_UB04 findings only — CPT/HCPCS codes appearing on UB-04 inpatient DRG claims.

You are a certified medical billing auditor specialising in institutional claim review (UB-04 / CMS-1450).
You have deep knowledge of CMS inpatient billing rules, DRG payment methodology, revenue code requirements,
and HCPCS/CPT applicability on institutional claims.

Analyse each flagged code and produce a precise, code-specific disposition.
Do not generalise. Be precise and citation-specific. Always respond in valid JSON matching the output schema.
Every code in the Flagged codes section below must appear in code_dispositions. If you are uncertain
about a code, use RETAIN and note the uncertainty in the reason field.

## Claim context
- Claim form type: {{claim_form_type}}
- Care setting: {{care_setting}}
- DRG: {{drg}}
- Date of service: {{dos}}

## Flagged codes (from rule engine)
{{flagged_codes_json}}

Each entry includes: code, code_type, revenue_code, revenue_description, units, charge.

## Rule DET-09 definition
Fires when CPT or HCPCS codes appear in FL 44 on a UB-04 inpatient claim under DRG-based payment.
Under DRG methodology the facility receives a single bundled rate — most line-level procedure codes
are informational only or incorrect. However, certain revenue code categories REQUIRE a HCPCS code
per CMS billing instructions even on inpatient claims (implants on 027x lines, new technology
pass-through items, and specific CMS-mandated reporting lines).

## Decision logic — apply to each flagged code

**REMOVE** — code should not appear in FL 44 at all. Revenue code alone is sufficient.
Inpatient DRG bundles this service.
Examples: surgical CPTs on 036x, anesthesia CPTs on 037x, radiology CPTs on 032x,
          lab CPTs on 030x, therapy CPTs on 042x.

**CORRECT** — a HCPCS code IS required on this revenue line, but the wrong code was used.
Provide the correct replacement code. The replacement must be the manufacturer-specific or
CMS NTAP-listed HCPCS — do not default to a miscellaneous NEC code (e.g. L8699, A9999)
unless no specific code exists and you explicitly state why.
Examples: 027x implant lines require the device-specific prosthesis HCPCS from the
          manufacturer's billing guide or the CMS NTAP/pass-through device list.

**RETAIN** — code is correctly present. CMS requires HCPCS on this revenue line even for inpatient DRG claims.
Examples: 027x lines with correct implant HCPCS, new technology add-on payment (NTAP) items,
          specific pass-through device codes.

Set confidence to the proportion of dispositions you can support with a specific CMS citation;
reduce it where revenue code context is ambiguous or the applicable HCPCS catalogue is device-specific.

Respond ONLY with valid JSON matching the output schema. No prose outside the JSON.""",
    },
    {
        "rule_id": "DET-18",
        "version": 1,
        "model": "claude-opus-4-8",
        "temperature": 0.0,
        "notes": "Two-assessment evaluation: A) medical necessity, B) ICD coding adequate for coverage. v6 design.",
        "output_schema": json.dumps({
            "type": "object",
            "properties": {
                "medical_necessity_met": {"type": "boolean"},
                "coding_issue": {"type": "boolean"},
                "coding_issue_description": {
                    "type": "string",
                    "description": "If coding_issue=true: ICD-10 code(s) that should have been documented; empty string if coding_issue=false"
                },
                "rationale": {
                    "type": "string",
                    "description": "Reasoning for both Assessment A (necessity) and Assessment B (coding)"
                },
                "covered_indications_cited": {
                    "type": "string",
                    "description": "Recognized covered indications for this CPT under CMS policy or clinical guidelines"
                },
                "coverage_standard": {"type": "string", "enum": ["lcd", "ncd", "clinical_guideline", "unknown"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1}
            },
            "required": ["medical_necessity_met", "coding_issue", "coding_issue_description",
                         "rationale", "covered_indications_cited", "coverage_standard", "confidence"]
        }),
        "prompt_template": """\
You are a payer-side coverage analyst. Our internal LCD/NCD catalogue has no
coverage rules for {{cpt_code}}. Make two independent assessments, both required.

## Claim
- CPT procedure: {{cpt_code}}
- Primary diagnosis (ICD-10): {{primary_icd}}
- Supporting diagnoses: {{other_icd_codes}}
- Place of service: {{pos_code}}
- Provider specialty: {{provider_specialty}}

## Assessment A — Medical necessity
Determine whether this procedure is clinically warranted for the documented
patient conditions, based on established clinical standards.

1. What are the recognized clinical indications for {{cpt_code}} per established
   guidelines? List the conditions for which this procedure is typically indicated.
2. Are any of these indications present in the documented diagnoses — primary,
   supporting, or comorbid?
3. Are there required prerequisites that guidelines stipulate before this procedure
   is indicated (e.g. failed conservative treatment, severity threshold, prior
   diagnostic workup) and are they absent from the claim?

Return medical_necessity_met: true if at least one recognized clinical indication
is present in the documented conditions; false if no indication is documented.

## Assessment B — Coding adequacy
Determine whether the documented ICD-10 codes satisfy the coverage requirement
for {{cpt_code}} under CMS policy (NCDs, widely adopted LCDs, or major
specialty-society clinical guidelines).

1. What are the recognized covered indications for {{cpt_code}} under CMS policy?
   List them concisely in covered_indications_cited.
2. Do any documented ICD-10 codes — primary or supporting — directly match a
   covered indication? Parent codes, manifestation codes, sequela codes, and closely
   related conditions within the same 3-character code block (e.g. M17.x) all count as a match.
3. If no match: what specific ICD-10 code should have been documented to satisfy
   the coverage requirement? Describe it in coding_issue_description for analyst
   use during records review — this is a pointer, not a directive to alter the claim.
   Set coding_issue_description to empty string if coding_issue is false.

Return coding_issue: true if the ICD-10 coding is deficient for coverage (a
required code is absent or incorrect); false if the coding adequately supports
coverage.

Unknown CPT: If you cannot identify coverage rules for {{cpt_code}}, return
medical_necessity_met: true (cannot determine — assume warranted), coding_issue:
true, coverage_standard: "unknown", confidence <= 0.35, and explain in rationale.
Do not assert the procedure is not warranted when you do not know the CPT.

Confidence calibration — use the lower of your two assessment confidences:
- 0.75-0.90: clear established clinical indication (A) AND a citable NCD/LCD (B).
- 0.50-0.74: clinical guidelines support (A) or broadly accepted practice without
  a citable CMS policy (B).
- 0.30-0.49: borderline clinical evidence (A), MAC-specific or ambiguous coverage
  (B), or the CPT is not clearly in your training knowledge.

rationale must address both assessments — explain your reasoning for A and B.

For coverage_standard: "ncd" or "lcd" only when you can cite a policy by name;
"clinical_guideline" for specialty-society standards; "unknown" otherwise.

Respond ONLY with valid JSON matching the output schema.""",
    },
    {
        "rule_id": "FWA-02",
        "version": 1,
        "model": "claude-sonnet-4-6",
        "temperature": 0.0,
        "notes": "Initial prompt — credential misrepresentation detection.",
        "output_schema": json.dumps({
            "type": "object",
            "properties": {
                "misrepresentation_detected": {"type": "boolean"},
                "issue": {"type": "string"},
                "rationale": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1}
            },
            "required": ["misrepresentation_detected", "rationale", "confidence"]
        }),
        "prompt_template": """\
You are a healthcare fraud examiner reviewing provider credential integrity.

## Provider
- Name: {{provider_name}}
- NPI: {{provider_npi}}
- Claimed specialty: {{provider_specialty}}
- Taxonomy code: {{taxonomy_code}}

## Claim
- CPT codes billed: {{cpt_codes}}
- Place of service: {{pos_code}}
- Primary diagnosis: {{primary_icd}}

## Task
Determine whether there is a credential misrepresentation concern:
1. Are the billed CPT codes consistent with the provider's stated specialty?
2. Does the taxonomy code match the specialty?
3. Are any billed procedures outside the typical scope for this specialty?

Respond ONLY with valid JSON matching the output schema.""",
    },
    {
        "rule_id": "FWA-03",
        "version": 1,
        "model": "claude-sonnet-4-6",
        "temperature": 0.0,
        "notes": "Initial prompt — place-of-service mismatch enrichment.",
        "output_schema": json.dumps({
            "type": "object",
            "properties": {
                "mismatch_detected": {"type": "boolean"},
                "expected_pos": {"type": "string"},
                "billed_pos": {"type": "string"},
                "rationale": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1}
            },
            "required": ["mismatch_detected", "rationale", "confidence"]
        }),
        "prompt_template": """\
You are a claims auditor checking place-of-service (POS) code accuracy.

## Claim
- Billed POS code: {{pos_code}} ({{pos_description}})
- CPT codes: {{cpt_codes}}
- Provider specialty: {{provider_specialty}}
- Primary diagnosis: {{primary_icd}}
- Care setting: {{care_setting}}

## Task
Determine whether the billed place-of-service code is consistent with:
1. The procedures billed (some CPTs are only payable in specific settings)
2. The provider's specialty
3. The documented diagnoses and care setting

Respond ONLY with valid JSON matching the output schema.""",
    },
]

# ── Verification prompts ──────────────────────────────────────────────────────
# One per LLM-evaluated rule. Receives the original claim + the primary LLM
# finding and acts as an adversarial second opinion — tries to refute the
# finding before it escalates to a human analyst.

VERIFICATION_PROMPTS = [
    {
        "rule_id": "DET-09",
        "version": 1,
        "prompt_type": "verification",
        "model": "claude-sonnet-4-6",
        "temperature": 0.0,
        "notes": "v7: adversarial review of REMOVE/CORRECT/RETAIN dispositions; corrected_disposition enum constrained; ESCALATE_TO_HUMAN criteria; unverifiable replacement code detection.",
        "output_schema": json.dumps({
            "type": "object",
            "properties": {
                "verification_result": {"type": "string", "enum": ["PASS", "FAIL", "PASS_WITH_WARNINGS"]},
                "overall_confidence": {"type": "number", "minimum": 0, "maximum": 1,
                    "description": "Confidence in the verification outcome — how certain you are that dispositions are correct"},
                "disposition_reviews": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "evaluation_disposition": {"type": "string", "enum": ["REMOVE", "CORRECT", "RETAIN"]},
                            "verified": {"type": "boolean"},
                            "issue": {"type": ["string", "null"]},
                            "corrected_disposition": {"type": ["string", "null"], "enum": ["REMOVE", "CORRECT", "RETAIN", None]},
                            "corrected_action": {"type": ["string", "null"],
                                "description": "If disposition or replacement code is wrong, state the correct action including the correct code"},
                        },
                        "required": ["code", "evaluation_disposition", "verified", "issue", "corrected_disposition", "corrected_action"],
                    },
                },
                "citation_issues": {"type": "array", "items": {"type": "string"},
                    "description": "Hallucinated policy citations AND unverifiable replacement codes prefixed with UNVERIFIED CODE:"},
                "warnings": {"type": "array", "items": {"type": "string"}},
                "recommended_action": {"type": "string",
                    "enum": ["RELEASE_TO_ANALYST", "RETURN_TO_EVALUATION", "ESCALATE_TO_HUMAN"]},
            },
            "required": ["verification_result", "overall_confidence", "disposition_reviews", "citation_issues", "warnings", "recommended_action"],
        }),
        "prompt_template": """\
You are a senior medical billing compliance officer reviewing an AI-generated audit finding
before it is presented to a human analyst. Your role is adversarial — assume the evaluation
may contain errors and look for them specifically.

## Claim context

Expected shape of claim_context_json:
{
  "claim_form_type": "UB-04",
  "care_setting": "Inpatient",
  "drg": "470",
  "dos": "2024-03-15",
  "flagged_codes": [
    {"code": "27447", "code_type": "CPT", "revenue_code": "0360",
     "revenue_description": "Operating Room Services", "units": 1, "charge": 12500.00}
  ]
}

Actual claim context:
{{claim_context_json}}

## Evaluation output under review
{{evaluation_output_json}}

## Verification checklist — apply each test

1. Does any REMOVE disposition incorrectly remove a code from a revenue line that CMS
   requires HCPCS on (027x implant lines, pass-through device lines)?

2. Does any RETAIN or CORRECT disposition incorrectly keep a code that should be removed
   (surgical CPTs, anesthesia CPTs, diagnostic CPTs bundled into DRG)?

3. For any CORRECT disposition — verify the replacement code is a currently active HCPCS/CPT
   code as of the date of service in the claim context. If the code is wrong, state the
   correct replacement code and its applicable revenue code category. If you cannot confirm
   the code exists, output "UNVERIFIED CODE: <code>" in citation_issues.

4. Are policy citations real? CMS IOM Pub 100-04 Chapter 3 covers inpatient billing.
   CMS-1450 instructions cover FL 44. Flag any citation that does not match these sources.

5. Does the corrective_action_summary give the biller enough information to correct the
   claim without further research?

Every disposition in the evaluation's code_dispositions array must have a corresponding entry in disposition_reviews.

Use ESCALATE_TO_HUMAN only when the claim involves a new technology or pass-through item
where neither you nor the evaluation can determine the correct HCPCS without a device-specific
lookup. Use RETURN_TO_EVALUATION when a disposition is wrong but correctable by re-running
the evaluation with more context. Use RELEASE_TO_ANALYST when the evaluation is correct or
only has minor warnings.

Respond ONLY with valid JSON matching the output schema. No prose outside the JSON.""",
    },
    {
        "rule_id": "DET-18",
        "version": 1,
        "prompt_type": "verification",
        "model": "claude-opus-4-8",
        "temperature": 0.0,
        "notes": "Second-opinion verifier: independently confirms necessity failure and/or coding deficiency.",
        "output_schema": json.dumps({
            "type": "object",
            "properties": {
                "medical_necessity_confirmed": {"type": "boolean"},
                "coding_issue_confirmed": {"type": "boolean"},
                "false_positive_reason": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "recommended_action": {"type": "string",
                    "enum": ["escalate", "dismiss", "request_medical_records"]}
            },
            "required": ["medical_necessity_confirmed", "coding_issue_confirmed",
                         "confidence", "recommended_action"]
        }),
        "prompt_template": """\
You are a second-level utilization review analyst (QIC-equivalent). A medical
necessity evaluation flagged the claim below on one or both grounds:
- Medical necessity not met: the procedure is not clinically warranted
- Coding deficiency: the ICD-10 codes don't satisfy the coverage requirement

Your job: independently verify each flagged issue before it reaches an analyst.
Default toward dismissal — only confirm when evidence is clear.

## Claim
- CPT procedure: {{cpt_code}}
- Primary DX: {{primary_icd}}
- Supporting diagnoses: {{other_icd_codes}}
- Place of service: {{pos_code}}
- Line of business: {{lob}}

## Initial evaluation
- Medical necessity flagged as NOT met: {{medical_necessity_met}}
  (true = evaluator said OK; false = evaluator flagged a problem)
- Coding deficiency flagged: {{coding_issue}}
- Coding gap identified: {{coding_issue_description}}
- Recognized covered indications for {{cpt_code}}: {{covered_indications_cited}}
- Coverage standard cited: {{coverage_standard}}
- Evaluation rationale: {{finding_description}}
- Initial confidence: {{initial_confidence}}

## Verification A — Medical necessity (if medical_necessity_met = false)
1. Is there a clinically recognised indication in the documented diagnoses that
   the evaluator may have missed — including secondary conditions or comorbidities?
2. Would a provider presenting clinical records have a reasonable chance of
   demonstrating necessity at appeal?

Set medical_necessity_confirmed: true only if you agree the procedure is NOT
clinically warranted; false if a valid indication exists.

## Verification B — Coding adequacy (if coding_issue = true)
1. Do any documented ICD-10 codes actually satisfy a covered indication when
   interpreted broadly — parent code, manifestation, closely related condition?
2. Is the identified coding gap genuine, or could existing codes satisfy coverage?

Set coding_issue_confirmed: true only if you agree the coding is genuinely
deficient; false if existing codes could satisfy coverage.

## Action selection
- "escalate": medical necessity confirmed NOT met — denial candidate
- "request_medical_records": coding deficiency confirmed but medical necessity
  may be supportable — records could provide the missing ICD documentation
- "dismiss": at least one flagged issue is not confirmed (false positive)

Override: dismiss if initial confidence < 0.60 AND coverage_standard is
"unknown", unless both assessments are unambiguous.

Populate false_positive_reason only when recommending dismiss.

Respond ONLY with valid JSON matching the output schema.""",
    },
    {
        "rule_id": "FWA-02",
        "version": 1,
        "prompt_type": "verification",
        "model": "claude-sonnet-4-6",
        "temperature": 0.0,
        "notes": "Adversarial second opinion for FWA-02 credential misrepresentation findings.",
        "output_schema": json.dumps({
            "type": "object",
            "properties": {
                "confirmed": {"type": "boolean"},
                "legitimate_explanation": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "recommended_action": {"type": "string",
                    "enum": ["escalate_to_siu", "escalate_to_analyst", "dismiss", "request_credentials"]}
            },
            "required": ["confirmed", "confidence", "recommended_action"]
        }),
        "prompt_template": """\
You are a Special Investigations Unit (SIU) supervisor reviewing a credential
misrepresentation flag before opening a formal investigation. False investigations
are costly and damage provider relationships. Only confirm if the concern is material.

## Provider
- Name: {{provider_name}} | NPI: {{provider_npi}}
- Claimed specialty: {{provider_specialty}}
- Taxonomy code: {{taxonomy_code}}

## Claim
- CPT codes billed: {{cpt_codes}}
- Primary DX: {{primary_icd}}
- POS: {{pos_code}}
- Flagged mismatches: {{mismatched_codes}}

## Finding under review
- {{finding_description}}
- Initial confidence: {{initial_confidence}}

## Your review task
1. Are the flagged CPT codes within a reasonable scope extension for this specialty?
   (e.g. family medicine performing minor office procedures, internist ordering cardiac monitoring)
2. Could this be a legitimate incident-to, split/shared, or teaching physician billing scenario?
3. Could the provider have dual board certification or fellowship training not captured
   in the taxonomy code?
4. Is the volume/pattern consistent with occasional scope extension vs. systematic misrepresentation?

Respond ONLY with valid JSON.
`confirmed: true` = misrepresentation concern is material; recommend SIU or analyst escalation.
`confirmed: false` = a legitimate explanation exists; dismiss.""",
    },
    {
        "rule_id": "FWA-03",
        "version": 1,
        "prompt_type": "verification",
        "model": "claude-sonnet-4-6",
        "temperature": 0.0,
        "notes": "Adversarial second opinion for FWA-03 place-of-service mismatch findings.",
        "output_schema": json.dumps({
            "type": "object",
            "properties": {
                "confirmed": {"type": "boolean"},
                "legitimate_pos_explanation": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "recommended_action": {"type": "string",
                    "enum": ["escalate", "dismiss", "verify_with_facility"]}
            },
            "required": ["confirmed", "confidence", "recommended_action"]
        }),
        "prompt_template": """\
You are a claims payment integrity auditor reviewing a place-of-service (POS) mismatch
flag before a demand letter is issued. POS errors are common and often innocent.
Only confirm findings that represent a genuine payment integrity risk.

## Claim
- Billed POS: {{pos_code}} ({{pos_description}})
- CPT codes: {{cpt_codes}}
- Provider specialty: {{provider_specialty}}
- Primary DX: {{primary_icd}}
- Care setting on record: {{care_setting}}
- Flagged mismatches: {{pos_mismatches}}

## Finding under review
- {{finding_description}}
- Initial confidence: {{initial_confidence}}

## Your review task
1. Is there a valid scenario where these CPT codes could be performed at POS {{pos_code}}?
   Consider: mobile services, telehealth waivers, rural/critical access hospitals,
   federally qualified health centres, or post-PHE flexibilities.
2. Could the POS code represent a facility type that legitimately performs these procedures
   even if it's outside the typical setting?
3. Is the payment differential between the billed POS and the expected POS material
   (i.e. would the payer have paid differently)?
4. Is this a data entry error or a systematic pattern?

Respond ONLY with valid JSON.
`confirmed: true` = POS mismatch is material and likely intentional; escalate.
`confirmed: false` = plausible legitimate explanation; dismiss.""",
    },
]


def seed(db_path: str = "opa.db") -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    inserted = 0
    all_prompts = [
        {**p, "prompt_type": p.get("prompt_type", "evaluation")}
        for p in RULE_PROMPTS + VERIFICATION_PROMPTS
    ]
    for p in all_prompts:
        row_id = str(uuid4())
        # Unique constraint: (rule_id, version, prompt_type)
        # Use INSERT OR IGNORE so re-runs are idempotent.
        cur.execute(
            """INSERT OR IGNORE INTO rule_prompts
               (id, rule_id, version, prompt_template, output_schema, prompt_type,
                active, model, temperature, last_edited_by, last_edited_at, notes, eval_score)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, 'seed', ?, ?, NULL)""",
            (
                row_id,
                p["rule_id"],
                p["version"],
                p["prompt_template"],
                p.get("output_schema"),
                p["prompt_type"],
                p["model"],
                p["temperature"],
                _NOW,
                p.get("notes"),
            ),
        )
        if cur.rowcount:
            inserted += 1

    conn.commit()
    conn.close()
    print(f"[seed_rule_prompts] inserted {inserted} prompt(s)")


if __name__ == "__main__":
    import os
    db = os.getenv("DB_PATH", "opa.db")
    seed(db)
