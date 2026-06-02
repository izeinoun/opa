"""Render structured MCP tool results as clean Markdown.

Used by the MCP layer (mcp_mount) ONLY — the in-app assistant keeps getting JSON.
Markdown is Claude's native output format, so it relays these faithfully and
renders them as formatted tables/cards in-chat (reliable, token-light) — unlike
raw HTML, which the model just re-summarizes.

`format_markdown(tool_name, data)` returns Markdown for supported tools, else
None (→ JSON fallback).
"""
from __future__ import annotations

from typing import Any

# Tools whose output we render as Markdown (the rest fall back to JSON).
MD_TOOLS = {"get_case", "search_cases", "search_members"}

_PRIO = {"HIGH": "🔴 HIGH", "MEDIUM": "🟠 MEDIUM", "LOW": "⚪ LOW"}


def _prio(p: Any) -> str:
    return _PRIO.get(str(p).upper(), str(p or "—"))


def _money(v: Any) -> str:
    try:
        return "${:,.2f}".format(float(v))
    except (TypeError, ValueError):
        return "—"


def _pct(v: Any) -> str:
    try:
        f = float(v)
        return f"{f * 100:.1f}%" if f <= 1 else f"{f:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _cell(v: Any) -> str:
    """Escape a value for a Markdown table cell."""
    s = "—" if v in (None, "") else str(v)
    return s.replace("|", "\\|").replace("\n", " ")


def _g(d: dict, *path, default=None):
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur not in (None, "") else default


def _case_detail(d: dict) -> str:
    claim = d.get("claim") or {}
    prov = claim.get("rendering_provider") or {}
    excl = " · ⚠️ EXCLUDED" if prov.get("is_excluded") else ""
    lines = [
        f'## Case {_g(d, "case_number", default="—")} · {_prio(d.get("priority"))} · `{_g(d, "status", default="—")}`',
        f'**{_g(d, "primary_detector_name", default="—")}** · {_g(d, "lob", default="—")}',
        "",
        "| Field | Value |",
        "|---|---|",
        f'| Amount billed | {_money(d.get("amount_billed"))} |',
        f'| Amount at risk | {_money(d.get("amount_at_risk"))} |',
        f'| Overpayment likelihood | {_pct(_g(d, "posterior_score", default=_g(d, "likelihood_score")))} |',
        f'| Deadline | {_g(d, "deadline", default="—")} |',
        f'| Opened | {_g(d, "opened_at", default="—")} |',
        f'| Assignee | {_g(d, "assignee", "full_name", default="—")} |',
        "",
        f'**Provider:** {_g(prov, "name", default="—")} · {_g(prov, "specialty", default="—")} · '
        f'NPI {_g(prov, "npi", default="—")} · Risk Tier {_g(prov, "risk_tier", default="—")}{excl}',
        "",
        f'**Member:** {_g(claim, "member", "name", default="—")} · {_g(claim, "member", "member_id", default="—")} · '
        f'DOB {_g(claim, "member", "dob", default="—")} · Claim {_g(claim, "claim_number", default="—")}',
    ]
    return "\n".join(lines)


def _case_list(d: dict) -> str:
    items = d.get("items") or []
    head = [
        f"**Cases** ({len(items)} shown)",
        "",
        "| Case | Priority | Status | Provider | Member | At risk | Deadline | Detector |",
        "|---|---|---|---|---|---:|---|---|",
    ]
    rows = []
    for c in items:
        claim = c.get("claim") or {}
        rows.append(
            f'| {_cell(_g(c, "case_number"))} | {_prio(c.get("priority"))} | {_cell(_g(c, "status"))} '
            f'| {_cell(_g(claim, "rendering_provider", "name"))} | {_cell(_g(claim, "member", "name"))} '
            f'| {_money(c.get("amount_at_risk"))} | {_cell(_g(c, "deadline"))} '
            f'| {_cell(_g(c, "primary_detector_name"))} |'
        )
    if not rows:
        rows = ["| _no cases_ | | | | | | | |"]
    return "\n".join(head + rows)


def _member_list(d: dict) -> str:
    items = d.get("items") or []
    head = [
        f"**Members** ({len(items)} shown)",
        "",
        "| Member # | Name | DOB | LOB | Coverage from |",
        "|---|---|---|---|---|",
    ]
    rows = []
    for m in items:
        name = f'{m.get("first_name", "")} {m.get("last_name", "")}'.strip() or "—"
        rows.append(
            f'| {_cell(_g(m, "member_number"))} | {_cell(name)} | {_cell(_g(m, "date_of_birth"))} '
            f'| {_cell(_g(m, "lob"))} | {_cell(_g(m, "coverage_effective_date"))} |'
        )
    if not rows:
        rows = ["| _no members_ | | | | |"]
    return "\n".join(head + rows)


def format_markdown(tool_name: str, data: Any) -> str | None:
    """Return Markdown for a supported tool, else None (→ JSON)."""
    if not isinstance(data, dict):
        return None
    try:
        if tool_name == "get_case":
            return _case_detail(data)
        if tool_name == "search_cases":
            return _case_list(data)
        if tool_name == "search_members":
            return _member_list(data)
    except Exception:
        return None
    return None
