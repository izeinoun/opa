from typing import Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from ..dao.letter_dao import LetterDAO
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
        return _serialize_notice(notice)

    async def get_notices(self, case_sequence: int) -> List[RecoveryNoticeRead]:
        case = await self.letter_dao.get_case_by_sequence(case_sequence)
        if case is None:
            return []
        notices = await self.letter_dao.get_notices_by_case_id(case.case_id)
        return [_serialize_notice(n) for n in notices]
