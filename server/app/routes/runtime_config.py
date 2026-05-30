"""Flat key/value feature-flag endpoints (ported from ClaimGuard's
routers/admin.py /config endpoints, now on the unified runtime_config table)."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from ..middleware.auth import require_role
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.workflow import RuntimeConfig
from ..schemas.prepay_schemas import RuntimeConfigOut, RuntimeConfigUpdate

# Reads are open (feature flags get consumed at bootstrap by every app);
# only mutations require admin.
router = APIRouter(prefix="/api/runtime-config", tags=["runtime-config"])


def _to_out(r: RuntimeConfig) -> RuntimeConfigOut:
    return RuntimeConfigOut(key=r.key, value=r.value, updated_at=r.updated_at)


@router.get("", response_model=List[RuntimeConfigOut])
async def list_config(db: AsyncSession = Depends(get_db)) -> List[RuntimeConfigOut]:
    res = await db.execute(select(RuntimeConfig).order_by(RuntimeConfig.key))
    return [_to_out(r) for r in res.scalars().all()]


@router.get("/{key}", response_model=RuntimeConfigOut)
async def get_config(
    key: str, db: AsyncSession = Depends(get_db)
) -> RuntimeConfigOut:
    res = await db.execute(select(RuntimeConfig).where(RuntimeConfig.key == key))
    row = res.scalar_one_or_none()
    if row is None:
        # ClaimGuard parity: return a default placeholder rather than 404
        return RuntimeConfigOut(key=key, value="", updated_at="")
    return _to_out(row)


@router.patch("/{key}", response_model=RuntimeConfigOut, dependencies=[Depends(require_role("admin"))])
async def update_config(
    key: str,
    body: RuntimeConfigUpdate,
    user_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> RuntimeConfigOut:
    res = await db.execute(select(RuntimeConfig).where(RuntimeConfig.key == key))
    row = res.scalar_one_or_none()
    now = datetime.utcnow().isoformat()
    if row is None:
        row = RuntimeConfig(
            key=key, value=body.value, updated_at=now, updated_by_user_id=user_id
        )
        db.add(row)
    else:
        row.value = body.value
        row.updated_at = now
        row.updated_by_user_id = user_id
    await db.commit()
    return _to_out(row)
