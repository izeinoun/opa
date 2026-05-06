from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..dao.audit_log_dao import AuditLogDAO
from ..schemas.case_schemas import AuditLogRead
from ..services.case_service import _serialize_audit


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit_dao = AuditLogDAO(session)

    async def get_case_timeline(self, case_id: str) -> List[AuditLogRead]:
        logs = await self.audit_dao.get_by_case(case_id)
        return [_serialize_audit(log) for log in logs]

    async def log_action(
        self,
        case_id: str,
        user_id: Optional[str],
        action: str,
        from_status: Optional[str],
        to_status: Optional[str],
        reason: Optional[str],
    ) -> AuditLogRead:
        log = await self.audit_dao.create_entry(
            case_id=case_id,
            actor_user_id=user_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
        )
        return _serialize_audit(log)
