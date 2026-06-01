"""SIU workspace endpoints — implements UC-SIU-01..06.

Router-level dep: require_app('siu'). Mutations on referrals + closure also
implicitly require investigator authority since they all flow through the
SIU app gate. Admin and supervisor roles automatically have siu access.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user, require_app
from ..models.workflow import OpaUser
from ..schemas.siu_schemas import (
    AddCaseToInvestigationIn,
    AddNoteIn,
    CloseInvestigationIn,
    EscalateCaseIn,
    FileReferralIn,
    GenerateExportIn,
    InvestigationNoteOut,
    InvestigationOut,
    LawEnforcementReferralOut,
    OpenInvestigationIn,
    RecordReferralOutcomeIn,
    SIUExportPackageOut,
    SIUQueueRow,
    UpdateInvestigationStatusIn,
)
from ..services.rbac_service import RBACService
from ..services.siu_service import SIUService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/siu",
    tags=["siu"],
    dependencies=[Depends(require_app("siu"))],
)


# ── Queue + detail ────────────────────────────────────────────────────────

@router.get("/queue", response_model=List[SIUQueueRow])
async def list_siu_queue(
    include_closed: bool = Query(False),
    pipeline_mode: Optional[str] = Query(
        None,
        description="Filter to 'post_pay' or 'pre_pay'; 'mixed' investigations always surface.",
        regex="^(post_pay|pre_pay)$",
    ),
    db: AsyncSession = Depends(get_db),
) -> List[SIUQueueRow]:
    return await SIUService(db).list_queue(
        include_closed=include_closed, pipeline_mode=pipeline_mode,
    )


@router.get("/investigations/{investigation_id}", response_model=InvestigationOut)
async def get_investigation(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> InvestigationOut:
    rbac = RBACService(db)
    role_names = await rbac.get_role_names_for_user(user.user_id)
    privileged = bool(role_names & {"admin", "supervisor", "siu_investigator", "system"})
    return await SIUService(db).get_investigation(
        investigation_id, include_confidential=privileged,
    )


# ── Pre-pay case detail (read-only, for SIU pre-pay investigation panel) ─

# Composed response: ClaimGuard's PrepayClaimDetail + the latest evidence-
# scanner findings, in one payload so the SIU detail page can render the
# rich pre-pay case view (ClaimGuard-style) with one round-trip.
#
# Read-only intentionally — SIU treats case evidence as frozen; the
# scan/recheck/mutate endpoints stay on the ClaimGuard router.

from pydantic import BaseModel  # noqa: E402

from sqlalchemy import select  # noqa: E402
from ..models.claims import Claim  # noqa: E402
from ..models.workflow import OpaCase  # noqa: E402
from ..schemas.prepay_schemas import PrepayClaimDetail  # noqa: E402
from ..routes.prepay_claims import _build_detail as _build_prepay_detail  # noqa: E402
from ..routes.prepay_evidence import (  # noqa: E402
    EvidenceFindingsResponse,
    _build_findings_response as _build_evidence_findings,
)


class PrepayCaseDetailForSIU(BaseModel):
    """Combined pre-pay case detail for the SIU investigation panel.

    `claim_detail` is ClaimGuard's PrepayClaimDetail shape (codes, AI
    findings, documents, comments, audit log). `evidence` is the latest
    code-evidence scanner output. SIU users get a read-only window into
    both without leaving the SIU app."""
    claim_detail: PrepayClaimDetail
    evidence: EvidenceFindingsResponse


@router.get(
    "/cases/{case_id}/prepay-detail",
    response_model=PrepayCaseDetailForSIU,
)
async def get_prepay_case_detail(
    case_id: str,
    db: AsyncSession = Depends(get_db),
) -> PrepayCaseDetailForSIU:
    """Pre-pay case detail for an SIU investigator. Resolves case → claim
    and returns the ClaimGuard-style detail bundle. Returns 404 if the case
    isn't pre-pay (post-pay cases route through a different detail
    builder — to be added when post-pay enrichment lands)."""
    case = (await db.execute(
        select(OpaCase).where(OpaCase.case_id == case_id)
    )).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == case.claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Linked claim not found")
    if (claim.pipeline_mode or "post_pay") != "pre_pay":
        raise HTTPException(
            status_code=404,
            detail="Case is not pre-pay; use the post-pay detail endpoint instead",
        )

    claim_detail = await _build_prepay_detail(db, claim)
    evidence = await _build_evidence_findings(claim, db)
    return PrepayCaseDetailForSIU(claim_detail=claim_detail, evidence=evidence)


# ── Post-pay case detail (read-only, for SIU post-pay investigation panel)

from ..schemas.case_schemas import CaseDetail  # noqa: E402
from ..services.case_service import CaseService  # noqa: E402


@router.get(
    "/cases/{case_id}/postpay-detail",
    response_model=CaseDetail,
)
async def get_postpay_case_detail(
    case_id: str,
    db: AsyncSession = Depends(get_db),
) -> CaseDetail:
    """Post-pay case detail for an SIU investigator. Returns the full
    PayGuard CaseDetail shape (member, provider, claim lines, detector
    results with FWA badges, recoupments, notes, audit). 404 if the case
    isn't post-pay (pre-pay cases use prepay-detail)."""
    case = (await db.execute(
        select(OpaCase).where(OpaCase.case_id == case_id)
    )).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == case.claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Linked claim not found")
    if (claim.pipeline_mode or "post_pay") != "post_pay":
        raise HTTPException(
            status_code=404,
            detail="Case is not post-pay; use the pre-pay detail endpoint instead",
        )

    # Reuse the existing PayGuard detail builder. It expects case_sequence,
    # not case_id — case_sequence is auto-assigned on creation so it's
    # always present.
    return await CaseService(db).get_case_detail(case.case_sequence)


