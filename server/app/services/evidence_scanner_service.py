"""Evidence scanner — checks attached PDFs for medical-record support of
ICD-10 / DRG codes on a claim.

Pattern adapted from prior-auth-v2's evaluation.js: store per-document
extracted text once at upload time; on each scan, concatenate document
texts (with === DOCUMENT: filename === headers), send to Claude with the
list of codes and their evidence-requirement descriptions, and parse a
structured JSON response of {result, evidence_text, document_name,
page_number, section_heading, gap_description} per code.

Frontend deep-links from the finding to the PDF page; pdf.js does the
text-position highlighting client-side (no server-side coordinates).

The scanner does ONE LLM call per claim covering all codes — keeps cost
predictable and the prompt size bounded by document text, not code count.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.claims import Claim, ClaimLine
from ..models.workflow import (
    CodeEvidenceRequirement,
    Document,
    EvidenceFinding,
)
from .pdf_extraction_service import extract_text as extract_pdf_text


logger = logging.getLogger(__name__)

MODEL = os.getenv("CLAIMGUARD_MODEL", "claude-sonnet-4-20250514")

# Hard cap on per-document text to keep prompts well under the model's
# context window when several PDFs are attached. Matches prior-auth-v2's
# convention of trimming each document independently rather than truncating
# the concatenation.
MAX_DOC_TEXT_CHARS = 60_000


_PROMPT = """You are a medical record evidence reviewer. For each diagnosis code listed below, decide whether the attached medical record text contains documentary evidence to justify that code.

For every code, return ONE row in the JSON output:

{
  "results": [
    {
      "code": "<the code, e.g. 'I50.21' or '470'>",
      "result": "found" | "not_found" | "partial",
      "confidence": "high" | "medium" | "low",
      "evidence_text": "<exact short verbatim quote from one of the documents (under 100 words). Do NOT paraphrase. If result=not_found, set to null.>",
      "document_name": "<exact filename from === DOCUMENT: filename === header where the evidence was found. Null if result=not_found.>",
      "page_number": <integer page number within that document. Estimate from text position. Null if cannot determine.>,
      "section_heading": "<nearest section heading above the evidence, e.g. 'HISTORY OF PRESENT ILLNESS', 'ASSESSMENT'. Null if no clear heading.>",
      "gap_description": "<one-sentence description of what's missing — only when result is not_found or partial. Null otherwise.>"
    },
    ...
  ]
}

RULES:
- "found": clear, explicit evidence in the medical record that satisfies the requirement.
- "partial": some evidence present but key elements missing or ambiguous.
- "not_found": no evidence in any attached document.
- Use HIGH confidence only when the evidence is explicit and unambiguous.
- evidence_text MUST be a direct quote from the document text — copy it verbatim, do not summarize.
- If multiple documents contain evidence, pick the strongest single source for the main fields.
- Return one row per code. Do not skip codes.

CODES TO SCAN:
{{CODES_BLOCK}}

ATTACHED MEDICAL RECORDS:
{{DOCUMENTS_BLOCK}}

Respond ONLY with valid JSON matching the schema above."""


def _client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:
        raise RuntimeError("anthropic SDK not installed") from e
    return AsyncAnthropic(api_key=api_key)


async def ensure_document_text(doc: Document, db: AsyncSession) -> None:
    """Back-fill documents.extracted_text for an existing document. Cheap
    no-op when already extracted. Logs and writes status='failed' on error
    so a future re-scan doesn't retry a broken PDF indefinitely."""
    if doc.extraction_status == "complete":
        return
    p = Path(doc.file_path) if doc.file_path else None
    if p is None or not p.exists():
        doc.extraction_status = "failed"
        doc.extracted_at = datetime.utcnow().isoformat()
        return
    text, pages = extract_pdf_text(p)
    doc.extracted_text = text or ""
    doc.page_count = pages or 0
    doc.extraction_status = "complete" if text else "failed"
    doc.extracted_at = datetime.utcnow().isoformat()


