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
  {"type": "directive", "view", "params", "caption", "guidance"?}
  {"type": "awaiting_user", "tool_use_id", "question", "options", "messages", "trace"}
  {"type": "awaiting_confirmation", "tool_use_id", "action", "params", "summary", "preview", "messages", "trace"}
  {"type": "final", "message", "messages", "trace", "guidance"?, "remaining_summary"?}
  {"type": "error", "error", "messages", "trace"}

When the turn concerns a specific case (a present_view(case) directive, or the
client passed context.active_case_id), the agent attaches role/owner-aware
`guidance` (lifecycle + next_action + remaining_summary) to the directive and
final events so the cockpit can render the lifecycle rail + Next pill.
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

from ...config import settings
from ...middleware.gate import gate_enabled, make_token
from ...models.workflow import OpaUser
from ...services.ai_service import _client
from ...services.rbac_service import RBACService
from .prompt import SYSTEM_PROMPT
from .tools import TOOLS_BY_NAME, tools_for_apps, WRITE_ACTIONS
from .clearlink_integration import call_clearlink_tool

logger = logging.getLogger("opa.assistant")

MAX_ITERATIONS = 8
MAX_TOKENS = 4096  # room for rich inline-styled HTML cards/tables without truncation
# Cap a single tool result so a big list can't blow the context window.
MAX_TOOL_RESULT_CHARS = 12_000

# The assistant is tool-routing + formatting, not deep reasoning — run it on
# Haiku for much lower latency (and cost). Single source of truth in config
# (settings.assistant_model; env ASSISTANT_MODEL overrides). Heavier AI (claim
# analysis in ai_service) stays on the Sonnet settings.llm_model.
ASSISTANT_MODEL = settings.assistant_model


import re

# Trailing line the assistant appends: @@FOLLOWUPS@@ ["q1","q2","q3"]
_FOLLOWUPS_RE = re.compile(r"@@FOLLOWUPS@@\s*(\[.*\])\s*$", re.S)


def _split_followups(text: str) -> tuple[str, list[str]]:
    """Split the trailing @@FOLLOWUPS@@ marker out of a text block.
    Returns (clean_text, suggestions). Never raises."""
    m = _FOLLOWUPS_RE.search(text or "")
    if not m:
        return text, []
    try:
        arr = json.loads(m.group(1))
        sugg = [str(s).strip() for s in arr if str(s).strip()][:4] if isinstance(arr, list) else []
    except Exception:
        sugg = []
    return text[: m.start()].rstrip(), sugg


def _strip_code_fence(text: str) -> str:
    """Remove a wrapping ```html … ``` (or plain ```) code fence the model
    sometimes adds around its reply. Only acts when the text starts with a fence,
    so normal output is untouched. Strips leading and trailing fences
    independently so a trailing ``` after @@FOLLOWUPS@@ doesn't survive."""
    t = (text or "").strip()
    if not t.startswith("```"):
        return text
    t = re.sub(r"^```[A-Za-z0-9]*[ \t]*\r?\n?", "", t)   # leading ```lang
    t = re.sub(r"\r?\n?```$", "", t.rstrip())            # trailing ```
    return t.strip()


# ── Deterministic fast-path ───────────────────────────────────────────────
# Obvious navigational commands shouldn't pay an LLM round-trip (or ride on the
# model's instruction-following). We match a few unambiguous phrasings on the
# latest user message and emit the render directive directly. Anything fuzzier
# falls through to the model. Patterns are anchored to the WHOLE message so a
# real question ("what CPTs are on case 1?") never gets hijacked.
_FP_CASE = re.compile(r"^\s*(?:open|show|view|display|pull up|go to|take me to)\s+case\s+#?(\d+)\s*[.!?]*\s*$", re.I)
_FP_MY_CASES = re.compile(r"^\s*(?:show |open |view )?(?:my )?(?:assigned )?(?:cases|worklist|queue)\s*[.!?]*\s*$", re.I)
_FP_MY_DASH = re.compile(r"^\s*(?:show |open |view )?(?:my dashboard|my metrics|how am i doing)\s*[.!?]*\s*$", re.I)
# "open this case" only resolves when the client tells us which case is on screen.
_FP_THIS_CASE = re.compile(r"^\s*(?:open|show|view|display|go to|pull up)\s+(?:(?:this|that|the|current|displayed)\s+){1,2}case\s*[.!?]*\s*$", re.I)


