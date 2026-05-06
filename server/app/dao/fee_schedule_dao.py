from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .base_dao import BaseDAO
from ..models.reference import FeeSchedule


class FeeScheduleDAO(BaseDAO[FeeSchedule]):
    model = FeeSchedule

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_allowed_amount(
        self, cpt_code: str, lob: str, service_date: str
    ) -> Optional[float]:
        stmt = (
            select(FeeSchedule)
            .where(
                and_(
                    FeeSchedule.cpt_code == cpt_code,
                    FeeSchedule.lob == lob,
                    FeeSchedule.effective_date <= service_date,
                    FeeSchedule.termination_date >= service_date,
                )
            )
            .order_by(FeeSchedule.effective_date.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        fee = result.scalar_one_or_none()
        return fee.base_rate if fee else None

    async def get_by_lob(self, lob: str) -> List[FeeSchedule]:
        stmt = select(FeeSchedule).where(FeeSchedule.lob == lob)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
