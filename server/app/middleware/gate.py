"""Shared-login demo gate.

When `DEMO_PASSWORD` is set (public deployments), every `/api/*` request must
carry a valid bearer token obtained from `POST /api/auth/login`. This walls the
open internet — and the paid AI endpoints — off from anonymous access, while the
existing X-User-Id persona switcher keeps working *behind* the gate.

When `DEMO_PASSWORD` is empty (local dev, tests), the gate is disabled and
nothing changes.

Tokens are stateless HMAC-signed `"<exp>.<sig>"` strings (no DB, no extra deps),
signed with SECRET_KEY and carrying an expiry. This is a coarse "you may enter
the demo" gate, NOT per-user auth — identity is still selected via X-User-Id.
"""
from __future__ import annotations

import hashlib
import hmac
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..config import settings

_TTL_SECONDS = 12 * 3600

# Paths reachable without a token (everything else under /api needs one).
_OPEN_PATHS = {"/api/auth/login", "/api/auth/status", "/health"}


def gate_enabled() -> bool:
    return bool(settings.demo_password)


def _secret() -> bytes:
    # Prefer an explicit SECRET_KEY; fall back to the demo password so the gate
    # still works if only DEMO_PASSWORD is configured.
    key = settings.secret_key or settings.demo_password or "dev"
    return key.encode()


def make_token(ttl_seconds: int = _TTL_SECONDS) -> str:
    exp = int(time.time()) + ttl_seconds
    sig = hmac.new(_secret(), str(exp).encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def verify_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        exp_s, sig = token.split(".", 1)
    except ValueError:
        return False
    expected = hmac.new(_secret(), exp_s.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        return int(exp_s) > int(time.time())
    except ValueError:
        return False


def check_password(password: str) -> bool:
    return bool(settings.demo_password) and hmac.compare_digest(
        password or "", settings.demo_password
    )


class DemoGateMiddleware(BaseHTTPMiddleware):
    """Require a valid bearer token on /api/* when the gate is enabled."""

    async def dispatch(self, request: Request, call_next):
        if not gate_enabled():
            return await call_next(request)

        path = request.url.path
        # Only guard the API; the SPA's static assets/index must load so the
        # login screen can render. CORS preflights pass through.
        if request.method == "OPTIONS" or not path.startswith("/api") or path in _OPEN_PATHS:
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else None
        if not verify_token(token):
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "detail": "Demo login required."},
            )
        return await call_next(request)
