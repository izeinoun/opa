"""The present_view → directive channel (interactive cockpit).

Proves that when the model calls the `present_view` tool, the assistant agent:
  1. emits a {"type":"directive", ...} event carrying the view + params, and
  2. still terminates with a `final`, AND
  3. leaves a VALID message history — the assistant tool_use is resolved by a
     synthetic tool_result, so the next turn's API call won't reject a dangling
     tool_use.

No real LLM and no DB: the present_view path touches neither (we stub the client
and the tool-schema lookup).
"""
import asyncio
from types import SimpleNamespace

from app.services.assistant import agent as agent_mod
from app.services.assistant.agent import AssistantService, _fast_directive


def _u(text):
    return [{"role": "user", "content": text}]


def test_fast_directive_matches_nav_commands():
    # Unambiguous navigational phrasings short-circuit to a directive.
    assert _fast_directive(_u("open case 1")) == {
        "view": "case", "params": {"case_id": 1}, "caption": "Case 1"}
    assert _fast_directive(_u("show case 19"))["params"] == {"case_id": 19}
    assert _fast_directive(_u("my cases"))["view"] == "worklist"
    assert _fast_directive(_u("show my assigned cases"))["params"] == {"scope": "mine"}
    assert _fast_directive(_u("my dashboard"))["view"] == "my_dashboard"


def test_fast_directive_ignores_real_questions():
    # A narrow factual question must NOT be hijacked into a view.
    assert _fast_directive(_u("what CPTs are on case 1?")) is None
    assert _fast_directive(_u("how is the recovery pipeline doing?")) is None
    # tool_result continuations (list content) are skipped.
    assert _fast_directive([{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": "y"}]}]) is None


def _fake_response():
    # A turn where the model emits a short text + a present_view tool call.
    text = SimpleNamespace(type="text", text="Here are your cases.")
    tool = SimpleNamespace(
        type="tool_use",
        id="tu_1",
        name="present_view",
        input={"view": "worklist", "params": {"scope": "mine"}, "caption": "Your cases"},
    )
    return SimpleNamespace(content=[text, tool], stop_reason="tool_use")


class _FakeMessages:
    async def create(self, **kwargs):
        return _fake_response()


class _FakeClient:
    messages = _FakeMessages()


async def _collect(agen):
    return [e async for e in agen]


def test_present_view_emits_directive(monkeypatch):
    monkeypatch.setattr(agent_mod, "_client", lambda: _FakeClient())

    svc = AssistantService(db=None, app=None)

    async def _schemas(_user):
        return []

    monkeypatch.setattr(svc, "_tool_schemas", _schemas)

    user = SimpleNamespace(user_id="u1")
    # A phrasing the deterministic fast-path does NOT match, so the (mocked)
    # model path is exercised: it returns a present_view tool call.
    messages = [{"role": "user", "content": "what should I work on next?"}]
    events = asyncio.run(_collect(svc.run(messages, user)))
    types = [e["type"] for e in events]

    # 1. a directive carrying the view + params
    assert "directive" in types, types
    directive = next(e for e in events if e["type"] == "directive")
    assert directive["view"] == "worklist"
    assert directive["params"] == {"scope": "mine"}
    assert directive["caption"] == "Your cases"

    # 2. the turn still finishes cleanly
    assert "final" in types

    # 3. the history is valid — the tool_use is resolved by a tool_result
    final = next(e for e in events if e["type"] == "final")
    last = final["messages"][-1]
    assert last["role"] == "user"
    assert last["content"][0]["type"] == "tool_result"
    assert last["content"][0]["tool_use_id"] == "tu_1"
