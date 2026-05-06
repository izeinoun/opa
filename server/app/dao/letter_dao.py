import json
from typing import List, Optional
from datetime import datetime, date, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.workflow import LetterTemplate, ProviderNotice, OpaCase


class LetterDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_template_by_id(self, template_id: str) -> Optional[LetterTemplate]:
        stmt = select(LetterTemplate).where(LetterTemplate.template_id == template_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_templates(self, lob: Optional[str] = None) -> List[LetterTemplate]:
        conditions = [LetterTemplate.is_active == True]
        if lob:
            conditions.append(LetterTemplate.lob == lob)
        stmt = select(LetterTemplate).where(and_(*conditions))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_case_by_sequence(self, case_sequence: int) -> Optional[OpaCase]:
        stmt = select(OpaCase).where(OpaCase.case_sequence == case_sequence)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_notice(
        self,
        case: OpaCase,
        template: LetterTemplate,
        amount_demanded: float,
        delivery_method: str,
        response_due: Optional[str],
        rendered_html: str,
    ) -> ProviderNotice:
        response_due_str = response_due or (date.today() + timedelta(days=30)).isoformat()
        content = json.dumps({
            "amount_demanded": amount_demanded,
            "delivery_method": delivery_method,
            "response_due": response_due_str,
            "html": rendered_html,
        })
        now = datetime.utcnow().isoformat()
        notice = ProviderNotice(
            case_id=case.case_id,
            template_id=template.template_id,
            lob=case.lob,
            generated_at=now,
            letter_content=content,
            status="sent",
            sent_at=now,
            created_at=now,
            updated_at=now,
        )
        self.session.add(notice)
        await self.session.flush()
        await self.session.refresh(notice)
        return notice

    async def get_notices_by_case_id(self, case_id: str) -> List[ProviderNotice]:
        stmt = (
            select(ProviderNotice)
            .where(ProviderNotice.case_id == case_id)
            .order_by(ProviderNotice.generated_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
