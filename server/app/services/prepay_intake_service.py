"""Pre-pay claim intake orchestrator.

Converts an extracted-from-PDF claim dict into rows on the unified model:
  • Attempts to resolve patient (member) and provider from reference data.
    If resolution fails, provisional records are created so the claim can
    still be persisted and run through the full detector pipeline. STR-013
    and STR-014 will surface missing/unresolvable member data as findings.
  • Creates a `claims` row with pipeline_mode='pre_pay' and the ClaimGuard-
    style fields (claim_form_type, care_setting, drg, description,
    extracted_text, etc.). Stores submitted_member_number and
    submitted_patient_dob from the raw extraction for detector use.
  • Creates one `claim_lines` row per CPT code (with even-split billed
    amount allocation matching ClaimGuard's heuristic).
  • Persists the source PDF as a `documents` row with kind='claim_form'.

Returns the new claim_id (UUID).
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.claims import Claim, ClaimLine
from ..models.reference import Member, Provider, ProviderOrg
from ..models.workflow import Document

logger = logging.getLogger(__name__)


# Storage location for inbound documents. Configurable via env so it can point
# at a mounted volume in production.
UPLOAD_DIR = Path(os.getenv("OPA_UPLOAD_DIR", "./uploads"))
FORMS_DIR = UPLOAD_DIR / "forms"

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    base = os.path.basename(name or "")
    base = _SAFE_FILENAME.sub("_", base)[:120]
    return base or "upload.pdf"


# ── Reference-data resolvers ──────────────────────────────────────────────

class IntakeValidationError(Exception):
    """Raised when an intake claim references reference data that doesn't exist.

    Per the architectural principle, claims for unknown providers/members are
    rejected at intake (status 422). The reference-sync flow is responsible for
    bringing those entities into our DB before the intake adapter runs.
    """


async def _resolve_member(
    db: AsyncSession,
    *,
    patient_name: str,
    dob: Optional[str],
) -> Optional[Member]:
    """Best-effort member resolution by name + DOB. Returns None if not found."""
    name = (patient_name or "").strip()
    if not name:
        return None
    parts = name.split(maxsplit=1)
    first = parts[0]
    last = parts[1] if len(parts) > 1 else ""

    stmt = select(Member).where(
        Member.first_name.ilike(first),
        Member.last_name.ilike(last) if last else Member.last_name.is_not(None),
    )
    if dob:
        stmt = stmt.where(Member.date_of_birth == dob)
    stmt = stmt.order_by(Member.member_id)

    res = await db.execute(stmt)
    members = list(res.scalars().all())
    if not members:
        return None
    if len(members) > 1:
        logger.warning(
            "Multiple members matched '%s' DOB=%s; picking %s",
            name, dob, members[0].member_id,
        )
    return members[0]


async def _create_provisional_member(
    db: AsyncSession,
    *,
    patient_name: str,
    dob: Optional[str],
    lob: str = "commercial",
) -> Member:
    """Create a provisional member record when reference resolution fails.

    The provisional member_number prefix makes it identifiable for later
    reconciliation. STR-013/STR-014 will fire based on submitted_patient_dob
    and submitted_member_number on the claim — not this record's fields.
    """
    now = datetime.utcnow().isoformat()
    name = (patient_name or "Unknown Patient").strip()
    parts = name.split(maxsplit=1)
    first = parts[0]
    last = parts[1] if len(parts) > 1 else "Unknown"
    provisional_id = str(uuid.uuid4())
    member = Member(
        member_id=provisional_id,
        member_number=f"PROVISIONAL-{provisional_id[:8].upper()}",
        first_name=first,
        last_name=last,
        date_of_birth=dob or "0000-00-00",
        lob=lob,
        coverage_effective_date="0000-00-00",
        created_at=now,
        updated_at=now,
    )
    db.add(member)
    logger.warning(
        "Member not resolved for '%s' DOB=%s — provisional record %s created",
        name, dob, provisional_id,
    )
    return member


async def _resolve_provider_org(
    db: AsyncSession, *, provider_name: str
) -> Optional[Tuple[ProviderOrg, Provider]]:
    """Resolve a provider-org + billing provider by name. Returns None if not found."""
    name = (provider_name or "").strip()
    if not name:
        return None
    org_res = await db.execute(
        select(ProviderOrg).where(ProviderOrg.name.ilike(name)).limit(1)
    )
    org = org_res.scalar_one_or_none()
    if org is None:
        return None
    prov_res = await db.execute(
        select(Provider).where(Provider.provider_org_id == org.provider_org_id).limit(1)
    )
    provider = prov_res.scalar_one_or_none()
    if provider is None:
        return None
    return org, provider


async def _create_provisional_provider(
    db: AsyncSession,
    *,
    provider_name: str,
) -> Tuple[ProviderOrg, Provider]:
    """Create provisional provider org + provider when reference resolution fails."""
    now = datetime.utcnow().isoformat()
    provisional_id = str(uuid.uuid4())
    name = (provider_name or "Unknown Provider").strip()
    org = ProviderOrg(
        provider_org_id=provisional_id,
        name=name,
        npi=f"PROVISIONAL-{provisional_id[:10].upper()}",
        tin=f"XX{provisional_id[:7].upper()}",
        org_type="group",
        is_sensitive=False,
        risk_score=0.5,
        created_at=now,
        updated_at=now,
    )
    db.add(org)
    provider = Provider(
        provider_id=str(uuid.uuid4()),
        provider_org_id=provisional_id,
        npi=f"PROVISIONAL-{provisional_id[:10].upper()}",
        tin=org.tin,
        name=name,
        specialty="unknown",
        credential_status="active",
        credential_effective_date="0000-00-00",
        is_excluded=False,
        billing_variance_score=0.5,
        created_at=now,
        updated_at=now,
    )
    db.add(provider)
    logger.warning(
        "Provider not resolved for '%s' — provisional org %s created",
        name, provisional_id,
    )
    return org, provider


# ── Field normalizers (preserve ClaimGuard's defensive behavior) ─────────

def _normalize_claim_form_type(v: Any) -> str:
    s = (v or "CMS-1500")
    return s if s in {"CMS-1500", "UB-04"} else "CMS-1500"


def _normalize_care_setting(v: Any, claim_form_type: str) -> str:
    s = v or ("Inpatient" if claim_form_type == "UB-04" else "Outpatient")
    return s if s in {"Inpatient", "Outpatient"} else "Outpatient"


def _normalize_specialty(v: Any) -> str:
    s = (v or "Other")
    return s if s in {"Surgical", "Oncology", "Inpatient", "Other"} else "Other"


def _normalize_billed(v: Any) -> float:
    try:
        b = float(v or 0)
    except (TypeError, ValueError):
        b = 0.0
    return max(b, 0.0)


# ── Main entry point ──────────────────────────────────────────────────────

async def ingest_extracted_claim(
    db: AsyncSession,
    *,
    extracted: dict[str, Any],
    pdf_bytes: Optional[bytes] = None,
    pdf_filename: Optional[str] = None,
    uploaded_by_user_id: Optional[str] = None,
    icn: Optional[str] = None,
) -> str:
    """Create claim + lines (+ source-PDF document if provided) from an
    extracted claim dict. Used by both PDF intake and manual creation.

    Returns the new `claim_id` (UUID). Raises IntakeValidationError if any
    reference data is missing — the caller should surface this as a 422.
    """
    claim_form_type = _normalize_claim_form_type(extracted.get("type"))
    care_setting    = _normalize_care_setting(extracted.get("claim_form"), claim_form_type)
    specialty       = _normalize_specialty(extracted.get("specialty"))
    billed          = _normalize_billed(extracted.get("billed_amount"))
    # Prefer structured lines from new extraction; fall back to flat cpts list.
    raw_lines: list[dict] = [l for l in (extracted.get("lines") or []) if l and l.get("cpt")]
    if raw_lines:
        cpts = [str(l["cpt"]) for l in raw_lines]
    else:
        cpts = [str(c) for c in (extracted.get("cpts") or []) if c]
    icd10: list[str] = [str(c) for c in (extracted.get("icd10") or []) if c]
    dos             = extracted.get("dos") or datetime.utcnow().strftime("%Y-%m-%d")
    description     = (extracted.get("description") or "")[:1000]

    # Raw values from the submission — captured before resolution so detectors
    # can check what the submitter actually provided (STR-013, STR-014).
    submitted_dob           = extracted.get("dob") or None
    submitted_member_number = extracted.get("member_number") or None
    patient_name            = str(extracted.get("patient") or "")
    provider_name           = str(extracted.get("provider") or "")

    # ── 1. Reference-data resolution (non-blocking) ──────────────────────
    # Try to resolve member and provider. On failure, create provisional
    # records so the claim can still be ingested and run through the full
    # detector pipeline — STR-013/014 will surface the gaps as findings.
    member = await _resolve_member(db, patient_name=patient_name, dob=submitted_dob)
    if member is None:
        member = await _create_provisional_member(
            db, patient_name=patient_name, dob=submitted_dob
        )

    provider_result = await _resolve_provider_org(db, provider_name=provider_name)
    if provider_result is None:
        org, provider = await _create_provisional_provider(db, provider_name=provider_name)
    else:
        org, provider = provider_result

    # ── 2. Create the claim row ──────────────────────────────────────────
    claim_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    new_icn = icn or f"PREPAY-{datetime.utcnow().strftime('%Y%m%d')}-{claim_id[:8].upper()}"

    claim = Claim(
        claim_id=claim_id,
        icn=new_icn,
        case_group_id=None,
        member_id=member.member_id,
        provider_org_id=org.provider_org_id,
        billing_provider_npi=provider.npi,
        rendering_provider_npi=provider.npi,
        lob=member.lob or "commercial",
        pipeline_mode="pre_pay",
        service_from_date=dos,
        service_to_date=dos,
        claim_type="professional" if claim_form_type == "CMS-1500" else "institutional",
        claim_form_type=claim_form_type,
        care_setting=care_setting,
        drg=extracted.get("drg") or None,
        specialty=specialty,
        description=description,
        submitted_member_number=submitted_member_number,
        submitted_patient_dob=submitted_dob,
        extracted_text=None,        # populated separately from the raw PDF text
        claim_summary=None,         # populated on-demand by AI service
        code_descriptions=None,
        claim_status="pending",
        total_billed=billed,
        total_paid=None,            # pre-pay → no payment yet
        paid_date=None,
        authorization_number=None,
        submission_date=now[:10],
        pos_code="11",              # office; can be refined later
        primary_icd=icd10[0] if icd10 else "Z00.00",
        source_type="pdf",
        era_transaction_id=None,
        raw_claim_json=json.dumps({"source": "pdf_intake", "extracted": extracted}),
        created_at=now,
        updated_at=now,
    )
    db.add(claim)
    await db.flush()

    # ── 3. Create claim_lines ─────────────────────────────────────────────
    # Use structured lines from extraction when available (includes revenue_code,
    # modifiers, per-line charge). Fall back to even-split for flat cpts lists.
    if cpts:
        per_line_fallback = round(billed / len(cpts), 2)
        for i, code in enumerate(cpts, start=1):
            rl = raw_lines[i - 1] if raw_lines and i <= len(raw_lines) else {}
            mods = rl.get("modifiers") or []
            charge = rl.get("charge")
            db.add(ClaimLine(
                claim_line_id=str(uuid.uuid4()),
                claim_id=claim_id,
                line_number=i,
                cpt_code=code,
                diag_1=icd10[0] if len(icd10) > 0 else None,
                diag_2=icd10[1] if len(icd10) > 1 else None,
                diag_3=icd10[2] if len(icd10) > 2 else None,
                diag_4=icd10[3] if len(icd10) > 3 else None,
                modifier_1=str(mods[0]) if len(mods) > 0 else None,
                modifier_2=str(mods[1]) if len(mods) > 1 else None,
                units_billed=int(rl.get("units") or 1),
                units_paid=None,
                billed_amount=round(float(charge), 2) if charge is not None else per_line_fallback,
                paid_amount=None,
                allowed_amount=None,
                pos_code="11",
                revenue_code=str(rl.get("revenue_code") or "") or None,
            ))

    # ── 4. Persist the source PDF as a document (skipped for manual create) ─
    if pdf_bytes is not None and pdf_filename is not None:
        safe = safe_filename(pdf_filename)
        final_name = f"{claim_id[:8]}_source_{safe}"
        final_path = FORMS_DIR / final_name
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(pdf_bytes)
        db.add(Document(
            document_id=str(uuid.uuid4()),
            claim_id=claim_id,
            case_id=None,
            filename=final_name,
            file_path=str(final_path),
            file_size_kb=max(1, len(pdf_bytes) // 1024),
            kind="claim_form",
            uploaded_at=now,
            uploaded_by_user_id=uploaded_by_user_id,
        ))

    await db.commit()
    return claim_id
