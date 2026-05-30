"""Connector executor service — adapted from clearlink/server/agents/
connectors/executor.js. Dispatches by `kind`, validates input against
the connector's JSON Schema (subset), returns a uniform Result so
callers can feed errors back without exception handling.

Supported kinds in this commit:
  - http     Outbound HTTP/REST call. Templated URL, configurable
             method/headers/auth, optional body interpolation.
  - sftp     Outbound SFTP file delivery. Uploads payload to a remote
             host/path. Returns the destination file path on success.
  - internal In-process Python function reference. Stub kind for
             future tool-use cases (e.g. invoke a service helper).
  - webhook  (Future) outbound POST to a registered callback URL.
             Stubbed; declared but not wired.

Each run is logged to connector_runs (append-only, immutable) for audit
and debugging.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.workflow import Connector, ConnectorRun

logger = logging.getLogger(__name__)


# ── Result shape ──────────────────────────────────────────────────────────

class RunResult(dict):
    """Uniform return type: {ok, data?, error?, duration_ms, metadata?}.

    Using a dict subclass keeps the JSON-friendly shape that mirrors
    ClearLink's executor return while letting Python callers .get fields
    cleanly. Not a Pydantic model — kept lightweight."""
    pass


def ok(data: Any, duration_ms: int, **meta: Any) -> RunResult:
    r = RunResult(ok=True, data=data, duration_ms=duration_ms)
    if meta:
        r["metadata"] = meta
    return r


def err(message: str, duration_ms: int, **meta: Any) -> RunResult:
    r = RunResult(ok=False, error=message, duration_ms=duration_ms)
    if meta:
        r["metadata"] = meta
    return r


# ── Minimal JSON-Schema-ish validation (subset used in practice) ─────────

def _validate_input(schema: Optional[dict], input_data: dict) -> Optional[str]:
    """Return None on valid input, an error string on rejection. Mirrors
    ClearLink's validateInput. Pull in Ajv-style validation later when
    we have more complex schemas."""
    if not schema or not isinstance(schema, dict):
        return None
    if schema.get("type") != "object":
        return None
    props = schema.get("properties") or {}
    required = schema.get("required") or []
    for k in required:
        if input_data.get(k) is None:
            return f"Missing required input: {k}"
    if schema.get("additionalProperties") is False:
        for k in input_data.keys():
            if k not in props:
                return f"Unknown input field: {k}"
    for k, definition in props.items():
        if input_data.get(k) is None:
            continue
        v = input_data[k]
        t = definition.get("type")
        if t == "integer" and not isinstance(v, int):
            return f"Field '{k}' must be an integer"
        if t == "string" and not isinstance(v, str):
            return f"Field '{k}' must be a string"
        if "enum" in definition and v not in definition["enum"]:
            return f"Field '{k}' must be one of: {', '.join(map(str, definition['enum']))}"
        if "minimum" in definition and v < definition["minimum"]:
            return f"Field '{k}' must be >= {definition['minimum']}"
        if "maximum" in definition and v > definition["maximum"]:
            return f"Field '{k}' must be <= {definition['maximum']}"
    return None


def _interpolate_url(template: str, input_data: dict) -> str:
    """Replace {placeholder} in URL templates with URL-encoded input values.
    Raises KeyError if a placeholder is unresolved."""
    import re
    from urllib.parse import quote
    def sub(m: "re.Match") -> str:
        k = m.group(1)
        if k not in input_data or input_data[k] is None:
            raise KeyError(k)
        return quote(str(input_data[k]), safe="")
    return re.sub(r"\{(\w+)\}", sub, template)


# ── Per-kind executors ────────────────────────────────────────────────────

async def _run_http(connector: Connector, input_data: dict) -> RunResult:
    start = time.monotonic()
    try:
        config = json.loads(connector.config_json or "{}")
        secret = json.loads(connector.secret_json or "{}")
    except json.JSONDecodeError as e:
        return err(f"Invalid connector config JSON: {e}", _ms(start))

    url_template = config.get("url")
    if not url_template:
        return err("Connector config missing 'url'", _ms(start))

    try:
        url = _interpolate_url(url_template, input_data)
    except KeyError as e:
        return err(f"URL placeholder {{{e.args[0]}}} missing from input", _ms(start))

    method = (config.get("method") or "GET").upper()
    headers: Dict[str, str] = {}
    if config.get("auth_header_name"):
        key = secret.get("api_key") or ""
        fmt = config.get("auth_header_format") or "{key}"
        headers[config["auth_header_name"]] = fmt.replace("{key}", key)
    extra_headers = config.get("headers")
    if isinstance(extra_headers, dict):
        headers.update({str(k): str(v) for k, v in extra_headers.items()})

    timeout = float(config.get("timeout_seconds", 30))

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            req_body = None if method == "GET" else input_data
            resp = await client.request(method, url, headers=headers, json=req_body)
            ct = resp.headers.get("content-type", "")
            data: Any
            if "application/json" in ct:
                try:
                    data = resp.json()
                except Exception:
                    data = resp.text
            else:
                data = resp.text
            ok_status = 200 <= resp.status_code < 300
            metadata = {
                "status_code": resp.status_code,
                "response_size_bytes": len(resp.content or b""),
                "url_resolved": url,
            }
            if ok_status:
                return ok(data, _ms(start), **metadata)
            return err(
                f"HTTP {resp.status_code}: {resp.reason_phrase}",
                _ms(start),
                **metadata,
                response_body_preview=(resp.text or "")[:400],
            )
    except httpx.HTTPError as e:
        return err(f"HTTP error: {e}", _ms(start), url_resolved=url)


async def _run_sftp(connector: Connector, input_data: dict) -> RunResult:
    """SFTP file upload. Expects input_data to contain either:
      - {payload: <bytes-or-string>, remote_filename: str} for an in-memory
        body to upload, or
      - {local_path: str, remote_filename: str} for a file on disk

    Connector config provides: host, port, username, remote_dir.
    Secret provides: password OR private_key_pem.

    Implementation uses paramiko (sync) wrapped in run_in_executor so the
    request loop isn't blocked. paramiko is the standard Python SFTP
    library; it's an optional dependency declared in requirements.
    """
    start = time.monotonic()
    try:
        config = json.loads(connector.config_json or "{}")
        secret = json.loads(connector.secret_json or "{}")
    except json.JSONDecodeError as e:
        return err(f"Invalid connector config JSON: {e}", _ms(start))

    host = config.get("host")
    port = int(config.get("port", 22))
    username = config.get("username") or secret.get("username")
    if not host or not username:
        return err("SFTP connector requires config.host and (config|secret).username", _ms(start))

    password = secret.get("password")
    private_key_pem = secret.get("private_key_pem")
    if not password and not private_key_pem:
        return err("SFTP connector requires secret.password or secret.private_key_pem", _ms(start))

    remote_dir = (config.get("remote_dir") or "/").rstrip("/") + "/"
    remote_filename = input_data.get("remote_filename")
    if not remote_filename:
        return err("input.remote_filename is required", _ms(start))

    payload = input_data.get("payload")
    local_path = input_data.get("local_path")
    if payload is None and not local_path:
        return err("input.payload or input.local_path is required", _ms(start))

    try:
        import paramiko  # type: ignore
    except ImportError:
        return err(
            "paramiko is not installed — SFTP connectors require it. "
            "Add 'paramiko>=3.0' to requirements.txt.",
            _ms(start),
        )

    def _do_upload() -> tuple[bool, str, dict]:
        try:
            transport = paramiko.Transport((host, port))
            try:
                if private_key_pem:
                    pkey = paramiko.RSAKey.from_private_key(io.StringIO(private_key_pem))
                    transport.connect(username=username, pkey=pkey)
                else:
                    transport.connect(username=username, password=password)
                sftp = paramiko.SFTPClient.from_transport(transport)
                if sftp is None:
                    return False, "Failed to open SFTP channel", {}
                remote_path = remote_dir + remote_filename
                if payload is not None:
                    body = payload.encode("utf-8") if isinstance(payload, str) else payload
                    with sftp.file(remote_path, "wb") as fh:
                        fh.write(body)
                    sz = len(body)
                else:
                    sftp.put(local_path, remote_path)
                    import os
                    sz = os.path.getsize(local_path)
                sftp.close()
                return True, remote_path, {"remote_path": remote_path, "bytes": sz}
            finally:
                transport.close()
        except Exception as e:
            return False, str(e), {}

    success, msg_or_path, meta = await asyncio.get_event_loop().run_in_executor(
        None, _do_upload,
    )
    if success:
        return ok({"remote_path": msg_or_path}, _ms(start), **meta)
    return err(f"SFTP upload failed: {msg_or_path}", _ms(start))


async def _run_internal(connector: Connector, input_data: dict) -> RunResult:
    """In-process function dispatch. The connector's config_json must contain
    {function: 'name'} where 'name' is registered in INTERNAL_REGISTRY.
    This is for tool-like operations that don't need their own HTTP service."""
    start = time.monotonic()
    try:
        config = json.loads(connector.config_json or "{}")
    except json.JSONDecodeError as e:
        return err(f"Invalid connector config JSON: {e}", _ms(start))

    fn_name = config.get("function")
    if not fn_name:
        return err("Internal connector requires config.function", _ms(start))
    fn = INTERNAL_REGISTRY.get(fn_name)
    if fn is None:
        return err(f"Unknown internal function: {fn_name}", _ms(start),
                   available=sorted(INTERNAL_REGISTRY.keys()))
    try:
        if asyncio.iscoroutinefunction(fn):
            data = await fn(input_data)
        else:
            data = fn(input_data)
        return ok(data, _ms(start))
    except Exception as e:
        return err(f"Internal connector raised: {e}", _ms(start))


