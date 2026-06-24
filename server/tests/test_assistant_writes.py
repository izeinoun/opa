"""The confirm_action write gate.

Proves the assistant can mutate cases ONLY through a confirm → CONFIRMED round
trip, and never executes a write without it. No real LLM and no DB: we stub the
model to emit a confirm_action, and stub the actual write + guidance lookups.
"""
import asyncio
from types import SimpleNamespace

from app.services.assistant import agent as agent_mod
from app.services.assistant.agent import AssistantService


async def _collect(agen):
    return [e async for e in agen]


def _confirm_tooluse():
    tool = SimpleNamespace(
        type="tool_use", id="ca_1", name="confirm_action",
        input={"action": "accept_finding", "summary": "Accept the DET-09 finding",
               "params": {"finding_id": "f1", "case_id": 21}},
    )
    return SimpleNamespace(content=[tool], stop_reason="tool_use")


class _FakeMessages:
    async def create(self, **kwargs):
        return _confirm_tooluse()


class _FakeClient:
    messages = _FakeMessages()


def _svc(monkeypatch):
    monkeypatch.setattr(agent_mod, "_client", lambda: _FakeClient())
    svc = AssistantService(db=None, app=None)

    async def _schemas(_user):
        return []
    monkeypatch.setattr(svc, "_tool_schemas", _schemas)

    async def _guidance(_cid, _user):
        return {"remaining_summary": "Remaining: …", "next_action": None, "lifecycle": []}
    monkeypatch.setattr(svc, "_guidance_for", _guidance)
    return svc


def test_proposing_a_write_pauses_for_confirmation_and_executes_nothing(monkeypatch):
    svc = _svc(monkeypatch)
    executed = []

    async def _exec_write(spec, params, user):
        executed.append((spec, params))
        return True, "ok", 1
    monkeypatch.setattr(svc, "_execute_write", _exec_write)

    user = SimpleNamespace(user_id="u1")
    events = asyncio.run(_collect(svc.run(
        [{"role": "user", "content": "accept the DET-09 finding"}], user,
        context={"active_case_id": 21},
    )))
    types = [e["type"] for e in events]

    assert "awaiting_confirmation" in types, types
    ac = next(e for e in events if e["type"] == "awaiting_confirmation")
    assert ac["action"] == "accept_finding"
    assert ac["summary"] == "Accept the DET-09 finding"
    assert ac["preview"]  # a deterministic "what changes" line
    assert ac["tool_use_id"] == "ca_1"
    # NOTHING executed yet — the gate held.
    assert executed == []
    # No final/directive yet; the turn pauses.
    assert "final" not in types and "directive" not in types


def test_confirmed_resume_executes_the_write_and_shows_the_case(monkeypatch):
    svc = _svc(monkeypatch)
    executed = []

    async def _exec_write(spec, params, user):
        executed.append((spec.path, params))
        return True, "ok", 5
    monkeypatch.setattr(svc, "_execute_write", _exec_write)

    user = SimpleNamespace(user_id="u1")
    messages = [
        {"role": "user", "content": "accept the DET-09 finding"},
        {"role": "assistant", "content": [{
            "type": "tool_use", "id": "ca_1", "name": "confirm_action",
            "input": {"action": "accept_finding", "summary": "Accept",
                      "params": {"finding_id": "f1", "case_id": 21}}}]},
        {"role": "user", "content": [{
            "type": "tool_result", "tool_use_id": "ca_1", "content": "CONFIRMED"}]},
    ]
    events = asyncio.run(_collect(svc.run(messages, user, context={"active_case_id": 21})))
    types = [e["type"] for e in events]

    # The write ran exactly once, against the accept endpoint.
    assert len(executed) == 1
    assert executed[0][0].endswith("/findings/{finding_id}/accept")
    assert executed[0][1]["finding_id"] == "f1"
    # The user sees execution + the refreshed case + a final.
    assert "tool_end" in types and "directive" in types and "final" in types
    directive = next(e for e in events if e["type"] == "directive")
    assert directive["view"] == "case" and directive["params"]["case_id"] == 21
    final = next(e for e in events if e["type"] == "final")
    assert "guidance" in final


def test_cancelled_resume_executes_nothing(monkeypatch):
    svc = _svc(monkeypatch)
    executed = []

    async def _exec_write(spec, params, user):
        executed.append(params)
        return True, "ok", 1
    monkeypatch.setattr(svc, "_execute_write", _exec_write)

    user = SimpleNamespace(user_id="u1")
    messages = [
        {"role": "user", "content": "accept it"},
        {"role": "assistant", "content": [{
            "type": "tool_use", "id": "ca_1", "name": "confirm_action",
            "input": {"action": "accept_finding", "summary": "Accept",
                      "params": {"finding_id": "f1", "case_id": 21}}}]},
        {"role": "user", "content": [{
            "type": "tool_result", "tool_use_id": "ca_1", "content": "CANCELLED"}]},
    ]
    events = asyncio.run(_collect(svc.run(messages, user, context={"active_case_id": 21})))

    assert executed == []  # nothing ran
    final = next(e for e in events if e["type"] == "final")
    assert "won't" in final["message"].lower() or "not" in final["message"].lower()
