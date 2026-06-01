"""Demo-gate auth endpoints.

  GET  /api/auth/status  → {"gate_enabled": bool}  (public; lets the UI decide
                           whether to show the login screen)
  POST /api/auth/login   → {"token": "..."} on correct password, else 401
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..middleware.gate import check_password, gate_enabled, make_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


@router.get("/status")
async def status() -> dict:
    return {"gate_enabled": gate_enabled()}


@router.post("/login")
async def login(req: LoginRequest) -> dict:
    if not gate_enabled():
        # No gate configured — issue a token anyway so the client flow is uniform.
        return {"token": make_token(), "gate_enabled": False}
    if not check_password(req.password):
        raise HTTPException(status_code=401, detail="Incorrect password")
    return {"token": make_token(), "gate_enabled": True}
