from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_dao import BaseDAO
from ..models.reference import ExcludedProvider


class ExcludedProviderDAO(BaseDAO[ExcludedProvider]):
    model = ExcludedProvider

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

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
