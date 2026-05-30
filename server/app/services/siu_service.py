"""SIU workspace service — escalation, investigation lifecycle, LE referrals,
JSON export. Implements the spec from UC-SIU-01..06.

Server-side enforcement:
  - siu_frozen blocks writes to the case outside the SIU workspace
  - law_enforcement_hold blocks recovery + closure on the case
  - Investigation closure is blocked while any active LE referral exists
  - Investigation notes are immutable after save (no update endpoint)
  - LE referrals are immutable after submission (only response/outcome editable)
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional, Sequence

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.claims import Claim
from ..models.reference import Member, ProviderOrg
from ..models.workflow import (
    AuditLog,
    Finding,
    InvestigationCase,
    InvestigationNote,
    LawEnforcementReferral,
    OpaCase,
    OpaUser,
    RuntimeConfig,
    SIUExportPackage,
    SIUInvestigation,
)
from ..schemas.siu_schemas import (
    AddCaseToInvestigationIn,
    CaseSummaryForSIU,
    CloseInvestigationIn,
    EscalateCaseIn,
    FileReferralIn,
    InvestigationNoteOut,
    InvestigationOut,
    LawEnforcementReferralOut,
    OpenInvestigationIn,
    RecordReferralOutcomeIn,
    SIUExportPackageOut,
    SIUQueueRow,
    UpdateInvestigationStatusIn,
)

logger = logging.getLogger(__name__)


# ── Enforcement helpers (re-usable by other services) ────────────────────

def assert_not_siu_frozen(case: OpaCase) -> None:
    """Reject writes on a case that's been frozen by an SIU escalation.
    Called by case write endpoints across PayGuard / ClaimGuard."""
    if case.siu_frozen:
        raise HTTPException(
            status_code=403,
            detail="Case evidence is frozen by an active SIU investigation. "
                   "Updates must go through the SIU workspace.",
        )


def assert_no_le_hold(case: OpaCase) -> None:
    """Reject recovery + closure actions on a case under a law enforcement hold."""
    if case.law_enforcement_hold:
        raise HTTPException(
            status_code=403,
            detail="Case has an active law enforcement hold. "
                   "Recovery and closure actions are blocked until the SIU "
                   "investigator closes the referral.",
        )


# ── Helpers ──────────────────────────────────────────────────────────────

async def _user_name(db: AsyncSession, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    res = await db.execute(select(OpaUser).where(OpaUser.user_id == user_id))
    u = res.scalar_one_or_none()
    return u.full_name if u else None


async def _resolve_siu_mode(db: AsyncSession) -> str:
    """Read 'siu_mode' from runtime_config; default to 'A' (internal)."""
    res = await db.execute(select(RuntimeConfig).where(RuntimeConfig.key == "siu_mode"))
    row = res.scalar_one_or_none()
    if not row:
        return "A"
    v = (row.value or "").strip().upper()
    return v if v in ("A", "B") else "A"


async def _case_to_summary(db: AsyncSession, case: OpaCase) -> CaseSummaryForSIU:
    # Provider org name + claim icn + member name + finding detector ids
    member_name: Optional[str] = None
    icn: Optional[str] = None
    provider_org_name: Optional[str] = None
    billing_npi: Optional[str] = None

    cm = await db.execute(select(Claim).where(Claim.claim_id == case.claim_id))
    claim = cm.scalar_one_or_none()
    if claim:
        icn = claim.icn
        billing_npi = claim.billing_provider_npi
        org = (await db.execute(
            select(ProviderOrg).where(ProviderOrg.provider_org_id == claim.provider_org_id)
        )).scalar_one_or_none()
        provider_org_name = org.name if org else None
        mem = (await db.execute(
            select(Member).where(Member.member_id == claim.member_id)
        )).scalar_one_or_none()
        if mem:
            member_name = f"{mem.first_name} {mem.last_name}"

    f_res = await db.execute(
        select(Finding.detector_id).where(Finding.claim_id == case.claim_id)
    )
    detector_ids = [r[0] for r in f_res.all() if r[0]]
    unique_dets = sorted(set(detector_ids))

    return CaseSummaryForSIU(
        case_id=case.case_id,
        case_number=case.case_number,
        claim_id=case.claim_id,
        icn=icn,
        provider_org_name=provider_org_name,
        billing_provider_npi=billing_npi,
        member_name=member_name,
        pipeline_mode=(claim.pipeline_mode if claim else "post_pay"),
        claim_status=(claim.claim_status if claim else "unknown"),
        case_status=case.status,
        total_overpayment_amount=case.total_overpayment_amount,
        detector_ids=unique_dets,
        siu_frozen=case.siu_frozen,
        law_enforcement_hold=case.law_enforcement_hold,
    )


def _audit(
    db: AsyncSession,
    *,
    case_id: Optional[str],
    actor_user_id: str,
    action: str,
    from_state: Optional[str] = None,
    to_state: Optional[str] = None,
    reason: Optional[str] = None,
    meta: Optional[dict] = None,
) -> None:
    db.add(AuditLog(
        audit_id=str(uuid.uuid4()),
        case_id=case_id,
        claim_id=None,
        actor_user_id=actor_user_id,
        action=action,
        from_state=from_state,
        to_state=to_state,
        reason=reason,
        meta_json=json.dumps(meta or {}),
        created_at=datetime.utcnow().isoformat(),
    ))


# ── Service ──────────────────────────────────────────────────────────────

class SIUService:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    # ── UC-SIU-01: receive escalated case ───────────────────────────────

    async def escalate_case(
        self, body: EscalateCaseIn, *, actor_user_id: str
    ) -> InvestigationOut:
        case = (await self.db.execute(
            select(OpaCase).where(OpaCase.case_id == body.case_id)
        )).scalar_one_or_none()
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        if case.siu_investigation_id and not body.target_investigation_id:
            raise HTTPException(
                status_code=409,
                detail=f"Case is already linked to investigation {case.siu_investigation_id}",
            )

        if body.target_investigation_id:
            # Pattern grouping: add case to an existing open investigation.
            inv = (await self.db.execute(
                select(SIUInvestigation).where(
                    SIUInvestigation.investigation_id == body.target_investigation_id
                )
            )).scalar_one_or_none()
            if inv is None:
                raise HTTPException(status_code=404, detail="Target investigation not found")
            if inv.status == "CLOSED":
                raise HTTPException(
                    status_code=409, detail="Target investigation is already closed"
                )
        else:
            now = datetime.utcnow().isoformat()
            inv = SIUInvestigation(
                investigation_id=str(uuid.uuid4()),
                investigation_type=body.investigation_type,
                status="OPEN",
                escalation_source=body.escalation_source,
                escalation_reason=body.escalation_reason,
                escalated_by_user_id=actor_user_id,
                escalated_at=now,
                siu_mode=await _resolve_siu_mode(self.db),
                created_at=now,
                updated_at=now,
            )
            self.db.add(inv)
            await self.db.flush()

        # Link case ↔ investigation, freeze the case, transition status
        old_status = case.status
        case.siu_investigation_id = inv.investigation_id
        case.siu_frozen = True
        case.status = "SIU_REFERRAL"
        case.updated_at = datetime.utcnow().isoformat()

        # M:N row (idempotent — skip if already linked)
        link_exists = (await self.db.execute(
            select(InvestigationCase).where(
                InvestigationCase.investigation_id == inv.investigation_id,
                InvestigationCase.case_id == case.case_id,
            )
        )).scalar_one_or_none()
        if link_exists is None:
            self.db.add(InvestigationCase(
                investigation_id=inv.investigation_id,
                case_id=case.case_id,
            ))

        _audit(
            self.db,
            case_id=case.case_id,
            actor_user_id=actor_user_id,
            action="SIU_ESCALATED",
            from_state=old_status,
            to_state="SIU_REFERRAL",
            reason=body.escalation_reason,
            meta={
                "investigation_id": inv.investigation_id,
                "escalation_source": body.escalation_source,
            },
        )

        await self.db.commit()
        return await self.get_investigation(inv.investigation_id)

    # ── UC-SIU-02: open investigation ───────────────────────────────────

    async def open_investigation(
        self,
        investigation_id: str,
        body: OpenInvestigationIn,
        *,
        actor_user_id: str,
    ) -> InvestigationOut:
        inv = await self._get_inv(investigation_id)
        if inv.opened_at:
            raise HTTPException(
                status_code=409, detail="Investigation already opened",
            )

        now = datetime.utcnow().isoformat()
        inv.investigator_assigned_user_id = (
            body.investigator_assigned_user_id or actor_user_id
        )
        inv.opened_at = now
        if body.investigation_type:
            inv.investigation_type = body.investigation_type
        inv.updated_at = now

        # Move all linked cases from SIU_REFERRAL → SIU_INVESTIGATION_OPEN
        cases = await self._cases_for(investigation_id)
        for c in cases:
            if c.status == "SIU_REFERRAL":
                _audit(
                    self.db,
                    case_id=c.case_id,
                    actor_user_id=actor_user_id,
                    action="SIU_INVESTIGATION_OPENED",
                    from_state=c.status,
                    to_state="SIU_INVESTIGATION_OPEN",
                    meta={"investigation_id": investigation_id},
                )
                c.status = "SIU_INVESTIGATION_OPEN"
                c.updated_at = now

        await self.db.commit()
        return await self.get_investigation(investigation_id)

    # ── UC-SIU-02 alternate: add case to existing investigation ─────────

    async def add_case_to_investigation(
        self,
        investigation_id: str,
        body: AddCaseToInvestigationIn,
        *,
        actor_user_id: str,
    ) -> InvestigationOut:
        inv = await self._get_inv(investigation_id)
        if inv.status == "CLOSED":
            raise HTTPException(status_code=409, detail="Investigation is closed")

        case = (await self.db.execute(
            select(OpaCase).where(OpaCase.case_id == body.case_id)
        )).scalar_one_or_none()
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        if case.siu_investigation_id and case.siu_investigation_id != investigation_id:
            raise HTTPException(
                status_code=409,
                detail=f"Case is already linked to a different investigation "
                       f"({case.siu_investigation_id})",
            )

        link_exists = (await self.db.execute(
            select(InvestigationCase).where(
                InvestigationCase.investigation_id == investigation_id,
                InvestigationCase.case_id == case.case_id,
            )
        )).scalar_one_or_none()
        if link_exists is None:
            self.db.add(InvestigationCase(
                investigation_id=investigation_id,
                case_id=case.case_id,
            ))

        now = datetime.utcnow().isoformat()
        old_status = case.status
        case.siu_investigation_id = investigation_id
        case.siu_frozen = True
        # If investigation already opened, snap the case to OPEN too; else REFERRAL.
        case.status = (
            "SIU_INVESTIGATION_OPEN" if inv.opened_at else "SIU_REFERRAL"
        )
        case.law_enforcement_hold = inv.law_enforcement_hold
        case.updated_at = now

        _audit(
            self.db,
            case_id=case.case_id,
            actor_user_id=actor_user_id,
            action="SIU_CASE_ADDED_TO_INVESTIGATION",
            from_state=old_status,
            to_state=case.status,
            meta={"investigation_id": investigation_id},
        )

        await self.db.commit()
        return await self.get_investigation(investigation_id)

    # ── UC-SIU-03: add note ─────────────────────────────────────────────

    async def add_note(
        self,
        investigation_id: str,
        note: InvestigationNoteOut,  # placeholder; actual input shape in route
        *,
        actor_user_id: str,
        note_date: str,
        note_type: str,
        body: str,
        is_confidential: bool,
    ) -> InvestigationNoteOut:
        inv = await self._get_inv(investigation_id)
        if inv.status == "CLOSED":
            raise HTTPException(
                status_code=409, detail="Cannot add notes to a closed investigation",
            )

        now = datetime.utcnow().isoformat()
        row = InvestigationNote(
            note_id=str(uuid.uuid4()),
            investigation_id=investigation_id,
            note_date=note_date,
            note_type=note_type,
            body=body,
            is_confidential=is_confidential,
            author_user_id=actor_user_id,
            created_at=now,
        )
        self.db.add(row)

        _audit(
            self.db,
            case_id=None,
            actor_user_id=actor_user_id,
            action="INVESTIGATION_NOTE_ADDED",
            meta={
                "investigation_id": investigation_id,
                "note_type": note_type,
                "confidential": is_confidential,
            },
        )
        await self.db.commit()
        return InvestigationNoteOut(
            note_id=row.note_id,
            investigation_id=row.investigation_id,
            note_date=row.note_date,
            note_type=row.note_type,
            body=row.body,
            is_confidential=row.is_confidential,
            author_user_id=row.author_user_id,
            author_name=await _user_name(self.db, row.author_user_id),
            created_at=row.created_at,
        )

    async def update_investigation_status(
        self,
        investigation_id: str,
        body: UpdateInvestigationStatusIn,
        *,
        actor_user_id: str,
    ) -> InvestigationOut:
        inv = await self._get_inv(investigation_id)
        if inv.status == "CLOSED":
            raise HTTPException(status_code=409, detail="Investigation is closed")
        old = inv.status
        inv.status = body.status
        if body.investigation_type:
            inv.investigation_type = body.investigation_type
        inv.updated_at = datetime.utcnow().isoformat()
        _audit(
            self.db,
            case_id=None,
            actor_user_id=actor_user_id,
            action="INVESTIGATION_STATUS_UPDATED",
            from_state=old,
            to_state=body.status,
            meta={"investigation_id": investigation_id},
        )
        await self.db.commit()
        return await self.get_investigation(investigation_id)

    # ── UC-SIU-04: file LE referral ─────────────────────────────────────

    async def file_referral(
        self,
        investigation_id: str,
        body: FileReferralIn,
        *,
        actor_user_id: str,
    ) -> LawEnforcementReferralOut:
        inv = await self._get_inv(investigation_id)
        if inv.status == "CLOSED":
            raise HTTPException(status_code=409, detail="Investigation is closed")

        now = datetime.utcnow().isoformat()
        ref = LawEnforcementReferral(
            referral_id=str(uuid.uuid4()),
            investigation_id=investigation_id,
            referral_date=body.referral_date,
            agency_name=body.agency_name,
            referral_type=body.referral_type,
            referral_summary=body.referral_summary,
            referral_contact_name=body.referral_contact_name,
            submitted_by_user_id=actor_user_id,
            submitted_at=now,
        )
        self.db.add(ref)

        # Activate the hard hold on the investigation + every linked case.
        inv.law_enforcement_hold = True
        # Status hint per spec (LAW_ENFORCEMENT_REFERRAL); use the
        # closest existing enum value (REFERRAL_SUBMITTED).
        inv.status = "REFERRAL_SUBMITTED"
        inv.updated_at = now

        cases = await self._cases_for(investigation_id)
        for c in cases:
            c.law_enforcement_hold = True
            c.updated_at = now
            _audit(
                self.db,
                case_id=c.case_id,
                actor_user_id=actor_user_id,
                action="LAW_ENFORCEMENT_REFERRAL_SUBMITTED",
                meta={
                    "investigation_id": investigation_id,
                    "referral_id": ref.referral_id,
                    "agency": body.agency_name,
                    "type": body.referral_type,
                },
            )

        await self.db.commit()
        return LawEnforcementReferralOut(
            referral_id=ref.referral_id,
            investigation_id=ref.investigation_id,
            referral_date=ref.referral_date,
            agency_name=ref.agency_name,
            referral_type=ref.referral_type,
            referral_summary=ref.referral_summary,
            referral_contact_name=ref.referral_contact_name,
            submitted_by_user_id=ref.submitted_by_user_id,
            submitted_at=ref.submitted_at,
        )

    async def record_referral_outcome(
        self,
        investigation_id: str,
        referral_id: str,
        body: RecordReferralOutcomeIn,
        *,
        actor_user_id: str,
    ) -> LawEnforcementReferralOut:
        inv = await self._get_inv(investigation_id)
        ref = (await self.db.execute(
            select(LawEnforcementReferral).where(
                LawEnforcementReferral.referral_id == referral_id,
                LawEnforcementReferral.investigation_id == investigation_id,
            )
        )).scalar_one_or_none()
        if ref is None:
            raise HTTPException(status_code=404, detail="Referral not found")
        if ref.referral_outcome is not None:
            raise HTTPException(
                status_code=409, detail="Outcome already recorded",
            )

        now = datetime.utcnow().isoformat()
        ref.response_received_date = body.response_received_date
        ref.referral_outcome = body.referral_outcome
        ref.outcome_notes = body.outcome_notes
        ref.closed_at = now

        # If all referrals on this investigation are now closed (PURSUED or
        # DECLINED), release the LE hold.
        all_refs = (await self.db.execute(
            select(LawEnforcementReferral).where(
                LawEnforcementReferral.investigation_id == investigation_id
            )
        )).scalars().all()
        if all(r.referral_outcome is not None for r in all_refs):
            inv.law_enforcement_hold = False
            inv.updated_at = now
            cases = await self._cases_for(investigation_id)
            for c in cases:
                c.law_enforcement_hold = False
                c.updated_at = now
            _audit(
                self.db,
                case_id=None,
                actor_user_id=actor_user_id,
                action="LAW_ENFORCEMENT_HOLD_RELEASED",
                meta={"investigation_id": investigation_id},
            )

        await self.db.commit()
        return LawEnforcementReferralOut(
            referral_id=ref.referral_id,
            investigation_id=ref.investigation_id,
            referral_date=ref.referral_date,
            agency_name=ref.agency_name,
            referral_type=ref.referral_type,
            referral_summary=ref.referral_summary,
            referral_contact_name=ref.referral_contact_name,
            submitted_by_user_id=ref.submitted_by_user_id,
            submitted_at=ref.submitted_at,
            response_received_date=ref.response_received_date,
            referral_outcome=ref.referral_outcome,
            outcome_notes=ref.outcome_notes,
            closed_at=ref.closed_at,
        )

    # ── UC-SIU-05: close investigation ──────────────────────────────────

    async def close_investigation(
        self,
        investigation_id: str,
        body: CloseInvestigationIn,
        *,
        actor_user_id: str,
    ) -> InvestigationOut:
        inv = await self._get_inv(investigation_id)
        if inv.status == "CLOSED":
            raise HTTPException(status_code=409, detail="Already closed")
        if inv.law_enforcement_hold:
            raise HTTPException(
                status_code=409,
                detail="Law enforcement referral must be closed before "
                       "investigation can be closed.",
            )

        now = datetime.utcnow().isoformat()
        inv.outcome = body.outcome
        inv.closure_notes = body.closure_notes
        inv.status = "CLOSED"
        inv.closed_at = now
        inv.closed_by_user_id = actor_user_id
        inv.updated_at = now

        # Release case freeze + LE hold + route back per outcome
        cases = await self._cases_for(investigation_id)
        new_case_status = {
            "FRAUD_CONFIRMED":              "approved",       # back to PI for recovery
            "NO_FRAUD_FOUND":               "in_review",      # back to analyst
            "INSUFFICIENT_EVIDENCE":        "in_review",
            "SUBROGATION_RECOVERY_INITIATED": "reconciling",  # third-party recovery path
            "CASE_CLOSED_NO_ACTION":        "closed_by_siu",  # terminal SIU close
        }.get(body.outcome, "in_review")

        for c in cases:
            c.siu_frozen = False
            c.law_enforcement_hold = False
            c.siu_investigation_id = None
            _audit(
                self.db,
                case_id=c.case_id,
                actor_user_id=actor_user_id,
                action="SIU_INVESTIGATION_CLOSED",
                from_state=c.status,
                to_state=new_case_status,
                reason=f"outcome={body.outcome}",
                meta={
                    "investigation_id": investigation_id,
                    "outcome": body.outcome,
                    "closure_notes": body.closure_notes[:200],
                },
            )
            c.status = new_case_status
            c.updated_at = now

        await self.db.commit()
        return await self.get_investigation(investigation_id)

    # ── UC-SIU-06: JSON export ──────────────────────────────────────────

    async def generate_export(
        self,
        investigation_id: str,
        *,
        actor_user_id: Optional[str],
        delivery_destination: Optional[str] = None,
    ) -> SIUExportPackageOut:
        inv = await self._get_inv(investigation_id)
        cases = await self._cases_for(investigation_id)
        notes = (await self.db.execute(
            select(InvestigationNote)
            .where(InvestigationNote.investigation_id == investigation_id)
            .order_by(InvestigationNote.created_at)
        )).scalars().all()
        refs = (await self.db.execute(
            select(LawEnforcementReferral)
            .where(LawEnforcementReferral.investigation_id == investigation_id)
            .order_by(LawEnforcementReferral.submitted_at)
        )).scalars().all()

        # Frozen claim snapshots + findings per linked case
        case_blocks = []
        for c in cases:
            claim = (await self.db.execute(
                select(Claim).where(Claim.claim_id == c.claim_id)
            )).scalar_one_or_none()
            findings = (await self.db.execute(
                select(Finding).where(Finding.claim_id == c.claim_id)
            )).scalars().all()
            case_blocks.append({
                "case_id": c.case_id,
                "case_number": c.case_number,
                "case_status_at_export": c.status,
                "siu_frozen": c.siu_frozen,
                "law_enforcement_hold": c.law_enforcement_hold,
                "claim_json": json.loads(claim.raw_claim_json) if claim and claim.raw_claim_json else {},
                "findings": [
                    {
                        "finding_id": f.finding_id,
                        "detector_id": f.detector_id,
                        "severity": f.severity,
                        "title": f.title,
                        "rationale": f.rationale,
                        "evidence": json.loads(f.evidence) if f.evidence else {},
                        "fired_at": f.fired_at,
                    } for f in findings
                ],
            })

        # Determine next version number
        prev_pkgs = (await self.db.execute(
            select(SIUExportPackage)
            .where(SIUExportPackage.investigation_id == investigation_id)
        )).scalars().all()
        next_version = (max((p.version for p in prev_pkgs), default=0) + 1)

        now = datetime.utcnow().isoformat()
        package = {
            "package_metadata": {
                "payer_id": "OPA-DEMO",
                "investigation_id": investigation_id,
                "export_timestamp": now,
                "schema_version": "1.0",
                "version": next_version,
            },
            "investigation": {
                "investigation_id": inv.investigation_id,
                "investigation_type": inv.investigation_type,
                "status": inv.status,
                "outcome": inv.outcome,
                "escalation_source": inv.escalation_source,
                "escalation_reason": inv.escalation_reason,
                "escalated_by_user_id": inv.escalated_by_user_id,
                "escalated_at": inv.escalated_at,
                "investigator_assigned_user_id": inv.investigator_assigned_user_id,
                "opened_at": inv.opened_at,
                "closed_at": inv.closed_at,
                "siu_mode": inv.siu_mode,
                "law_enforcement_hold": inv.law_enforcement_hold,
            },
            "cases": case_blocks,
            "investigation_notes": [
                {
                    "note_id": n.note_id,
                    "note_date": n.note_date,
                    "note_type": n.note_type,
                    "body": n.body,
                    "is_confidential": n.is_confidential,
                    "author_user_id": n.author_user_id,
                    "created_at": n.created_at,
                } for n in notes
            ],
            "law_enforcement_referrals": [
                {
                    "referral_id": r.referral_id,
                    "referral_date": r.referral_date,
                    "agency_name": r.agency_name,
                    "referral_type": r.referral_type,
                    "referral_summary": r.referral_summary,
                    "referral_contact_name": r.referral_contact_name,
                    "submitted_by_user_id": r.submitted_by_user_id,
                    "submitted_at": r.submitted_at,
                    "response_received_date": r.response_received_date,
                    "referral_outcome": r.referral_outcome,
                    "closed_at": r.closed_at,
                } for r in refs
            ],
        }
        package_json = json.dumps(package, separators=(",", ":"), sort_keys=True)
        digest = hashlib.sha256(package_json.encode("utf-8")).hexdigest()

        row = SIUExportPackage(
            package_id=str(uuid.uuid4()),
            investigation_id=investigation_id,
            version=next_version,
            package_json=package_json,
            integrity_hash=digest,
            generated_at=now,
            generated_by_user_id=actor_user_id,
            delivery_status="pending",
            delivery_destination=delivery_destination,
            delivery_attempts=0,
        )
        self.db.add(row)

        _audit(
            self.db,
            case_id=None,
            actor_user_id=actor_user_id or "system",
            action="SIU_JSON_EXPORT_GENERATED",
            meta={
                "investigation_id": investigation_id,
                "version": next_version,
                "hash": digest,
                "destination": delivery_destination,
            },
        )
        await self.db.commit()

        return self._package_to_out(row)

    # ── Reads ────────────────────────────────────────────────────────────

    async def get_investigation(
        self, investigation_id: str, *, include_confidential: bool = True,
    ) -> InvestigationOut:
        inv = await self._get_inv(investigation_id)
        case_rows = await self._cases_for(investigation_id)
        case_summaries = [await _case_to_summary(self.db, c) for c in case_rows]

        notes_res = await self.db.execute(
            select(InvestigationNote)
            .where(InvestigationNote.investigation_id == investigation_id)
            .order_by(InvestigationNote.created_at)
        )
        notes: List[InvestigationNoteOut] = []
        for n in notes_res.scalars().all():
            if n.is_confidential and not include_confidential:
                continue
            notes.append(InvestigationNoteOut(
                note_id=n.note_id,
                investigation_id=n.investigation_id,
                note_date=n.note_date,
                note_type=n.note_type,
                body=n.body,
                is_confidential=n.is_confidential,
                author_user_id=n.author_user_id,
                author_name=await _user_name(self.db, n.author_user_id),
                created_at=n.created_at,
            ))

        refs_res = await self.db.execute(
            select(LawEnforcementReferral)
            .where(LawEnforcementReferral.investigation_id == investigation_id)
            .order_by(LawEnforcementReferral.submitted_at)
        )
        refs = [
            LawEnforcementReferralOut(
                referral_id=r.referral_id,
                investigation_id=r.investigation_id,
                referral_date=r.referral_date,
                agency_name=r.agency_name,
                referral_type=r.referral_type,
                referral_summary=r.referral_summary,
                referral_contact_name=r.referral_contact_name,
                submitted_by_user_id=r.submitted_by_user_id,
                submitted_at=r.submitted_at,
                response_received_date=r.response_received_date,
                referral_outcome=r.referral_outcome,
                outcome_notes=r.outcome_notes,
                closed_at=r.closed_at,
            )
            for r in refs_res.scalars().all()
        ]

        pkgs_res = await self.db.execute(
            select(SIUExportPackage)
            .where(SIUExportPackage.investigation_id == investigation_id)
            .order_by(SIUExportPackage.version.desc())
        )
        exports = [self._package_to_out(p) for p in pkgs_res.scalars().all()]

        return InvestigationOut(
            investigation_id=inv.investigation_id,
            investigation_type=inv.investigation_type,
            status=inv.status,
            outcome=inv.outcome,
            closure_notes=inv.closure_notes,
            escalation_source=inv.escalation_source,
            escalation_reason=inv.escalation_reason,
            escalated_by_user_id=inv.escalated_by_user_id,
            escalated_at=inv.escalated_at,
            investigator_assigned_user_id=inv.investigator_assigned_user_id,
            investigator_assigned_name=await _user_name(self.db, inv.investigator_assigned_user_id),
            opened_at=inv.opened_at,
            closed_at=inv.closed_at,
            closed_by_user_id=inv.closed_by_user_id,
            law_enforcement_hold=inv.law_enforcement_hold,
            siu_mode=inv.siu_mode,
            created_at=inv.created_at,
            updated_at=inv.updated_at,
            cases=case_summaries,
            notes=notes,
            referrals=refs,
            exports=exports,
        )

    async def list_queue(
        self, *, include_closed: bool = False,
    ) -> List[SIUQueueRow]:
        stmt = select(SIUInvestigation).order_by(SIUInvestigation.escalated_at.desc())
        if not include_closed:
            stmt = stmt.where(SIUInvestigation.status != "CLOSED")
        invs = (await self.db.execute(stmt)).scalars().all()

        rows: List[SIUQueueRow] = []
        for inv in invs:
            cases = await self._cases_for(inv.investigation_id)
            providers: List[str] = []
            dets: List[str] = []
            total_at_risk = 0.0
            for c in cases:
                claim = (await self.db.execute(
                    select(Claim).where(Claim.claim_id == c.claim_id)
                )).scalar_one_or_none()
                if claim:
                    org = (await self.db.execute(
                        select(ProviderOrg).where(
                            ProviderOrg.provider_org_id == claim.provider_org_id
                        )
                    )).scalar_one_or_none()
                    if org and org.name not in providers:
                        providers.append(org.name)
                f_res = await self.db.execute(
                    select(Finding.detector_id).where(Finding.claim_id == c.claim_id)
                )
                for r in f_res.all():
                    if r[0] and r[0] not in dets:
                        dets.append(r[0])
                if c.total_overpayment_amount:
                    total_at_risk += c.total_overpayment_amount

            rows.append(SIUQueueRow(
                investigation_id=inv.investigation_id,
                investigation_type=inv.investigation_type,
                status=inv.status,
                escalation_source=inv.escalation_source,
                escalation_reason=inv.escalation_reason,
                escalated_at=inv.escalated_at,
                investigator_assigned_user_id=inv.investigator_assigned_user_id,
                investigator_assigned_name=await _user_name(
                    self.db, inv.investigator_assigned_user_id
                ),
                law_enforcement_hold=inv.law_enforcement_hold,
                siu_mode=inv.siu_mode,
                case_count=len(cases),
                provider_org_names=providers,
                detector_ids=sorted(dets),
                total_at_risk=round(total_at_risk, 2) if total_at_risk else None,
            ))
        return rows

    async def get_export_payload(
        self, investigation_id: str, package_id: str
    ) -> tuple[str, str]:
        """Returns (package_json, integrity_hash). 404 if missing."""
        pkg = (await self.db.execute(
            select(SIUExportPackage).where(
                SIUExportPackage.investigation_id == investigation_id,
                SIUExportPackage.package_id == package_id,
            )
        )).scalar_one_or_none()
        if pkg is None:
            raise HTTPException(status_code=404, detail="Package not found")
        return pkg.package_json, pkg.integrity_hash

    # ── Private helpers ─────────────────────────────────────────────────

    async def _get_inv(self, investigation_id: str) -> SIUInvestigation:
        res = await self.db.execute(
            select(SIUInvestigation).where(
                SIUInvestigation.investigation_id == investigation_id
            )
        )
        inv = res.scalar_one_or_none()
        if inv is None:
            raise HTTPException(status_code=404, detail="Investigation not found")
        return inv

    async def _cases_for(self, investigation_id: str) -> Sequence[OpaCase]:
        link_res = await self.db.execute(
            select(InvestigationCase.case_id).where(
                InvestigationCase.investigation_id == investigation_id
            )
        )
        case_ids = [r[0] for r in link_res.all()]
        if not case_ids:
            return []
        case_res = await self.db.execute(
            select(OpaCase).where(OpaCase.case_id.in_(case_ids))
        )
        return case_res.scalars().all()

    def _package_to_out(self, row: SIUExportPackage) -> SIUExportPackageOut:
        return SIUExportPackageOut(
            package_id=row.package_id,
            investigation_id=row.investigation_id,
            version=row.version,
            integrity_hash=row.integrity_hash,
            generated_at=row.generated_at,
            generated_by_user_id=row.generated_by_user_id,
            delivery_status=row.delivery_status,
            delivery_destination=row.delivery_destination,
            delivery_attempts=row.delivery_attempts,
            last_attempt_at=row.last_attempt_at,
            last_error=row.last_error,
        )
