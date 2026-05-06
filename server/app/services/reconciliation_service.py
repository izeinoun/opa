from typing import Optional
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession

from ..dao.case_dao import CaseDAO
from ..dao.audit_log_dao import AuditLogDAO
from ..models.claims import ERATransaction
from ..schemas.case_schemas import CaseDetail
from .case_service import CaseService


class ReconciliationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.case_dao = CaseDAO(session)
        self.audit_dao = AuditLogDAO(session)
        self.case_service = CaseService(session)

    async def process_era(
        self,
        case_id: int,
        era_data: dict,
        user_id: Optional[int],
    ) -> CaseDetail:
        case = await self.case_dao.get_by_id(case_id)
        if case is None:
            raise ValueError(f"Case {case_id} not found")

        # Create ERA transaction
        era_txn = ERATransaction(
            claim_id=case.claim_id,
            era_number=era_data.get("era_number", ""),
            payment_date=era_data.get("payment_date", date.today()),
            payment_amount=era_data.get("payment_amount", 0.0),
            check_number=era_data.get("check_number"),
            payer_id=era_data.get("payer_id", ""),
            created_at=datetime.utcnow(),
        )
        self.session.add(era_txn)
        await self.session.flush()

        # Transition case to reconciling
        from_status = case.status
        case.status = "reconciling"
        await self.session.flush()

        await self.audit_dao.create_entry(
            case_id=case_id,
            user_id=user_id,
            action="ERA_PROCESSED",
            from_status=from_status,
            to_status="reconciling",
            notes=f"ERA {era_txn.era_number} processed, amount: {era_txn.payment_amount}",
        )

        return await self.case_service.get_case_detail(case_id)

    async def write_off(
        self,
        case_id: int,
        reason: str,
        user_id: Optional[int],
    ) -> CaseDetail:
        case = await self.case_dao.get_by_id(case_id)
        if case is None:
            raise ValueError(f"Case {case_id} not found")

        from_status = case.status
        case.status = "closed_written_off"
        case.is_active = False
        case.closed_at = datetime.utcnow()
        case.closure_reason = reason
        await self.session.flush()

        await self.audit_dao.create_entry(
            case_id=case_id,
            user_id=user_id,
            action="WRITTEN_OFF",
            from_status=from_status,
            to_status="closed_written_off",
            notes=reason,
        )

        return await self.case_service.get_case_detail(case_id)

    async def mark_no_overpayment(
        self,
        case_id: int,
        reason: str,
        user_id: Optional[int],
    ) -> CaseDetail:
        case = await self.case_dao.get_by_id(case_id)
        if case is None:
            raise ValueError(f"Case {case_id} not found")

        from_status = case.status
        case.status = "closed_no_overpayment"
        case.is_active = False
        case.closed_at = datetime.utcnow()
        case.closure_reason = reason
        await self.session.flush()

        await self.audit_dao.create_entry(
            case_id=case_id,
            user_id=user_id,
            action="NO_OVERPAYMENT",
            from_status=from_status,
            to_status="closed_no_overpayment",
            notes=reason,
        )

        return await self.case_service.get_case_detail(case_id)
