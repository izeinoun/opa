from typing import Optional, List, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from ..dao.letter_dao import LetterDAO
from ..dao.case_dao import CaseDAO
from ..dao.audit_log_dao import AuditLogDAO
from ..schemas.letter_schemas import (
    LetterTemplateRead,
    LetterTemplateDetail,
    RecoveryNoticeCreate,
    RecoveryNoticeRead,
    RenderedLetter,
)
from ..utils.letter_renderer import render_template
from ..services.case_service import _serialize_notice


def _tmpl_to_read(t, detail: bool = False):
    try:
        version_int = int(t.version.split(".")[0])
    except Exception:
        version_int = 1
    base = LetterTemplateRead(
        id=t.template_id,
        code=t.template_id,
        name=t.template_name,
        template_type="initial_demand",
        lob=t.lob,
        version=version_int,
        is_active=t.is_active,
        created_at=t.created_at,
        regulatory_reference=t.regulatory_reference or "",
    )
    if detail:
        return LetterTemplateDetail(**base.model_dump(), content_html=t.template_content)
    return base


class LetterService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.letter_dao = LetterDAO(session)

    async def get_templates(self, lob: Optional[str] = None) -> List[LetterTemplateRead]:
        templates = await self.letter_dao.get_active_templates(lob)
        return [_tmpl_to_read(t) for t in templates]

    async def get_template_detail(self, template_id: str) -> Optional[LetterTemplateDetail]:
        t = await self.letter_dao.get_template_by_id(template_id)
        if t is None:
            return None
        return _tmpl_to_read(t, detail=True)

    async def render_letter(self, case_sequence: int, template_id: str) -> RenderedLetter:
        case = await self.letter_dao.get_case_by_sequence(case_sequence)
        if case is None:
            raise ValueError(f"Case sequence {case_sequence} not found")

        template = await self.letter_dao.get_template_by_id(template_id)
        if template is None:
            raise ValueError(f"Template '{template_id}' not found")

        claim = case.claim
        provider_name = ""
        provider_npi = ""
        claim_number = ""
        service_date = ""
        member_name = ""
        member_id_str = ""
        cpt_codes = ""

        if claim:
            claim_number = claim.icn
            service_date = claim.service_from_date
            provider_npi = claim.rendering_provider_npi or claim.billing_provider_npi or ""
            if claim.member:
                member_name = f"{claim.member.first_name} {claim.member.last_name}"
                member_id_str = claim.member.member_number
            if claim.provider_org:
                provider_name = claim.provider_org.name
            if claim.lines:
                codes = [ln.cpt_code for ln in claim.lines if ln.cpt_code]
                cpt_codes = ", ".join(dict.fromkeys(codes))

        analyst_name = "OPA Analyst"
        analyst_phone = "1-800-OPA-HEAL"
        if case.assigned_analyst:
            analyst_name = case.assigned_analyst.full_name or case.assigned_analyst.username
            analyst_phone = "1-800-OPA-HEAL"

        recovery_method = (case.recommended_recovery_method or "claim offset").replace("_", " ").title()
        plan_name = "Health Plan"

        variables = {
            "case_number": case.case_number,
            "provider_name": provider_name,
            "provider_npi": provider_npi,
            "claim_number": claim_number,
            "amount_demanded": f"${case.total_overpayment_amount:,.2f}",
            "overpayment_amount": f"${case.total_overpayment_amount:,.2f}",
            "service_date": service_date,
            "deadline": case.deadline_date or "",
            "lob": case.lob,
            "member_name": member_name,
            "member_id": member_id_str,
            "regulatory_reference": template.regulatory_reference or "",
            "plan_name": plan_name,
            "payer_name": plan_name,
            "response_due_date": case.provider_response_due_date or case.deadline_date or "",
            "recovery_method": recovery_method,
            "analyst_name": analyst_name,
            "analyst_phone": analyst_phone,
            "response_address": "OPA Recovery Unit, P.O. Box 1000",
            "contact_phone": analyst_phone,
            "contact_email": "recovery@opa.internal",
            "cpt_codes": cpt_codes,
        }

        html_content = render_template(template.template_content, variables)

        return RenderedLetter(
            case_id=case_sequence,
            template_code=template_id,
            html_content=html_content,
            rendered_at=datetime.utcnow().isoformat(),
        )

    async def send_notice(self, data: RecoveryNoticeCreate) -> RecoveryNoticeRead:
        case = await self.letter_dao.get_case_by_sequence(data.case_id)
        if case is None:
            raise ValueError(f"Case sequence {data.case_id} not found")

        template = await self.letter_dao.get_template_by_id(data.template_id)
        if template is None:
            raise ValueError(f"Template '{data.template_id}' not found")

        rendered = await self.render_letter(data.case_id, data.template_id)

        notice = await self.letter_dao.create_notice(
            case=case,
            template=template,
            amount_demanded=data.amount_demanded,
            delivery_method=data.delivery_method,
            response_due=data.response_due,
            rendered_html=rendered.html_content,
        )

        # If the case isn't yet in notice_sent (typical when sending through the
        # composer modal), advance it now. Skip the auto-generation side-effect
        # since we just created the notice manually.
        if case.status in ("ready_for_notice", "in_review"):
            from ..dao.case_dao import CaseDAO
            await CaseDAO(self.session).transition_status(data.case_id, "notice_sent")
            await self.session.commit()

        return _serialize_notice(notice)

    async def get_notices(self, case_sequence: int, include_content: bool = True) -> List[RecoveryNoticeRead]:
        case = await self.letter_dao.get_case_by_sequence(case_sequence)
        if case is None:
            return []
        notices = await self.letter_dao.get_notices_by_case_id(case.case_id)
        # Latest first
        sorted_n = sorted(notices, key=lambda n: n.generated_at or "", reverse=True)
        return [_serialize_notice(n, include_content=include_content) for n in sorted_n]

    async def auto_generate_for_case(self, case_sequence: int) -> Optional[RecoveryNoticeRead]:
        """Generate a recovery notice using the default template for the case's
        LOB. Idempotent in spirit but not enforced — caller decides when to
        invoke (typically once on transition to notice_sent)."""
        from sqlalchemy import select
        from ..models.workflow import LetterTemplate
        from datetime import timedelta, date

        case = await self.letter_dao.get_case_by_sequence(case_sequence)
        if case is None:
            return None

        # Skip if a notice was already manually composed (e.g. via SendNoticeModal)
        existing = await self.letter_dao.get_notices_by_case_id(case.case_id)
        if existing:
            return None

        res = await self.session.execute(
            select(LetterTemplate)
            .where(LetterTemplate.lob == case.lob)
            .where(LetterTemplate.is_active == True)  # noqa: E712
            .order_by(LetterTemplate.version.desc())
            .limit(1)
        )
        template = res.scalar_one_or_none()
        if template is None:
            return None  # no template for this LOB; skip silently

        response_due = (date.today() + timedelta(days=30)).isoformat()
        data = RecoveryNoticeCreate(
            case_id=case_sequence,
            template_id=template.template_id,
            amount_demanded=case.total_overpayment_amount or 0.0,
            delivery_method="mail",
            response_due=response_due,
        )
        return await self.send_notice(data)

    async def generate_notice_for_case(
        self,
        case_id: str,
        user_id: str,
        content_override: Optional[str] = None,
    ) -> dict[str, Any]:
        """Generate a provider notice for a case (idempotent).

        Steps:
        1. Fetch case (sequence or UUID) — validate exists & not in terminal state
        2. Check if notice exists → return existing (with message: "Notice already exists")
        3. If no notice:
           a. Fetch case letter OR render from template
           b. If content_override: use override instead
           c. Create ProviderNotice row
           d. Transition case: current_status → "notice_sent"
        4. Audit log: action="generate_provider_notice", user_id=user_id
        5. Return: {notice_id, case_id, status, message, content_preview}
        """
        # Fetch case (try as sequence number first, then as UUID)
        case = None
        try:
            seq_num = int(case_id)
            case = await self.letter_dao.get_case_by_sequence(seq_num)
        except ValueError:
            # Not an integer, try as UUID
            case_dao = CaseDAO(self.session)
            case = await case_dao.get_by_id(case_id)

        if not case:
            raise ValueError(f"Case {case_id} not found")

        # Check if case is in terminal state
        if case.status.startswith("closed_"):
            raise ValueError(f"Cannot generate notice for closed case (status: {case.status})")

        # Check if notice already exists
        existing_notices = await self.letter_dao.get_notices_by_case_id(case.case_id)
        if existing_notices:
            existing = existing_notices[0]  # Latest first
            return {
                "notice_id": existing.notice_id,
                "case_id": case.case_id,
                "case_number": case.case_number,
                "status": case.status,
                "message": "Notice already exists",
                "content_preview": (existing.letter_content or "")[:200] if existing.letter_content else None,
            }

        # Generate new notice via auto-generation (if no override)
        content_overridden = False
        if not content_override:
            # Auto-generate a notice using the default template
            # This creates the notice AND transitions the case
            auto_result = await self.auto_generate_for_case(case.case_sequence)
            if not auto_result:
                raise ValueError("No letter template found for this case's LOB")
            # Fetch the notice that was just created
            notices = await self.letter_dao.get_notices_by_case_id(case.case_id)
            if notices:
                notice = notices[0]
                return {
                    "notice_id": notice.notice_id,
                    "case_id": case.case_id,
                    "case_number": case.case_number,
                    "status": "notice_sent",
                    "message": "Notice generated successfully",
                    "content_overridden": False,
                    "content_preview": (notice.letter_content or "")[:200] if notice.letter_content else None,
                }
            else:
                raise ValueError("Notice generation failed - not found after creation")
        else:
            # Content override provided - create custom notice
            content_overridden = True
            response_due = (datetime.today() + __import__("datetime").timedelta(days=30)).date().isoformat()
            notice_data = RecoveryNoticeCreate(
                case_id=case.case_sequence,
                template_id="custom_override",
                amount_demanded=case.total_overpayment_amount or 0.0,
                delivery_method="email",
                response_due=response_due,
            )
            # Send notice with custom content
            notice_result = await self.send_notice(notice_data)

            # Transition case to notice_sent
            case_dao = CaseDAO(self.session)
            await case_dao.transition_status(case.case_id, "notice_sent", reason="Notice generated (content overridden)")

            # Audit log
            audit_dao = AuditLogDAO(self.session)
            await audit_dao.create_entry(
                case_id=case.case_id,
                actor_user_id=user_id,
                action="generate_provider_notice",
                from_status=case.status,
                to_status="notice_sent",
                reason="Provider notice generated (content overridden)",
            )

            await self.session.commit()

            return {
                "notice_id": notice_result.notice_id,
                "case_id": case.case_id,
                "case_number": case.case_number,
                "status": "notice_sent",
                "message": "Notice generated successfully with custom content",
                "content_overridden": True,
                "content_preview": content_override[:200] if content_override else None,
            }
