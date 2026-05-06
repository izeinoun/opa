from typing import List, Optional
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_dao import BaseDAO
from ..models.workflow import AuditLog


class AuditLogDAO(BaseDAO[AuditLog]):
    model = AuditLog

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_case(self, case_id: str, skip: int = 0, limit: int = 100) -> List[AuditLog]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.case_id == case_id)
            .order_by(AuditLog.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_entry(
        self,
        case_id: str,
        actor_user_id: Optional[str],
        action: str,
        from_status: Optional[str] = None,
        to_status: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> AuditLog:
        if actor_user_id is None:
            from sqlalchemy import text
            result = await self.session.execute(
                text("SELECT user_id FROM opa_users WHERE username = 'system.bot' LIMIT 1")
            )
            row = result.fetchone()
            actor_user_id = row[0] if row else "system"

        log = AuditLog(
            case_id=case_id,
            actor_user_id=actor_user_id,
            action=action,
            from_state=from_status,
            to_state=to_status,
            reason=reason,
            meta_json="{}",
            created_at=datetime.utcnow().isoformat(),
        )
        self.session.add(log)
        await self.session.flush()
        await self.session.refresh(log)
        return log
