"""Seed generic LLM document templates — synchronous sqlite3.

Two starter templates, one per app, demonstrating the shared `document_templates`
table partitioned by the `app` discriminator:
  • payguard   — provider overpayment recovery notice (Markdown)
  • claimguard — pre-pay claim review determination letter (Markdown)

These are LLM-driven: `task_prompt` instructs the model and `template_markdown`
is the structure it fills from caller-supplied content. Distinct from the
deterministic {{placeholder}} letter_templates seeded by seed_letter_templates.
"""
from __future__ import annotations

import os
import sqlite3
import uuid

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2024-01-01T08:00:00"

TEMPLATES = [
    {
        "app": "payguard",
        "name": "Provider Overpayment Recovery Notice",
        "description": "Post-pay recovery notice generated from case + finding data.",
        "task_prompt": (
            "Draft a formal provider overpayment recovery notice. Use the case, "
            "provider, member, and finding details in the content. State the "
            "overpayment amount, summarize each finding plainly, cite the "
            "regulatory references provided, and give the response due date. "
            "Keep a professional, non-accusatory tone."
        ),
        "template_markdown": (
            "# Overpayment Recovery Notice\n\n"
            "**Case:** {case_number}  \n"
            "**Date:** {notice_date}\n\n"
            "**To:** {provider_name} (NPI {provider_npi})\n\n"
            "Dear {provider_name},\n\n"
            "This notice concerns a post-payment review of claims for member "
            "{member_name} (ID {member_id}).\n\n"
            "## Summary of Findings\n\n"
            "{findings}\n\n"
            "**Total overpayment identified:** {overpayment_amount}\n\n"
            "## Your Rights and Obligations\n\n"
            "Pursuant to {regulatory_reference}, please remit or dispute the "
            "identified overpayment by **{response_due_date}**.\n\n"
            "## Recovery Method\n\n"
            "{recovery_method}\n\n"
            "Sincerely,  \n{analyst_name}\n"
        ),
    },
    {
        "app": "claimguard",
        "name": "Pre-Pay Claim Review Determination",
        "description": "Pre-pay determination letter generated from claim review findings.",
        "task_prompt": (
            "Draft a pre-payment claim review determination letter. Summarize "
            "the reviewed claim, list each review finding with its severity, and "
            "state the determination (approve, deny, or pend for documentation). "
            "Be specific about what documentation, if any, is required."
        ),
        "template_markdown": (
            "# Claim Review Determination\n\n"
            "**Claim:** {claim_id}  \n"
            "**Date of Service:** {dos}  \n"
            "**Provider:** {provider}  \n"
            "**Patient:** {patient}\n\n"
            "## Determination\n\n"
            "{determination}\n\n"
            "## Review Findings\n\n"
            "{findings}\n\n"
            "## Required Documentation\n\n"
            "{required_documentation}\n"
        ),
    },
]


def run(db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    try:
        if conn.execute("SELECT COUNT(*) FROM document_templates").fetchone()[0]:
            print("  document_templates already seeded — skipping")
            return 0

        user_row = conn.execute(
            "SELECT user_id FROM opa_users WHERE username = 'system.bot' LIMIT 1"
        ).fetchone()
        if not user_row:
            user_row = conn.execute("SELECT user_id FROM opa_users LIMIT 1").fetchone()
        created_by = user_row[0] if user_row else None

        for tmpl in TEMPLATES:
            conn.execute(
                "INSERT INTO document_templates "
                "(template_id, app, name, description, task_prompt, "
                "template_markdown, version, is_active, created_by_user_id, "
                "created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    tmpl["app"],
                    tmpl["name"],
                    tmpl["description"],
                    tmpl["task_prompt"],
                    tmpl["template_markdown"],
                    1,
                    1,
                    created_by,
                    NOW, NOW,
                ),
            )

        conn.commit()
        print(f"  Inserted {len(TEMPLATES)} document templates")
        return len(TEMPLATES)
    finally:
        conn.close()


if __name__ == "__main__":
    run()
