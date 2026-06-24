from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.reference import ProviderDeliveryPlaybook


class PlaybookDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_org(self, provider_org_id: str) -> Optional[ProviderDeliveryPlaybook]:
        stmt = select(ProviderDeliveryPlaybook).where(
            ProviderDeliveryPlaybook.provider_org_id == provider_org_id
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def upsert(
        self,
        provider_org_id: str,
        data: dict,
        user_id: str,
    ) -> ProviderDeliveryPlaybook:
        playbook = await self.get_by_org(provider_org_id)

        if playbook:
            for key, value in data.items():
                if key not in ("playbook_id", "provider_org_id", "created_at", "created_by_id"):
                    setattr(playbook, key, value)
            playbook.updated_by_id = user_id
            self.session.add(playbook)
        else:
            playbook = ProviderDeliveryPlaybook(
                provider_org_id=provider_org_id,
                created_by_id=user_id,
                updated_by_id=user_id,
                **data,
            )
            self.session.add(playbook)

        await self.session.flush()
        return playbook