async def _claim_codes_with_requirements(
    claim: Claim, db: AsyncSession,
) -> list[dict[str, Any]]:
    """Return the (code_type, code, requirement) triples for this claim.
    Codes without a registered requirement still appear with requirement=None
    so the analyst can see the scan ran against every code on the claim.
    The prompt synthesizes a generic 'document the diagnosis' requirement
    when none is registered."""
    # Unique ICD-10 set (primary_icd + per-line array)
    lines_res = await db.execute(
        select(ClaimLine).where(ClaimLine.claim_id == claim.claim_id)
    )
    lines = list(lines_res.scalars().all())
    icd_codes: list[str] = []
    seen: set[str] = set()
    for code in [claim.primary_icd]:
        if code and code not in seen:
            icd_codes.append(code)
            seen.add(code)
    for ln in lines:
        if not ln.icd_codes:
            continue
        try:
            arr = json.loads(ln.icd_codes)
        except Exception:
            continue
        for code in arr or []:
            if code and code not in seen:
                icd_codes.append(code)
                seen.add(code)

    # DRG (optional, single)
    drgs = [claim.drg] if claim.drg else []

    # Load any active requirements for these codes
    all_codes_filter = [("icd10", c) for c in icd_codes] + [("drg", c) for c in drgs]
    if not all_codes_filter:
        return []

    req_rows = (await db.execute(
        select(CodeEvidenceRequirement).where(
            CodeEvidenceRequirement.is_active == True  # noqa: E712
        )
    )).scalars().all()
    req_index = {(r.code_type, r.code): r for r in req_rows}

    out: list[dict[str, Any]] = []
    for ct, c in all_codes_filter:
        req = req_index.get((ct, c))
        out.append({
            "code_type": ct,
            "code": c,
            "requirement": req,
            "title": req.title if req else None,
            "description": (
                req.requirement_description if req
                else f"Document the basis for assigning code {c}: confirming "
                     f"diagnostic findings (signs/symptoms, labs, imaging) and "
                     f"a clinician note attributing them to {c}."
            ),
        })
    return out


async def _claim_documents(claim: Claim, db: AsyncSession) -> list[Document]:
    """Return medical-record-style docs on this claim (excludes claim_form
    intake PDFs whose text is already the claim's own form). Lazily back-
    fills extracted_text on any not yet extracted."""
    rows = (await db.execute(
        select(Document)
        .where(Document.claim_id == claim.claim_id)
        .where(Document.kind.in_(("supporting", "medical_record")))
    )).scalars().all()

    for d in rows:
        if d.extraction_status != "complete":
            await ensure_document_text(d, db)
    return list(rows)