def _fast_directive(messages: list[dict], context: dict | None = None) -> dict | None:
    """Return a render directive for an unambiguous navigational command on the
    latest user message, or None to defer to the model. Only fires on a plain
    string user turn (not a tool_result continuation)."""
    if not messages:
        return None
    last = messages[-1]
    if last.get("role") != "user":
        return None
    content = last.get("content")
    if not isinstance(content, str):
        return None
    text = content.strip()
    m = _FP_CASE.match(text)
    if m:
        return {"view": "case", "params": {"case_id": int(m.group(1))}, "caption": f"Case {m.group(1)}"}
    active_case_id = (context or {}).get("active_case_id")
    if active_case_id and _FP_THIS_CASE.match(text):
        return {"view": "case", "params": {"case_id": int(active_case_id)}, "caption": f"Case {active_case_id}"}
    if _FP_MY_CASES.match(text):
        return {"view": "worklist", "params": {"scope": "mine"}, "caption": "Your assigned cases"}
    if _FP_MY_DASH.match(text):
        return {"view": "my_dashboard", "params": {"period": "month"}, "caption": "Your dashboard"}
    return None


def _context_preamble(context: dict | None) -> str | None:
    """A short note telling the model what the user is currently looking at, so
    "this case" / "the displayed case" resolves from the first message on."""
    if not context:
        return None
    cid = context.get("active_case_id")
    view = context.get("active_view")
    if cid:
        return (
            f"CURRENT VIEW: the user is looking at case #{cid} in the app. When they say "
            f"\"this case\", \"the case\", \"the current/displayed case\", or otherwise refer to a "
            f"case without naming a number, they mean case #{cid}. Pass case_id={cid} to any tool "
            f"that needs a case id, unless they clearly name a different case."
        )
    if view:
        return f"CURRENT VIEW: the user is on the {view} view."
    return None


_CONFIRM_YES = "CONFIRMED"
_CONFIRM_NO = "CANCELLED"


def _http_error_detail(r) -> str:
    """Pull a human message out of a failed in-process response (FastAPI's JSON
    `detail`, falling back to the raw body)."""
    try:
        data = r.json()
        return str(data.get("detail") or data.get("error") or r.text)[:300]
    except Exception:
        return (r.text or f"HTTP {r.status_code}")[:300]


def _pending_write(messages: list[dict]) -> dict | None:
    """If the latest user turn is a confirm/cancel of a previously-proposed
    write, return {decision, action, params, tool_use_id}. The decision lives in
    a tool_result whose tool_use_id points back at a confirm_action tool_use."""
    if not messages:
        return None
    last = messages[-1]
    if last.get("role") != "user" or not isinstance(last.get("content"), list):
        return None
    tr = next((b for b in last["content"] if isinstance(b, dict) and b.get("type") == "tool_result"), None)
    if not tr:
        return None
    tid = tr.get("tool_use_id")
    decision = (tr.get("content") or "").strip().upper()
    if decision not in (_CONFIRM_YES, _CONFIRM_NO):
        return None
    # Find the matching confirm_action tool_use in an earlier assistant turn.
    for m in reversed(messages):
        if m.get("role") == "assistant" and isinstance(m.get("content"), list):
            for b in m["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") == tid \
                        and b.get("name") == "confirm_action":
                    inp = b.get("input") or {}
                    return {
                        "decision": decision,
                        "action": inp.get("action"),
                        "params": inp.get("params") or {},
                        "summary": inp.get("summary", ""),
                        "tool_use_id": tid,
                    }
    return None


