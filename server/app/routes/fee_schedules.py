"""GET /api/fee-schedules — provider orgs with fee schedules and contract limitations."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from ..middleware.auth import require_app
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.reference import ContractLimitation, CptCode, FeeSchedule, ProviderOrg

router = APIRouter(prefix="/api/fee-schedules", tags=["fee-schedules"], dependencies=[Depends(require_app("payguard"))])


class FeeScheduleRow(BaseModel):
    fee_schedule_id: str
    lob: str
    cpt_code: str
    cpt_description: Optional[str]
    effective_date: str
    termination_date: Optional[str]
    base_rate: float
    rate_basis: str
    modifier_applicable: Optional[str]


class ContractLimitationRow(BaseModel):
    limitation_id: str
    cpt_code: str
    limitation_type: str
    limitation_value: str
    effective_date: str
    description: str


class ProviderOrgSummary(BaseModel):
    provider_org_id: str
    name: str
    npi: str
    org_type: str
    schedule_count: int
    lobs: List[str]


class ProviderOrgDetail(BaseModel):
    provider_org_id: str
    name: str
    npi: str
    tin: str
    org_type: str
    fee_schedules: List[FeeScheduleRow]
    contract_limitations: List[ContractLimitationRow]


@router.get("", response_model=List[ProviderOrgSummary])
async def list_orgs(db: AsyncSession = Depends(get_db)) -> List[ProviderOrgSummary]:
    orgs_res = await db.execute(
        select(ProviderOrg).order_by(ProviderOrg.name)
    )
    orgs = orgs_res.scalars().all()

    result = []
    for org in orgs:
        schedules = org.fee_schedules or []
        if not schedules:
            continue
        lobs = sorted({s.lob for s in schedules})
        result.append(ProviderOrgSummary(
            provider_org_id=org.provider_org_id,
            name=org.name,
            npi=org.npi,
            org_type=org.org_type,
            schedule_count=len(schedules),
            lobs=lobs,
        ))
    return result


@router.get("/{provider_org_id}", response_model=ProviderOrgDetail)
async def get_org_schedules(
    provider_org_id: str,
    db: AsyncSession = Depends(get_db),
) -> ProviderOrgDetail:
    org_res = await db.execute(
        select(ProviderOrg).where(ProviderOrg.provider_org_id == provider_org_id)
    )
    org = org_res.scalar_one()

    cpt_res = await db.execute(select(CptCode))
    cpt_map = {c.code: c.description for c in cpt_res.scalars().all()}

    lim_res = await db.execute(
        select(ContractLimitation).where(ContractLimitation.provider_org_id == provider_org_id)
    )
    limitations = lim_res.scalars().all()

    schedules = sorted(org.fee_schedules or [], key=lambda s: (s.cpt_code, s.lob))

    return ProviderOrgDetail(
        provider_org_id=org.provider_org_id,
        name=org.name,
        npi=org.npi,
        tin=org.tin,
        org_type=org.org_type,
        fee_schedules=[
            FeeScheduleRow(
                fee_schedule_id=s.fee_schedule_id,
                lob=s.lob,
                cpt_code=s.cpt_code,
                cpt_description=cpt_map.get(s.cpt_code),
                effective_date=s.effective_date,
                termination_date=s.termination_date,
                base_rate=s.base_rate,
                rate_basis=s.rate_basis,
                modifier_applicable=s.modifier_applicable,
            )
            for s in schedules
        ],
        contract_limitations=[
            ContractLimitationRow(
                limitation_id=l.limitation_id,
                cpt_code=l.cpt_code,
                limitation_type=l.limitation_type,
                limitation_value=l.limitation_value,
                effective_date=l.effective_date,
                description=l.description,
            )
            for l in limitations
        ],
    )