def _build_codes_block(codes: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for c in codes:
        title = f" — {c['title']}" if c["title"] else ""
        lines.append(f"• {c['code_type'].upper()} {c['code']}{title}")
        lines.append(f"    Required evidence: {c['description']}")
    return "\n".join(lines)


def _build_documents_block(docs: list[Document]) -> str:
    if not docs:
        return "(no medical records attached)"
    parts: list[str] = []
    for d in docs:
        text = (d.extracted_text or "").strip()
        if not text:
            continue
        if len(text) > MAX_DOC_TEXT_CHARS:
            text = text[:MAX_DOC_TEXT_CHARS] + "\n…[truncated]"
        parts.append(f"=== DOCUMENT: {d.filename} ===\n{text}")
    if not parts:
        return "(documents attached but no extracted text available)"
    return "\n\n---\n\n".join(parts)


def _parse_response(raw: str) -> list[dict[str, Any]]:
    """Pull the JSON object out of Claude's response. Tolerant of leading/
    trailing commentary, code fences, or trailing commas."""
    # Find the outermost {...}
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise ValueError("No JSON object in scanner response")
    blob = m.group(0)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        # Strip trailing commas before close brackets — a common Claude tic
        cleaned = re.sub(r",(\s*[\]}])", r"\1", blob)
        data = json.loads(cleaned)
    results = data.get("results") or []
    if not isinstance(results, list):
        raise ValueError("'results' must be a list")
    return results


async def scan_claim(claim: Claim, db: AsyncSession) -> dict[str, Any]:
    """Scan a claim's attached medical records for evidence of each ICD/DRG
    code. Upserts evidence_findings rows. Returns a small summary the route
    can hand back to the client."""
    codes = await _claim_codes_with_requirements(claim, db)
    docs = await _claim_documents(claim, db)

    # Document filename → document_id index so we can attribute Claude's
    # "document_name" string back to the actual document record.
    by_filename = {d.filename: d for d in docs}

    now = datetime.utcnow().isoformat()

    if not codes:
        return {"scanned": 0, "results": [], "reason": "no codes on claim"}

    # If there are no documents (or none with extracted text), emit
    # not_found findings for every code without an LLM call. The analyst
    # still sees a row per code with a clear gap description.
    has_any_text = any((d.extracted_text or "").strip() for d in docs)
    if not has_any_text:
        await _upsert_no_doc_findings(claim, codes, db, now)
        await db.flush()
        return {
            "scanned": len(codes),
            "results": [],
            "reason": "no medical-record documents with extracted text",
        }

    prompt = (
        _PROMPT
        .replace("{{CODES_BLOCK}}", _build_codes_block(codes))
        .replace("{{DOCUMENTS_BLOCK}}", _build_documents_block(docs))
    )

    client = _client()
    resp = await client.messages.create(
        model=MODEL,
        max_tokens=4_000,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text if resp.content else ""

    try:
        parsed_results = _parse_response(raw)
    except Exception as e:
        logger.exception("evidence_scanner: response parse failed: %s", e)
        # Fail soft — record not_found for every code so the analyst sees
        # the scan ran but didn't produce findings, instead of a 500.
        await _upsert_no_doc_findings(
            claim, codes, db, now, gap="scan response could not be parsed",
        )
        return {"scanned": len(codes), "results": [], "error": str(e)}

    by_code = {r.get("code"): r for r in parsed_results if isinstance(r, dict)}

    # Upsert one finding row per code we asked about
    written: list[str] = []
    for c in codes:
        r = by_code.get(c["code"]) or {}
        result = (r.get("result") or "not_found").lower()
        if result not in ("found", "not_found", "partial"):
            result = "not_found"
        confidence = (r.get("confidence") or "").lower() or None
        if confidence and confidence not in ("high", "medium", "low"):
            confidence = None
        doc_name = r.get("document_name") or None
        doc_id = by_filename[doc_name].document_id if doc_name in by_filename else None
        page_number = r.get("page_number")
        try:
            page_number = int(page_number) if page_number is not None else None
        except (TypeError, ValueError):
            page_number = None
        additional = r.get("additional_sources") or []
        if not isinstance(additional, list):
            additional = []

        await _upsert_finding(
            db,
            claim_id=claim.claim_id,
            document_id=doc_id,
            requirement_id=(c["requirement"].requirement_id if c["requirement"] else None),
            code_type=c["code_type"],
            code=c["code"],
            result=result,
            confidence=confidence,
            evidence_text=r.get("evidence_text") or None,
            page_number=page_number,
            section_heading=r.get("section_heading") or None,
            additional_sources=json.dumps(additional),
            gap_description=r.get("gap_description") or None,
            model_used=MODEL,
            scanned_at=now,
        )
        written.append(c["code"])

    await db.flush()
    return {"scanned": len(codes), "results": parsed_results, "written": written}


async def _upsert_finding(
    db: AsyncSession,
    *,
    claim_id: str,
    document_id: Optional[str],
    requirement_id: Optional[str],
    code_type: str,
    code: str,
    result: str,
    confidence: Optional[str],
    evidence_text: Optional[str],
    page_number: Optional[int],
    section_heading: Optional[str],
    additional_sources: str,
    gap_description: Optional[str],
    model_used: Optional[str],
    scanned_at: str,
) -> None:
    """Insert a new evidence_findings row or update the existing
    (claim_id, code_type, code) row. SQLite lacks UPSERT in older SQLAlchemy
    versions, so do it manually."""
    existing = (await db.execute(
        select(EvidenceFinding).where(
            EvidenceFinding.claim_id == claim_id,
            EvidenceFinding.code_type == code_type,
            EvidenceFinding.code == code,
        )
    )).scalar_one_or_none()

    if existing is None:
        db.add(EvidenceFinding(
            finding_id=str(uuid.uuid4()),
            claim_id=claim_id,
            document_id=document_id,
            requirement_id=requirement_id,
            code_type=code_type,
            code=code,
            result=result,
            confidence=confidence,
            evidence_text=evidence_text,
            page_number=page_number,
            section_heading=section_heading,
            additional_sources=additional_sources,
            gap_description=gap_description,
            model_used=model_used,
            scanned_at=scanned_at,
        ))
        return

    existing.document_id = document_id
    existing.requirement_id = requirement_id
    existing.result = result
    existing.confidence = confidence
    existing.evidence_text = evidence_text
    existing.page_number = page_number
    existing.section_heading = section_heading
    existing.additional_sources = additional_sources
    existing.gap_description = gap_description
    existing.model_used = model_used
    existing.scanned_at = scanned_at


async def _upsert_no_doc_findings(
    claim: Claim,
    codes: list[dict[str, Any]],
    db: AsyncSession,
    now: str,
    gap: str = "No medical-record documents attached to this claim.",
) -> None:
    for c in codes:
        await _upsert_finding(
            db,
            claim_id=claim.claim_id,
            document_id=None,
            requirement_id=(c["requirement"].requirement_id if c["requirement"] else None),
            code_type=c["code_type"],
            code=c["code"],
            result="not_found",
            confidence=None,
            evidence_text=None,
            page_number=None,
            section_heading=None,
            additional_sources="[]",
            gap_description=gap,
            model_used=None,
            scanned_at=now,
        )
