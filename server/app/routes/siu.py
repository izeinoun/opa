"""SIU workspace endpoints — implements UC-SIU-01..06.

Router-level dep: require_app('siu'). Mutations on referrals + closure also
implicitly require investigator authority since they all flow through the
SIU app gate. Admin and supervisor roles automatically have siu access.
"""
from __future__ import annotations

import logging
from typing import List

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
    db: AsyncSession = Depends(get_db),
) -> List[SIUQueueRow]:
    return await SIUService(db).list_queue(include_closed=include_closed)


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
