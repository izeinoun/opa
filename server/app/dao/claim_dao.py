from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_dao import BaseDAO
from ..models.claims import Claim


class ClaimDAO(BaseDAO[Claim]):
    model = Claim

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_with_details(self, claim_id: str) -> Optional[Claim]:
        stmt = select(Claim).where(Claim.claim_id == claim_id)
        result = await self.session.execute(stmt)
        claim = result.scalar_one_or_none()
        if claim is None:
            return None
        # Relationships are lazy="selectin" on the model — force load
        _ = claim.lines
        _ = claim.member
        _ = claim.provider_org
        return claim

    async def get_by_icn(self, icn: str) -> Optional[Claim]:
        stmt = select(Claim).where(Claim.icn == icn)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_lob(self, lob: str, skip: int = 0, limit: int = 100) -> List[Claim]:
        stmt = select(Claim).where(Claim.lob == lob).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
