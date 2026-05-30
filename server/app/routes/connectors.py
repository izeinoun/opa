"""Connector CRUD + run/test endpoints. Admin-only.

The Connectors admin lives as a tab in the IAM app at :5177. All routes
require the 'admin' role via the existing RBAC enforcement layer.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user, require_role
from ..models.workflow import Connector, ConnectorRun, OpaUser
from ..schemas.connector_schemas import (
    ConnectorCreate,
    ConnectorOut,
    ConnectorRunIn,
    ConnectorRunResult,
    ConnectorRunRow,
    ConnectorUpdate,
)
from ..services.connector_service import ConnectorService, serialize_connector

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/connectors",
    tags=["connectors"],
    dependencies=[Depends(require_role("admin"))],
)


# ── List + detail ────────────────────────────────────────────────────────

@router.get("", response_model=List[ConnectorOut])
async def list_connectors(
    kind: Optional[str] = Query(None),
    include_inactive: bool = Query(True),
    db: AsyncSession = Depends(get_db),
) -> List[ConnectorOut]:
    stmt = select(Connector).order_by(Connector.name)
    if kind:
        stmt = stmt.where(Connector.kind == kind)
    if not include_inactive:
        stmt = stmt.where(Connector.is_active == True)  # noqa: E712
    res = await db.execute(stmt)
    return [ConnectorOut(**serialize_connector(c)) for c in res.scalars().all()]


@router.get("/{connector_id}", response_model=ConnectorOut)
async def get_connector(
    connector_id: str,
    db: AsyncSession = Depends(get_db),
) -> ConnectorOut:
    c = (await db.execute(
        select(Connector).where(Connector.connector_id == connector_id)
    )).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    return ConnectorOut(**serialize_connector(c))


# ── Create + update + delete ─────────────────────────────────────────────

@router.post("", response_model=ConnectorOut, status_code=201)
async def create_connector(
    body: ConnectorCreate,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> ConnectorOut:
    dup = (await db.execute(
        select(Connector).where(Connector.name == body.name)
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="A connector with that name already exists")

    now = datetime.utcnow().isoformat()
    c = Connector(
        connector_id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        kind=body.kind,
        direction=body.direction,
        is_active=body.is_active,
        config_json=json.dumps(body.config or {}),
        secret_json=json.dumps(body.secret or {}),
        input_schema_json=json.dumps(body.input_schema) if body.input_schema else None,
        mock_enabled=body.mock_enabled,
        mock_response_json=json.dumps(body.mock_response) if body.mock_response else None,
        created_at=now,
        updated_at=now,
        created_by_user_id=user.user_id,
    )
    db.add(c)
    await db.commit()
    return ConnectorOut(**serialize_connector(c))


@router.patch("/{connector_id}", response_model=ConnectorOut)
async def update_connector(
    connector_id: str,
    body: ConnectorUpdate,
    db: AsyncSession = Depends(get_db),
) -> ConnectorOut:
    c = (await db.execute(
        select(Connector).where(Connector.connector_id == connector_id)
    )).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="Connector not found")

    if body.name is not None:           c.name = body.name
    if body.description is not None:    c.description = body.description
    if body.direction is not None:      c.direction = body.direction
    if body.is_active is not None:      c.is_active = body.is_active
    if body.config is not None:         c.config_json = json.dumps(body.config)
    if body.secret is not None:
        # Merge-on-update: caller sends only the keys they want to add/replace.
        # To remove a key, send {key: null}. Empty object = no change.
        try:
            existing = json.loads(c.secret_json or "{}")
        except json.JSONDecodeError:
            existing = {}
        for k, v in body.secret.items():
            if v is None:
                existing.pop(k, None)
            else:
                existing[k] = v
        c.secret_json = json.dumps(existing)
    if body.input_schema is not None:
        c.input_schema_json = json.dumps(body.input_schema)
    if body.mock_enabled is not None:   c.mock_enabled = body.mock_enabled
    if body.mock_response is not None:
        c.mock_response_json = json.dumps(body.mock_response)
    c.updated_at = datetime.utcnow().isoformat()
    await db.commit()
    return ConnectorOut(**serialize_connector(c))


@router.delete("/{connector_id}", status_code=204)
async def delete_connector(
    connector_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    c = (await db.execute(
        select(Connector).where(Connector.connector_id == connector_id)
    )).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    # Note: connector_runs rows reference connector_id but FKs aren't ON
    # DELETE CASCADE in the migration. Keep the history; only delete the
    # connector row itself. If you need to purge runs too, do it explicitly.
    await db.delete(c)
    await db.commit()


# ── Run + test ───────────────────────────────────────────────────────────

@router.post("/{connector_id}/run", response_model=ConnectorRunResult)
async def run_connector(
    connector_id: str,
    body: ConnectorRunIn,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> ConnectorRunResult:
    svc = ConnectorService(db)
    result = await svc.run(
        connector_id,
        body.input or {},
        triggered_by_user_id=user.user_id,
        correlation_id=body.correlation_id,
        skip_logging=body.dry_run,
    )
    return ConnectorRunResult(**result)


@router.post("/{connector_id}/test", response_model=ConnectorRunResult)
async def test_connector(
    connector_id: str,
    body: ConnectorRunIn,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(get_current_user),
) -> ConnectorRunResult:
    """Same as /run but always skips the connector_runs log entry and is
    allowed against inactive connectors. Use this for the IAM 'Test
    connection' button."""
    svc = ConnectorService(db)
    result = await svc.run(
        connector_id,
        body.input or {},
        triggered_by_user_id=user.user_id,
        correlation_id=body.correlation_id,
        skip_logging=True,
    )
    return ConnectorRunResult(**result)


# ── Run history ──────────────────────────────────────────────────────────

@router.get("/{connector_id}/runs", response_model=List[ConnectorRunRow])
async def list_runs(
    connector_id: str,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> List[ConnectorRunRow]:
    res = await db.execute(
        select(ConnectorRun)
        .where(ConnectorRun.connector_id == connector_id)
        .order_by(ConnectorRun.triggered_at.desc())
        .limit(limit)
    )
    out: List[ConnectorRunRow] = []
    for r in res.scalars().all():
        try:
            meta = json.loads(r.metadata_json or "{}")
        except Exception:
            meta = {}
        out.append(ConnectorRunRow(
            run_id=r.run_id,
            connector_id=r.connector_id,
            triggered_at=r.triggered_at,
            triggered_by_user_id=r.triggered_by_user_id,
            correlation_id=r.correlation_id,
            duration_ms=r.duration_ms,
            ok=r.ok,
            error_message=r.error_message,
            input_preview=(r.input_json or "")[:400] or None,
            output_preview=(r.output_json or "")[:400] or None,
            metadata=meta,
        ))
    return out
