from datetime import date
from typing import Optional, List, Tuple
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .base_dao import BaseDAO
from ..models.workflow import OpaCase
from ..models.reference import Member
from ..schemas.case_schemas import WorklistFilters


class CaseDAO(BaseDAO[OpaCase]):
    model = OpaCase

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_sequence(self, case_sequence: int) -> Optional[OpaCase]:
        result = await self.session.execute(
            select(OpaCase).where(OpaCase.case_sequence == case_sequence)
        )
        return result.scalar_one_or_none()

    async def get_worklist(
        self,
        filters: WorklistFilters,
        skip: int = 0,
        limit: int = 25,
    ) -> Tuple[List[OpaCase], int]:
        stmt = select(OpaCase).join(Member, OpaCase.member_id == Member.member_id, isouter=True)

        conditions = []
        if filters.closed_only:
            conditions.append(OpaCase.status.like("closed_%"))
        elif filters.exclude_closed:
            conditions.append(~OpaCase.status.like("closed_%"))
        if filters.status:
            conditions.append(OpaCase.status == filters.status)
        if filters.priority:
            conditions.append(OpaCase.priority == filters.priority)
        if filters.lob:
            conditions.append(OpaCase.lob == filters.lob)
        if filters.detector_code:
            conditions.append(OpaCase.primary_detector_id == filters.detector_code)
        if filters.group_id:
            conditions.append(OpaCase.case_group_id == filters.group_id)
        if filters.assignee_id:
            if filters.assignee_id == "__unassigned__":
                conditions.append(OpaCase.assigned_analyst_id.is_(None))
            else:
                conditions.append(OpaCase.assigned_analyst_id == filters.assignee_id)
        if filters.mine_or_unassigned_for_user_id:
            conditions.append(or_(
                OpaCase.assigned_analyst_id == filters.mine_or_unassigned_for_user_id,
                OpaCase.assigned_analyst_id.is_(None),
            ))
        if filters.search:
            term = f"%{filters.search}%"
            conditions.append(or_(
                OpaCase.case_number.ilike(term),
                Member.first_name.ilike(term),
                Member.last_name.ilike(term),
                (Member.first_name + " " + Member.last_name).ilike(term),
            ))
        if filters.overdue_only:
            from datetime import timedelta
            cutoff = (date.today() + timedelta(days=5)).isoformat()
            conditions.append(OpaCase.deadline_date <= cutoff)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar_one()

        stmt = stmt.order_by(OpaCase.priority_score.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def get_with_full_details(self, case_sequence: int) -> Optional[OpaCase]:
        result = await self.session.execute(
            select(OpaCase).where(OpaCase.case_sequence == case_sequence)
        )
        return result.scalar_one_or_none()

    async def transition_status(
        self,
        case_sequence: int,
        to_status: str,
    ) -> OpaCase:
        case = await self.get_by_sequence(case_sequence)
        if case is None:
            raise ValueError(f"Case {case_sequence} not found")

        case.status = to_status
        closed_statuses = {
            "closed_recovered", "closed_written_off",
            "closed_overturned", "closed_no_overpayment",
        }
        if to_status in closed_statuses:
            case.is_active = False

        await self.session.flush()
        await self.session.refresh(case)
        return case
