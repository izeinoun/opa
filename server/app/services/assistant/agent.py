"""AssistantService — the Claude tool_use loop (modeled on ClearLink's Charlie).

The loop: call Claude with the user's message history + the app-filtered tool
defs; on each turn, surface any text, then execute the requested tool_use blocks
in-process against OPA's real READ endpoints (forwarding the user's identity),
feed the tool_results back, and repeat until the model stops (end_turn / no
tool_use) — or ask_user pauses for disambiguation.

run() is an async generator yielding event dicts so the route can stream them
as SSE (and the non-streaming route can just take the terminal event).

Events:
  {"type": "assistant_text", "text": str}
  {"type": "tool_start", "id", "name", "input"}
  {"type": "tool_end", "id", "name", "ok", "duration_ms", "error"?}
  {"type": "awaiting_user", "tool_use_id", "question", "options", "messages", "trace"}
  {"type": "final", "message", "messages", "trace"}
  {"type": "error", "error", "messages", "trace"}
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from ...middleware.gate import gate_enabled, make_token
from ...models.workflow import OpaUser
from ...services.ai_service import MODEL, _client
from ...services.rbac_service import RBACService
from .prompt import SYSTEM_PROMPT
from .tools import TOOLS_BY_NAME, tools_for_apps

logger = logging.getLogger("opa.assistant")

MAX_ITERATIONS = 8
MAX_TOKENS = 2048
# Cap a single tool result so a big list can't blow the context window.
MAX_TOOL_RESULT_CHARS = 12_000

ASSISTANT_MODEL = os.getenv("ASSISTANT_MODEL", MODEL)


def _blocks_to_dicts(content: list[Any]) -> list[dict]:
    """Serialize SDK content blocks to plain dicts for the message history."""
    out: list[dict] = []
    for b in content:
        t = getattr(b, "type", None)
        if t == "text":
            out.append({"type": "text", "text": b.text})
        elif t == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


class AssistantService:
    def __init__(self, db: AsyncSession, app: FastAPI) -> None:
        self.db = db
        self.app = app  # used for in-process ASGI tool calls
        self.rbac = RBACService(db)

    async def _tool_schemas(self, user: OpaUser) -> list[dict]:
        apps = await self.rbac.get_app_names_for_user(user.user_id)
        schemas = [t.anthropic_schema() for t in tools_for_apps(apps)]
        # Prompt caching: cache_control on the last tool caches the whole
        # (static) tool prefix + system prompt across turns.
        if schemas:
            schemas[-1] = {**schemas[-1], "cache_control": {"type": "ephemeral"}}
        return schemas

    async def run(
        self, messages: list[dict], user: OpaUser
    ) -> AsyncIterator[dict]:
        tool_schemas = await self._tool_schemas(user)
        system = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
        working = list(messages)
        trace: list[dict] = []

        try:
            client = _client()
        except Exception as e:
            yield {"type": "error", "error": f"LLM unavailable: {e}", "messages": working, "trace": trace}
            return

        for _ in range(MAX_ITERATIONS):
            try:
                resp = await client.messages.create(
                    model=ASSISTANT_MODEL,
                    max_tokens=MAX_TOKENS,
                    system=system,
                    tools=tool_schemas,
                    messages=working,
                )
            except Exception as e:
                logger.exception("assistant LLM call failed")
                yield {"type": "error", "error": f"LLM call failed: {e}", "messages": working, "trace": trace}
                return

            content = resp.content or []
            working.append({"role": "assistant", "content": _blocks_to_dicts(content)})

            for b in content:
                if getattr(b, "type", None) == "text" and b.text:
                    yield {"type": "assistant_text", "text": b.text}

            tool_uses = [b for b in content if getattr(b, "type", None) == "tool_use"]
            if not tool_uses or resp.stop_reason == "end_turn":
                text = next((b.text for b in content if getattr(b, "type", None) == "text"), "")
                yield {"type": "final", "message": text or "(no response)", "messages": working, "trace": trace}
                return

            # ask_user → pause immediately for disambiguation
            ask = next((t for t in tool_uses if t.name == "ask_user"), None)
            if ask is not None:
                trace.append({"tool": "ask_user", "input": ask.input})
                yield {
                    "type": "awaiting_user",
                    "tool_use_id": ask.id,
                    "question": (ask.input or {}).get("question", ""),
                    "options": (ask.input or {}).get("options", []),
                    "messages": working,
                    "trace": trace,
                }
                return

            tool_results = []
            for tu in tool_uses:
                yield {"type": "tool_start", "id": tu.id, "name": tu.name, "input": tu.input}
                block, entry = await self._execute(tu, user)
                tool_results.append(block)
                trace.append(entry)
                yield {
                    "type": "tool_end",
                    "id": tu.id,
                    "name": tu.name,
                    "ok": entry["ok"],
                    "duration_ms": entry["duration_ms"],
                    **({"error": entry["error"]} if not entry["ok"] else {}),
                }
            working.append({"role": "user", "content": tool_results})

        yield {
            "type": "error",
            "error": f"Reached max tool iterations ({MAX_ITERATIONS}) without finishing. Try a narrower question.",
            "messages": working,
            "trace": trace,
        }

    async def _execute(self, tool_use: Any, user: OpaUser) -> tuple[dict, dict]:
        """Run one tool by calling the underlying OPA endpoint in-process,
        forwarding the user's identity. Returns (tool_result_block, trace_entry)."""
        name, tid, inp = tool_use.name, tool_use.id, (tool_use.input or {})
        t0 = time.perf_counter()

        tool = TOOLS_BY_NAME.get(name)
        if tool is None or not tool.method:
            err = f"Unknown or non-executable tool: {name}"
            return (
                {"type": "tool_result", "tool_use_id": tid, "content": err, "is_error": True},
                {"tool": name, "input": inp, "ok": False, "error": err, "duration_ms": 0},
            )

        path = tool.path
        for p in tool.path_params:
            path = path.replace("{" + p + "}", str(inp.get(p, "")))
        params = {k: inp[k] for k in tool.query_params if inp.get(k) is not None}

        # Identity for the in-process call. When the demo gate is enabled, these
        # internal tool calls must also carry a gate token — the agent already
        # passed the gate at /api/assistant/chat, so it mints an internal one.
        headers = {"X-User-Id": user.user_id}
        if gate_enabled():
            headers["Authorization"] = f"Bearer {make_token()}"

        try:
            transport = httpx.ASGITransport(app=self.app)  # no lifespan re-run
            async with httpx.AsyncClient(
                transport=transport, base_url="http://assistant.internal"
            ) as client:
                r = await client.request(tool.method, path, params=params, headers=headers)
            ok = r.status_code < 400
            body = r.text
            if len(body) > MAX_TOOL_RESULT_CHARS:
                body = body[:MAX_TOOL_RESULT_CHARS] + "\n…[truncated]"
            content = body if ok else f"HTTP {r.status_code}: {body}"
        except Exception as e:  # pragma: no cover
            logger.exception("tool execution failed: %s", name)
            ok, content = False, f"tool execution error: {e}"

        dur = int((time.perf_counter() - t0) * 1000)
        # Read-only PHI access via the agent — audit at info level.
        logger.info("assistant tool=%s user=%s ok=%s dur=%dms", name, user.user_id, ok, dur)
        return (
            {"type": "tool_result", "tool_use_id": tid, "content": content, "is_error": not ok},
            {"tool": name, "input": inp, "ok": ok, "duration_ms": dur,
             **({"error": content} if not ok else {})},
        )
