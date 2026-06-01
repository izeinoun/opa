"""Data access for DocumentTemplate — generic LLM document templates.

All reads are scoped by the `app` discriminator so PayGuard and ClaimGuard
never see each other's templates even though they share one table.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.workflow import DocumentTemplate


class DocumentTemplateDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self, template_id: str, app: Optional[str] = None
    ) -> Optional[DocumentTemplate]:
        conditions = [DocumentTemplate.template_id == template_id]
        if app is not None:
            conditions.append(DocumentTemplate.app == app)
        result = await self.session.execute(
            select(DocumentTemplate).where(and_(*conditions))
        )
        return result.scalar_one_or_none()

    async def list_for_app(
        self, app: str, active_only: bool = True
    ) -> List[DocumentTemplate]:
        conditions = [DocumentTemplate.app == app]
        if active_only:
            conditions.append(DocumentTemplate.is_active == True)  # noqa: E712
        result = await self.session.execute(
            select(DocumentTemplate)
            .where(and_(*conditions))
            .order_by(DocumentTemplate.name)
        )
        return list(result.scalars().all())

    async def create(self, template: DocumentTemplate) -> DocumentTemplate:
        self.session.add(template)
        await self.session.flush()
        await self.session.refresh(template)
        return template

    async def delete(self, template: DocumentTemplate) -> None:
        await self.session.delete(template)
        await self.session.flush()