def _change_preview(action: str, params: dict) -> str:
    """A short, deterministic 'what will change' line to accompany the model's
    summary on the confirmation card."""
    p = params or {}
    if action == "accept_finding":
        return "Accept this finding — it will count toward the case's at-risk total."
    if action == "reject_finding":
        return f"Reject this finding as a false positive ($0). Reason: {p.get('reason', '—')}."
    if action == "adjust_finding":
        amt = p.get("adjusted_amount")
        return f"Adjust this finding to ${amt:,.2f}." if isinstance(amt, (int, float)) else "Adjust this finding's amount."
    if action == "take_ownership":
        return "Assign this case to you."
    if action == "assign_case":
        return "Reassign this case."
    if action == "transition_case":
        return f"Move the case to '{p.get('to_status', '?')}'."
    if action == "approve_case":
        return "Approve the held decision (recoup → recoupment letter is generated)."
    if action == "reject_case":
        return f"Reject the held decision; the case returns to in-review. Reason: {p.get('reason', '—')}."
    if action == "escalate_to_supervisor":
        return f"Flag the case for supervisor attention. Reason: {p.get('reason', '—')}."
    return "This will modify the case."


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

    async def _guidance_for(self, case_id, user: OpaUser) -> dict | None:
        """Compute role/owner-aware case guidance directly via the service (same
        DB session) so the cockpit's lifecycle rail + Next pill are grounded in
        real case state. Returns a JSON-able dict, or None on any failure."""
        if not case_id:
            return None
        try:
            from ...services.case_service import CaseService
            detail = await CaseService(self.db).get_case_detail(int(case_id), user=user)
            return detail.guidance.model_dump() if detail.guidance else None
        except Exception:
            logger.debug("guidance computation failed for case %s", case_id, exc_info=True)
            return None

    @staticmethod
    def _final_guidance(guidance: dict | None) -> dict:
        """Extra fields to splice into a `final` event when a case is in play."""
        if not guidance:
            return {}
        return {"guidance": guidance, "remaining_summary": guidance.get("remaining_summary", "")}

    async def run(
        self, messages: list[dict], user: OpaUser, context: dict | None = None
    ) -> AsyncIterator[dict]:
        # Resume after a write confirmation: execute (or skip) the proposed
        # write deterministically — never touches the model.
        pend = _pending_write(messages)
        if pend is not None:
            async for evt in self._handle_confirmation(pend, messages, user, context):
                yield evt
            return

        # Deterministic fast-path: obvious nav commands skip the LLM entirely.
        fast = _fast_directive(messages, context)
        if fast is not None:
            working = list(messages) + [
                {"role": "assistant", "content": [{"type": "text", "text": fast["caption"]}]}
            ]
            guidance = None
            if fast["view"] == "case":
                guidance = await self._guidance_for(fast["params"].get("case_id"), user)
            yield {"type": "directive", **fast, **({"guidance": guidance} if guidance else {})}
            yield {"type": "final", "message": fast["caption"], "messages": working,
                   "trace": [{"shortcut": fast["view"], "params": fast["params"]}], "suggestions": [],
                   **self._final_guidance(guidance)}
            return

        tool_schemas = await self._tool_schemas(user)
        # Cached static system prompt first (stable cache prefix); append the
        # dynamic per-turn view context as a separate, uncached block.
        system = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
        preamble = _context_preamble(context)
        if preamble:
            system.append({"type": "text", "text": preamble})
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
            # Serialize blocks, then strip the trailing @@FOLLOWUPS@@ line out of
            # text blocks (so it never displays / persists) and capture it.
            dict_blocks = _blocks_to_dicts(content)
            turn_suggestions: list[str] = []
            for blk in dict_blocks:
                if blk.get("type") == "text":
                    # Drop any wrapping ```html fence first so the trailing ```
                    # doesn't shield the @@FOLLOWUPS@@ marker from stripping.
                    blk["text"] = _strip_code_fence(blk["text"])
                    blk["text"], sugg = _split_followups(blk["text"])
                    if sugg:
                        turn_suggestions = sugg
            working.append({"role": "assistant", "content": dict_blocks})

            for blk in dict_blocks:
                if blk.get("type") == "text" and blk["text"]:
                    yield {"type": "assistant_text", "text": blk["text"]}

            tool_uses = [b for b in content if getattr(b, "type", None) == "tool_use"]
            if not tool_uses or resp.stop_reason == "end_turn":
                text = next((blk["text"] for blk in dict_blocks if blk.get("type") == "text"), "")
                # A prose answer about the case on screen still carries guidance
                # so the cockpit rail + Next pill update.
                guidance = await self._guidance_for((context or {}).get("active_case_id"), user)
                yield {"type": "final", "message": text or "(no response)",
                       "messages": working, "trace": trace, "suggestions": turn_suggestions,
                       **self._final_guidance(guidance)}
                return

            # present_view → emit a render directive and finish the turn. The
            # view is handled entirely client-side (mount an interactive view),
            # so there's no follow-up tool_result from the user; we append a
            # synthetic one ourselves to keep the message history valid (a
            # dangling tool_use would break the next turn's API call).
            present = next((t for t in tool_uses if t.name == "present_view"), None)
            if present is not None:
                pin = present.input or {}
                trace.append({"tool": "present_view", "input": pin})
                text = next((blk["text"] for blk in dict_blocks if blk.get("type") == "text"), "")
                pin_params = pin.get("params") or {}
                guide_case_id = (
                    pin_params.get("case_id") if pin.get("view") == "case"
                    else (context or {}).get("active_case_id")
                )
                guidance = await self._guidance_for(guide_case_id, user)
                yield {
                    "type": "directive",
                    "view": pin.get("view"),
                    "params": pin_params,
                    "caption": pin.get("caption") or text,
                    **({"guidance": guidance} if guidance else {}),
                }
                # Resolve EVERY tool_use this turn (the model may have paired
                # present_view with a read tool) so no tool_use is left dangling.
                working.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": "View presented to the user."
                            if tu.id == present.id
                            else "(skipped — a view was presented)",
                        }
                        for tu in tool_uses
                    ],
                })
                yield {"type": "final", "message": text or "",
                       "messages": working, "trace": trace, "suggestions": turn_suggestions,
                       **self._final_guidance(guidance)}
                return

            # confirm_action → propose a write and pause for explicit user
            # confirmation. The write executes ONLY on resume (CONFIRMED).
            confirm = next((t for t in tool_uses if t.name == "confirm_action"), None)
            if confirm is not None:
                ci = confirm.input or {}
                action = ci.get("action")
                params = ci.get("params") or {}
                if action not in WRITE_ACTIONS:
                    # Unknown action → tell the model and let it retry.
                    working.append({"role": "user", "content": [{
                        "type": "tool_result", "tool_use_id": confirm.id,
                        "content": f"Unknown action '{action}'. Valid actions: {list(WRITE_ACTIONS)}.",
                        "is_error": True,
                    }]})
                    continue
                trace.append({"tool": "confirm_action", "input": ci})
                yield {
                    "type": "awaiting_confirmation",
                    "tool_use_id": confirm.id,
                    "action": action,
                    "params": params,
                    "summary": ci.get("summary", ""),
                    "preview": _change_preview(action, params),
                    "messages": working,
                    "trace": trace,
                }
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

    async def _handle_confirmation(
        self, pend: dict, messages: list[dict], user: OpaUser, context: dict | None
    ) -> AsyncIterator[dict]:
        """Resume after the user confirmed/cancelled a proposed write. The
        confirm_action tool_use + the user's tool_result are already in
        `messages` (valid history); we execute (or not) deterministically — no
        extra LLM round-trip — and present the updated case."""
        working = list(messages)
        action, params = pend["action"], pend["params"]
        case_id = params.get("case_id") or (context or {}).get("active_case_id")

        if pend["decision"] != _CONFIRM_YES:
            msg = "Okay — I won't make that change."
            working.append({"role": "assistant", "content": [{"type": "text", "text": msg}]})
            guidance = await self._guidance_for(case_id, user)
            yield {"type": "final", "message": msg, "messages": working, "trace": [],
                   "suggestions": [], **self._final_guidance(guidance)}
            return

        spec = WRITE_ACTIONS.get(action)
        if spec is None:
            err = f"Unknown write action '{action}'."
            working.append({"role": "assistant", "content": [{"type": "text", "text": err}]})
            yield {"type": "error", "error": err, "messages": working, "trace": []}
            return

        yield {"type": "tool_start", "id": pend["tool_use_id"], "name": action, "input": params}
        ok, content, dur = await self._execute_write(spec, params, user)
        entry = {"tool": action, "input": params, "ok": ok, "duration_ms": dur,
                 **({"error": content} if not ok else {})}
        yield {"type": "tool_end", "id": pend["tool_use_id"], "name": action, "ok": ok,
               "duration_ms": dur, **({"error": content} if not ok else {})}

        guidance = await self._guidance_for(case_id, user)
        if ok:
            msg = "Done — the change has been applied."
            working.append({"role": "assistant", "content": [{"type": "text", "text": msg}]})
            if case_id:
                yield {"type": "directive", "view": "case",
                       "params": {"case_id": int(case_id)}, "caption": f"Case {case_id}",
                       **({"guidance": guidance} if guidance else {})}
            yield {"type": "final", "message": msg, "messages": working, "trace": [entry],
                   "suggestions": [], **self._final_guidance(guidance)}
        else:
            msg = f"That didn't go through — {content}"
            working.append({"role": "assistant", "content": [{"type": "text", "text": msg}]})
            yield {"type": "final", "message": msg, "messages": working, "trace": [entry],
                   "suggestions": [], **self._final_guidance(guidance)}

    async def _execute_write(self, spec, params: dict, user: OpaUser) -> tuple[bool, str, int]:
        """Call one write endpoint in-process as the user (JSON body). Returns
        (ok, content, duration_ms). Server-side RBAC / gates / audit all apply."""
        t0 = time.perf_counter()
        path = spec.path
        for p in spec.path_params:
            path = path.replace("{" + p + "}", str(params.get(p, "")))
        body: dict[str, Any] = {k: params[k] for k in spec.body_params if params.get(k) is not None}
        if spec.inject_analyst_id:
            body["analyst_id"] = user.user_id

        headers = {"X-User-Id": user.user_id, "Content-Type": "application/json"}
        if gate_enabled():
            headers["Authorization"] = f"Bearer {make_token()}"
        try:
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://assistant.internal"
            ) as client:
                r = await client.request(spec.method, path, json=body, headers=headers)
            ok = r.status_code < 400
            content = "ok" if ok else _http_error_detail(r)
        except Exception as e:  # pragma: no cover
            logger.exception("assistant write failed: %s", spec.path)
            ok, content = False, f"write execution error: {e}"
        dur = int((time.perf_counter() - t0) * 1000)
        logger.info("assistant WRITE path=%s user=%s ok=%s dur=%dms", path, user.user_id, ok, dur)
        return ok, content, dur

    async def _execute(self, tool_use: Any, user: OpaUser) -> tuple[dict, dict]:
        """Run one tool by calling the underlying endpoint (OPA in-process or
        ClearLink via HTTP). Returns (tool_result_block, trace_entry)."""
        name, tid, inp = tool_use.name, tool_use.id, (tool_use.input or {})
        t0 = time.perf_counter()

        tool = TOOLS_BY_NAME.get(name)
        if tool is None or not tool.method:
            err = f"Unknown or non-executable tool: {name}"
            return (
                {"type": "tool_result", "tool_use_id": tid, "content": err, "is_error": True},
                {"tool": name, "input": inp, "ok": False, "error": err, "duration_ms": 0},
            )

        # ClearLink tools: call via MCP server HTTP
        if tool.path.startswith("/mcp/proxy/"):
            # Extract tool name from path: /mcp/proxy/tools/{tool_name}
            mcp_tool_name = tool.path.split("/")[-1]
            ok, content = await call_clearlink_tool(mcp_tool_name, inp)
            if len(content) > MAX_TOOL_RESULT_CHARS:
                content = content[:MAX_TOOL_RESULT_CHARS] + "\n…[truncated]"
            dur = int((time.perf_counter() - t0) * 1000)
            logger.info("assistant tool=%s (clearlink) user=%s ok=%s dur=%dms", name, user.user_id, ok, dur)
            return (
                {"type": "tool_result", "tool_use_id": tid, "content": content, "is_error": not ok},
                {"tool": name, "input": inp, "ok": ok, "duration_ms": dur,
                 **({"error": content} if not ok else {})},
            )

        # OPA tools: call in-process
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
