"""Seed letter templates — synchronous sqlite3.

3 templates: MA, PPO, Medicaid.
Each body is 400-600 words with all 15 required placeholders.
Placeholders: {{case_number}}, {{provider_name}}, {{provider_npi}},
{{member_name}}, {{member_id}}, {{service_date}}, {{cpt_codes}},
{{overpayment_amount}}, {{recovery_method}}, {{response_due_date}},
{{regulatory_reference}}, {{plan_name}}, {{lob}}, {{analyst_name}},
{{analyst_phone}}
"""
from __future__ import annotations

import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2024-01-01T08:00:00"

TEMPLATES = [
    {
        "template_id":        "TMPL-MA-001",
        "lob":                "MA",
        "template_name":      "Medicare Advantage Overpayment Recovery Notice",
        "regulatory_reference": (
            "42 CFR §422.326; CMS Medicare Managed Care Manual Chapter 4 §110.6; "
            "42 CFR §422.500 (provider contract requirements)"
        ),
        "version":            "2.1",
        "content": """\
[PLAN LETTERHEAD]

Date: {{service_date}}
Case Reference: {{case_number}}

{{provider_name}}
NPI: {{provider_npi}}

RE: Medicare Advantage Overpayment Recovery Notice — {{plan_name}}

Dear {{provider_name}},

This notice is issued on behalf of {{plan_name}} (hereinafter "the Plan") pursuant to our obligations under 42 CFR §422.326 and the Medicare Managed Care Manual, Chapter 4, Section 110.6. Following a systematic post-payment review of claims submitted for Medicare Advantage (MA) beneficiaries, our Overpayment Detection Unit has identified a potential overpayment associated with claims billed on behalf of member {{member_name}} (Member ID: {{member_id}}).

SUMMARY OF FINDINGS

Our clinical review and automated pattern analysis identified services billed under procedure code(s) {{cpt_codes}} for dates of service {{service_date}} that do not appear to meet the criteria for medical necessity, correct coding, or contractual reimbursement as required under your participating provider agreement and applicable CMS guidelines. The total overpayment amount identified is {{overpayment_amount}}.

The specific issues identified in our review include, but may not be limited to, the following: (1) the documentation submitted does not support the level of service billed; (2) the procedure code(s) were billed in combination with diagnosis code(s) that do not reflect a clinically supported indication; or (3) the services billed exceeded the frequency limitations established under the Plan's benefit design for the applicable line of business ({{lob}}).

YOUR RIGHTS AND OBLIGATIONS

As a participating provider in {{plan_name}}'s Medicare Advantage network, you are required under 42 CFR §422.500 and your provider service agreement to return identified overpayments promptly upon notification. Failure to return confirmed overpayments within the required timeframe may result in offset against future claim payments, referral to the Centers for Medicare & Medicaid Services (CMS) Program Integrity unit, or other remedies available under the provider agreement and applicable law.

You have the right to submit a written dispute or provide additional supporting documentation for our review. To exercise this right, your written response must be received no later than {{response_due_date}}. Responses should include the case reference number ({{case_number}}), a copy of the relevant medical records, and a written explanation addressing each item identified in this notice.

RECOVERY METHOD

The Plan intends to recover this overpayment via {{recovery_method}}. If you have questions regarding the recovery timeline or wish to arrange an alternative repayment schedule, please contact our Provider Overpayment Recovery Team directly.

REGULATORY REFERENCE

This notice is issued in compliance with {{regulatory_reference}}. The Plan is required by CMS to report and recover identified Medicare Advantage overpayments. Your cooperation is essential to maintaining compliance with federal program integrity requirements.

If you have questions about this notice, please contact your assigned OPA analyst, {{analyst_name}}, at {{analyst_phone}}. When calling, please reference case number {{case_number}} to ensure prompt assistance.

Sincerely,

{{analyst_name}}
Payment Integrity Analyst
{{plan_name}} — Overpayment Detection Unit
Phone: {{analyst_phone}}

This communication contains information that is confidential and intended solely for the named recipient. If you have received this in error, please notify the sender immediately.
""",
    },
    {
        "template_id":        "TMPL-PPO-001",
        "lob":                "PPO",
        "template_name":      "Commercial PPO Overpayment Recovery Notice",
        "regulatory_reference": (
            "29 CFR §2560.503-1; ERISA §502(a); Plan's provider agreement Section 8.3 "
            "(Overpayment Recovery); state prompt-pay statutes as applicable"
        ),
        "version":            "1.4",
        "content": """\
[PLAN LETTERHEAD]

Date: {{service_date}}
Case Reference: {{case_number}}

{{provider_name}}
NPI: {{provider_npi}}

RE: Commercial PPO Overpayment Recovery Notice — {{plan_name}}

Dear {{provider_name}},

{{plan_name}} (hereinafter "the Plan") administers health benefits for a self-funded employer group subject to the Employee Retirement Income Security Act of 1974 (ERISA), as amended. In the course of our ongoing post-payment audit program, our Payment Integrity team has identified a potential overpayment on claims billed for covered member {{member_name}} (Member ID: {{member_id}}).

NATURE OF THE IDENTIFIED OVERPAYMENT

A systematic review of claims with dates of service {{service_date}} revealed that procedure code(s) {{cpt_codes}} were reimbursed at amounts that appear to exceed the applicable contracted rate or were paid without adequate documentation of medical necessity as required under the terms of your participating provider agreement and the Plan's benefit design for the {{lob}} line of business. The total amount subject to recovery is {{overpayment_amount}}.

Our review considered the following factors: adherence to the Plan's clinical coverage policies, correct application of the applicable fee schedule for your specialty and place of service, the presence of applicable modifiers and their appropriate usage, and whether the billed procedure codes accurately reflect the services rendered as documented in the medical record. If any of these elements were found to be inconsistent with Plan requirements, payment may be subject to full or partial recoupment.

DISPUTE AND APPEAL RIGHTS

The Plan's provider agreement and applicable state and federal regulations afford you the right to dispute this overpayment determination. If you believe this determination is incorrect, you must submit a written dispute no later than {{response_due_date}}. Your dispute must reference case number {{case_number}} and include all supporting clinical documentation, applicable medical records, and a written statement addressing the specific basis for your disagreement. Disputes submitted without adequate supporting documentation may not be considered for review.

Please be advised that per 29 CFR §2560.503-1 and the Plan's internal claims dispute procedures, a decision on your dispute will be rendered within 60 days of receipt of a complete submission.

RECOVERY PROCESS

The Plan will initiate recovery of the identified overpayment ({{overpayment_amount}}) through {{recovery_method}} unless a dispute is received and pending resolution by {{response_due_date}}. If you wish to discuss an alternative repayment arrangement, please contact our Provider Relations team at the number listed below before the recovery action is initiated.

CONTACT INFORMATION

For questions regarding this notice or the recovery process, please contact {{analyst_name}} at {{analyst_phone}}. Please reference case number {{case_number}} in all correspondence. The regulatory basis for this recovery action is set forth in {{regulatory_reference}}.

Sincerely,

{{analyst_name}}
Senior Payment Integrity Analyst — Commercial Programs
{{plan_name}}
Phone: {{analyst_phone}}

CONFIDENTIALITY NOTICE: This letter and any attachments may contain confidential, proprietary, or legally privileged information. Unauthorized disclosure, copying, distribution, or use of the contents of this document is strictly prohibited.
""",
    },
    {
        "template_id":        "TMPL-MEDICAID-001",
        "lob":                "Medicaid",
        "template_name":      "Medicaid Managed Care Overpayment Recovery Notice",
        "regulatory_reference": (
            "42 CFR §455.1–455.23; State Medicaid Program Integrity Manual §3.2; "
            "42 CFR §438.608 (managed care program integrity); state Medicaid provider agreement"
        ),
        "version":            "3.0",
        "content": """\
[PLAN LETTERHEAD]

Date: {{service_date}}
Case Reference: {{case_number}}

{{provider_name}}
NPI: {{provider_npi}}

RE: Medicaid Managed Care Overpayment Recovery Notice — {{plan_name}}

Dear {{provider_name}},

This letter is sent to you on behalf of {{plan_name}}, a licensed Medicaid Managed Care Organization (MCO) operating under contract with the State Medicaid Agency. Pursuant to 42 CFR §455.1 and our obligations under the State Medicaid Program Integrity framework, we are notifying you of a potential overpayment identified through our post-payment review process.

IDENTIFIED OVERPAYMENT

Our payment integrity review has identified a potential overpayment totaling {{overpayment_amount}} for claims submitted on behalf of Medicaid beneficiary {{member_name}} (Member ID: {{member_id}}) for services with dates of service {{service_date}}. The claim(s) at issue include procedure code(s) {{cpt_codes}} under the {{lob}} program.

The basis for this overpayment determination is as follows: our review identified that the services billed do not conform to applicable Medicaid coverage criteria, prior authorization requirements, or the medically necessary standard as defined in the State Medicaid Program and the MCO's clinical coverage policies. In addition, the procedure codes billed may not be consistent with the member's documented clinical condition or the supporting diagnosis codes submitted on the claim, as required under the State Medicaid Provider Participation Agreement and 42 CFR §455.18.

PROGRAM INTEGRITY OBLIGATIONS

As a Medicaid-participating provider, you are subject to the program integrity requirements set forth in 42 CFR §455.1 through §455.23 and the State Medicaid Provider Manual. These provisions require providers to return identified Medicaid overpayments within 60 days of identification or the date on which the corresponding cost report is due, whichever is later. Failure to return an identified overpayment within the required timeframe may result in referral to the State Medicaid Fraud Control Unit (MFCU), imposition of sanctions, or exclusion from the Medicaid program.

The Plan is also required under 42 CFR §438.608 to report this overpayment determination to the State Medicaid Agency. A copy of this notice may be provided to the State Agency as part of our mandatory program integrity reporting obligations.

YOUR RIGHT TO RESPOND

You have the right to submit a written response, dispute, or additional supporting documentation within {{response_due_date}} of receipt of this notice. Your response must reference case number {{case_number}} and include complete medical records, physician notes, and any prior authorization documentation relevant to the services identified. Incomplete responses may result in the determination being upheld without further review.

RECOVERY

The Plan will proceed with recovery of {{overpayment_amount}} via {{recovery_method}} as permitted under the provider agreement and applicable state and federal regulations. The applicable regulatory authority for this action is {{regulatory_reference}}.

Please direct all inquiries and dispute submissions to {{analyst_name}}, your assigned Payment Integrity Analyst, at {{analyst_phone}}. All correspondence should reference case number {{case_number}} to ensure proper routing.

Sincerely,

{{analyst_name}}
Payment Integrity Analyst — Medicaid Programs
{{plan_name}} — Program Integrity Unit
Phone: {{analyst_phone}}

This notice is issued pursuant to applicable state and federal Medicaid program integrity requirements. Recipient is advised to retain this correspondence for compliance recordkeeping purposes.
""",
    },
]


def run(db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    try:
        if conn.execute("SELECT COUNT(*) FROM letter_templates").fetchone()[0]:
            print("  letter_templates already seeded — skipping")
            return 0

        # Get the system user or first user for created_by
        user_row = conn.execute(
            "SELECT user_id FROM opa_users WHERE username = 'system.bot' LIMIT 1"
        ).fetchone()
        if not user_row:
            user_row = conn.execute("SELECT user_id FROM opa_users LIMIT 1").fetchone()
        created_by = user_row[0] if user_row else str(__import__("uuid").uuid4())

        for tmpl in TEMPLATES:
            conn.execute(
                "INSERT INTO letter_templates "
                "(template_id, lob, template_name, regulatory_reference, "
                "template_content, version, is_active, created_by_user_id, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    tmpl["template_id"],
                    tmpl["lob"],
                    tmpl["template_name"],
                    tmpl["regulatory_reference"],
                    tmpl["content"],
                    tmpl["version"],
                    1,
                    created_by,
                    NOW, NOW,
                ),
            )

        conn.commit()
        print(f"  Inserted {len(TEMPLATES)} letter templates")
        return len(TEMPLATES)
    finally:
        conn.close()


if __name__ == "__main__":
    run()