# ── UC-SIU-01: escalate a case ───────────────────────────────────────────

@router.post("/escalate", response_model=InvestigationOut, status_code=201)
async def escalate_case(
    body: EscalateCaseIn,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> InvestigationOut:
    return await SIUService(db).escalate_case(body, actor_user_id=user.user_id)


# ── UC-SIU-02: open investigation, add case (pattern grouping) ───────────

@router.post(
    "/investigations/{investigation_id}/open",
    response_model=InvestigationOut,
)
async def open_investigation(
    investigation_id: str,
    body: OpenInvestigationIn,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> InvestigationOut:
    return await SIUService(db).open_investigation(
        investigation_id, body, actor_user_id=user.user_id,
    )


@router.post(
    "/investigations/{investigation_id}/cases",
    response_model=InvestigationOut,
    status_code=201,
)
async def add_case_to_investigation(
    investigation_id: str,
    body: AddCaseToInvestigationIn,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> InvestigationOut:
    return await SIUService(db).add_case_to_investigation(
        investigation_id, body, actor_user_id=user.user_id,
    )


# ── UC-SIU-03: notes + status updates ────────────────────────────────────

@router.post(
    "/investigations/{investigation_id}/notes",
    response_model=InvestigationNoteOut,
    status_code=201,
)
async def add_note(
    investigation_id: str,
    body: AddNoteIn,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> InvestigationNoteOut:
    svc = SIUService(db)
    return await svc.add_note(
        investigation_id,
        None,  # placeholder; ignored
        actor_user_id=user.user_id,
        note_date=body.note_date,
        note_type=body.note_type,
        body=body.body,
        is_confidential=body.is_confidential,
    )


@router.patch(
    "/investigations/{investigation_id}/status",
    response_model=InvestigationOut,
)
async def update_status(
    investigation_id: str,
    body: UpdateInvestigationStatusIn,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> InvestigationOut:
    return await SIUService(db).update_investigation_status(
        investigation_id, body, actor_user_id=user.user_id,
    )


# ── UC-SIU-04: law enforcement referral ──────────────────────────────────

@router.post(
    "/investigations/{investigation_id}/referrals",
    response_model=LawEnforcementReferralOut,
    status_code=201,
)
async def file_referral(
    investigation_id: str,
    body: FileReferralIn,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> LawEnforcementReferralOut:
    return await SIUService(db).file_referral(
        investigation_id, body, actor_user_id=user.user_id,
    )


@router.patch(
    "/investigations/{investigation_id}/referrals/{referral_id}",
    response_model=LawEnforcementReferralOut,
)
async def record_referral_outcome(
    investigation_id: str,
    referral_id: str,
    body: RecordReferralOutcomeIn,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> LawEnforcementReferralOut:
    return await SIUService(db).record_referral_outcome(
        investigation_id, referral_id, body, actor_user_id=user.user_id,
    )


# ── UC-SIU-05: close investigation ───────────────────────────────────────

@router.post(
    "/investigations/{investigation_id}/close",
    response_model=InvestigationOut,
)
async def close_investigation(
    investigation_id: str,
    body: CloseInvestigationIn,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> InvestigationOut:
    return await SIUService(db).close_investigation(
        investigation_id, body, actor_user_id=user.user_id,
    )


# ── UC-SIU-06: JSON export ───────────────────────────────────────────────

@router.post(
    "/investigations/{investigation_id}/exports",
    response_model=SIUExportPackageOut,
    status_code=201,
)
async def generate_export(
    investigation_id: str,
    body: GenerateExportIn = GenerateExportIn(),
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> SIUExportPackageOut:
    return await SIUService(db).generate_export(
        investigation_id,
        actor_user_id=user.user_id,
        delivery_destination=body.delivery_destination,
    )


@router.get(
    "/investigations/{investigation_id}/exports/{package_id}/download",
)
async def download_export(
    investigation_id: str,
    package_id: str,
    db: AsyncSession = Depends(get_db),
):
    payload, digest = await SIUService(db).get_export_payload(
        investigation_id, package_id,
    )
    return Response(
        content=payload,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="siu-{investigation_id[:8]}-{package_id[:8]}.json"',
            "X-SIU-Integrity-SHA256": digest,
        },
    )
