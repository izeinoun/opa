from typing import List, Optional, Tuple
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .base_dao import BaseDAO
from ..models.reference import ExcludedProvider


class ExcludedProviderDAO(BaseDAO[ExcludedProvider]):
    model = ExcludedProvider

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def search(
        self, query: Optional[str], skip: int = 0, limit: int = 50
    ) -> Tuple[List[ExcludedProvider], int]:
        """Paginated LEIE browse. Optional case-insensitive match on NPI,
        last/first/business name. Returns (page_rows, total_matching)."""
        conditions = []
        if query:
            like = f"%{query.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(ExcludedProvider.npi).like(like),
                    func.lower(ExcludedProvider.last_name).like(like),
                    func.lower(ExcludedProvider.first_name).like(like),
                    func.lower(ExcludedProvider.business_name).like(like),
                )
            )

        count_stmt = select(func.count()).select_from(ExcludedProvider)
        page_stmt = select(ExcludedProvider)
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
            page_stmt = page_stmt.where(cond)

        total = (await self.session.execute(count_stmt)).scalar_one()
        page_stmt = (
            page_stmt.order_by(
                ExcludedProvider.last_name.asc(),
                ExcludedProvider.business_name.asc(),
            )
            .offset(skip)
            .limit(limit)
        )
        rows = list((await self.session.execute(page_stmt)).scalars().all())
        return rows, total

    async def get_by_npi(self, npi: str) -> Optional[ExcludedProvider]:
        """Return the most recent LEIE exclusion for an NPI, or None.

        Orders by exclusion_date desc so re-excluded NPIs surface the active
        record. Match is exact on the 10-digit NPI — the deterministic key.
        """
        if not npi:
            return None
        stmt = (
            select(ExcludedProvider)
            .where(ExcludedProvider.npi == npi)
            .order_by(ExcludedProvider.exclusion_date.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
