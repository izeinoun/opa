"""Assistant chat API — app-aware, read-only Claude tool-using agent.

  POST /api/assistant/chat         single-shot; returns the terminal event
  POST /api/assistant/chat/stream  SSE; streams assistant_text / tool_* / final
  GET  /api/assistant/tools        the tools available to the current user

Gated to users who can reach at least one app; the agent then filters tools to
the user's apps. The server pins identity from the authenticated user — the
model never controls whose data it can read.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user, require_any_app
from ..models.workflow import OpaUser
from ..services.assistant.agent import AssistantService
from ..services.assistant.tools import tools_for_apps
from ..services.rbac_service import RBACService

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

_ASSISTANT_APPS = ("payguard", "claimguard", "siu")


class ChatRequest(BaseModel):
    # Anthropic-format message history; the client maintains it across turns.
    messages: list[dict[str, Any]]


def _validate(req: ChatRequest) -> None:
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages must be non-empty")
    if req.messages[-1].get("role") != "user":
        raise HTTPException(status_code=400, detail="last message must have role 'user'")


@router.get("/tools")
async def list_tools(
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(require_any_app(*_ASSISTANT_APPS)),
) -> dict:
    apps = await RBACService(db).get_app_names_for_user(user.user_id)
    return {
        "apps": sorted(apps),
        "tools": [
            {"name": t.name, "description": t.description, "apps": list(t.apps)}
            for t in tools_for_apps(apps)
        ],
    }


@router.post("/chat")
async def chat(
    req: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(require_any_app(*_ASSISTANT_APPS)),
) -> dict:
    _validate(req)
    service = AssistantService(db, request.app)
    terminal = {"type": "error", "error": "no response produced"}
    async for evt in service.run(req.messages, user):
        if evt["type"] in ("final", "awaiting_user", "error"):
            terminal = evt
    return terminal


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(require_any_app(*_ASSISTANT_APPS)),
) -> StreamingResponse:
    _validate(req)
    service = AssistantService(db, request.app)

    async def event_source():
        yield "data: " + json.dumps({"type": "ready"}) + "\n\n"
        try:
            async for evt in service.run(req.messages, user):
                yield "data: " + json.dumps(evt) + "\n\n"
        except Exception as e:  # pragma: no cover
            yield "data: " + json.dumps({"type": "error", "error": str(e)}) + "\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