async def _run_webhook(connector: Connector, input_data: dict) -> RunResult:
    """Outbound webhook — same wire shape as http, but the conceptual
    direction is push: 'we are notifying someone'. For now this delegates
    to _run_http since the mechanics are identical. The 'webhook' kind
    exists so the UI + audit log can distinguish 'we called their API to
    pull data' from 'we pushed a notification to their endpoint'."""
    return await _run_http(connector, input_data)


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


# ── Internal function registry (stub; add real entries as they appear) ────

INTERNAL_REGISTRY: Dict[str, Any] = {
    # 'recompute_priority': recompute_priority_handler,
    # ... add platform-internal callables here
}


# ── Public service API ────────────────────────────────────────────────────

class ConnectorService:
    """High-level connector operations: run, test, and audit."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def run(
        self,
        connector_id: str,
        input_data: dict,
        *,
        triggered_by_user_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        skip_logging: bool = False,
    ) -> RunResult:
        """Execute a connector. Validates input, dispatches by kind, returns
        a uniform RunResult, and persists a connector_runs row unless
        skip_logging=True (useful for 'test connection' dry runs)."""
        c = (await self.db.execute(
            select(Connector).where(Connector.connector_id == connector_id)
        )).scalar_one_or_none()
        if c is None:
            return RunResult(
                ok=False, error="Connector not found", duration_ms=0,
            )
        if not c.is_active and not skip_logging:
            # 'test' calls (skip_logging=True) may still run an inactive connector
            return RunResult(
                ok=False, error="Connector is not active", duration_ms=0,
            )

        # Input validation
        schema = None
        if c.input_schema_json:
            try:
                schema = json.loads(c.input_schema_json)
            except json.JSONDecodeError:
                schema = None
        validation_err = _validate_input(schema, input_data or {})
        if validation_err:
            result = RunResult(ok=False, error=validation_err, duration_ms=0)
            await self._log(c, input_data, result, triggered_by_user_id, correlation_id, skip_logging)
            return result

        # Mock short-circuit
        if c.mock_enabled and c.mock_response_json:
            try:
                mock = json.loads(c.mock_response_json)
                result = RunResult(ok=True, data=mock, duration_ms=0, metadata={"mocked": True})
            except json.JSONDecodeError as e:
                result = RunResult(ok=False, error=f"Mock JSON invalid: {e}", duration_ms=0)
            await self._log(c, input_data, result, triggered_by_user_id, correlation_id, skip_logging)
            return result

        # Dispatch
        if c.kind == "http":
            result = await _run_http(c, input_data or {})
        elif c.kind == "sftp":
            result = await _run_sftp(c, input_data or {})
        elif c.kind == "internal":
            result = await _run_internal(c, input_data or {})
        elif c.kind == "webhook":
            result = await _run_webhook(c, input_data or {})
        else:
            result = RunResult(
                ok=False, error=f"Unsupported connector kind: {c.kind}",
                duration_ms=0,
            )

        await self._log(c, input_data, result, triggered_by_user_id, correlation_id, skip_logging)
        return result

    async def _log(
        self,
        c: Connector,
        input_data: Optional[dict],
        result: RunResult,
        triggered_by_user_id: Optional[str],
        correlation_id: Optional[str],
        skip: bool,
    ) -> None:
        if skip:
            return
        try:
            row = ConnectorRun(
                run_id=str(uuid.uuid4()),
                connector_id=c.connector_id,
                triggered_at=datetime.utcnow().isoformat(),
                triggered_by_user_id=triggered_by_user_id,
                correlation_id=correlation_id,
                duration_ms=int(result.get("duration_ms") or 0),
                ok=bool(result.get("ok")),
                error_message=result.get("error"),
                input_json=json.dumps(input_data) if input_data else None,
                output_json=json.dumps(result.get("data"))[:50_000] if result.get("data") is not None else None,
                metadata_json=json.dumps(result.get("metadata") or {}),
            )
            self.db.add(row)
            await self.db.commit()
        except Exception as e:
            logger.exception("Failed to log connector run: %s", e)


# ── Helper: serialize a Connector hiding secrets ──────────────────────────

def serialize_connector(c: Connector, *, include_secrets: bool = False) -> dict:
    """Return the connector as a dict suitable for API responses. Secrets
    are returned as a masked summary ({'set': True} per key) unless
    include_secrets=True (only for the connector owner / system jobs)."""
    try:
        config = json.loads(c.config_json or "{}")
    except json.JSONDecodeError:
        config = {}
    try:
        secret = json.loads(c.secret_json or "{}")
    except json.JSONDecodeError:
        secret = {}
    secret_view = secret if include_secrets else {k: {"set": True} for k in secret.keys()}

    try:
        schema = json.loads(c.input_schema_json) if c.input_schema_json else None
    except json.JSONDecodeError:
        schema = None
    try:
        mock = json.loads(c.mock_response_json) if c.mock_response_json else None
    except json.JSONDecodeError:
        mock = None

    return {
        "connector_id": c.connector_id,
        "name": c.name,
        "description": c.description,
        "kind": c.kind,
        "direction": c.direction,
        "is_active": c.is_active,
        "config": config,
        "secret_keys": secret_view,
        "input_schema": schema,
        "mock_enabled": c.mock_enabled,
        "mock_response": mock,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        "created_by_user_id": c.created_by_user_id,
    }
