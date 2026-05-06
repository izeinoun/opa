from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_dao import BaseDAO
from ..models.workflow import OpaUser


class UserDAO(BaseDAO[OpaUser]):
    model = OpaUser

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_username(self, username: str) -> Optional[OpaUser]:
        stmt = select(OpaUser).where(OpaUser.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_role(self, role: str) -> List[OpaUser]:
        stmt = select(OpaUser).where(OpaUser.role == role)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_analysts(self) -> List[OpaUser]:
        stmt = select(OpaUser).where(OpaUser.role == "analyst", OpaUser.is_active == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
