"""Pydantic schemas for the Connectors admin surface."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ConnectorKind = Literal["http", "sftp", "internal", "webhook"]
ConnectorDirection = Literal["inbound", "outbound"]


class ConnectorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    kind: ConnectorKind
    direction: ConnectorDirection = "outbound"
    is_active: bool = True
    config: Dict[str, Any] = {}
    secret: Dict[str, Any] = {}
    input_schema: Optional[Dict[str, Any]] = None
    mock_enabled: bool = False
    mock_response: Optional[Dict[str, Any]] = None


class ConnectorUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    direction: Optional[ConnectorDirection] = None
    is_active: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None
    secret: Optional[Dict[str, Any]] = None        # send only the keys you want to add/replace
    input_schema: Optional[Dict[str, Any]] = None
    mock_enabled: Optional[bool] = None
    mock_response: Optional[Dict[str, Any]] = None


class ConnectorOut(BaseModel):
    connector_id: str
    name: str
    description: str
    kind: str
    direction: str
    is_active: bool
    config: Dict[str, Any]
    secret_keys: Dict[str, Any]   # masked summary unless owner/system requests reveal
    input_schema: Optional[Dict[str, Any]] = None
    mock_enabled: bool
    mock_response: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: str
    created_by_user_id: Optional[str] = None


class ConnectorRunIn(BaseModel):
    input: Dict[str, Any] = {}
    correlation_id: Optional[str] = None
    # True for "Test" — runs without writing a connector_runs row.
    dry_run: bool = False


class ConnectorRunResult(BaseModel):
    ok: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: int = 0
    metadata: Optional[Dict[str, Any]] = None


class ConnectorRunRow(BaseModel):
    run_id: str
    connector_id: str
    triggered_at: str
    triggered_by_user_id: Optional[str] = None
    correlation_id: Optional[str] = None
    duration_ms: Optional[int] = None
    ok: bool
    error_message: Optional[str] = None
    input_preview: Optional[str] = None      # first ~400 chars
    output_preview: Optional[str] = None
    metadata: Dict[str, Any] = {}
