from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.reference import BillTypeCode, RevenueCode


class BillRevenueDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def bill_type_exists(self, code: str) -> bool:
        result = await self.session.execute(
            select(BillTypeCode.bill_type_code_id).where(
                BillTypeCode.code == code,
                BillTypeCode.is_active.is_(True),
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def revenue_code_exists(self, code: str) -> bool:
        result = await self.session.execute(
            select(RevenueCode.revenue_code_id).where(
                RevenueCode.code == code,
                RevenueCode.is_active.is_(True),
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None
