"""Render structured MCP tool results as PayGuard-styled, self-contained HTML.

Used by the MCP layer (mcp_mount / mcp_remote) ONLY — the in-app assistant keeps
getting JSON. For tools that return structured data (a case, a list of cases, a
member list), we return a complete HTML document so a connected client (Claude)
can render it as an HTML artifact instead of showing raw JSON.

`format_html(tool_name, data)` returns an HTML string for supported tools, or
None to fall back to JSON. `LEAD_IN` is prepended by the caller to nudge the
model to render the document as an artifact.
"""
from __future__ import annotations

from html import escape
from typing import Any

# Tools whose output we render as HTML (the rest fall back to JSON).
HTML_TOOLS = {"get_case", "search_cases", "search_members"}

# Instruction prepended to the HTML result so the model renders (not summarizes) it.
LEAD_IN = (
    "Render the HTML document below as an HTML artifact for the user — do not "
    "summarize, truncate, or rewrite it. After rendering, you may add a one-line "
    "note.\n\n"
)

# PayGuard look: pink brand (#FE017D), light slate UI, card + table layout.
_CSS = """
:root{--pg:#FE017D;--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--bg:#f8fafc;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:14px;line-height:1.45}
.wrap{max-width:860px;margin:0 auto;padding:24px}
.brand{display:flex;align-items:center;gap:8px;margin-bottom:16px}
.brand .dot{width:22px;height:22px;border-radius:6px;background:var(--pg)}
.brand b{font-size:15px}.brand span{color:var(--muted);font-size:12px}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:16px;
 box-shadow:0 1px 2px rgba(0,0,0,.04)}
h1{font-size:20px;margin:0 0 2px}h2{font-size:13px;text-transform:uppercase;letter-spacing:.05em;
 color:var(--muted);margin:0 0 10px}
.row{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}
.kv .l{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.kv .v{font-size:15px;font-weight:600;margin-top:2px}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:11px;font-weight:700;
 text-transform:uppercase;letter-spacing:.03em}
.b-high{background:#fee2e2;color:#b91c1c}.b-med{background:#fef3c7;color:#b45309}
.b-low{background:#e2e8f0;color:#475569}.b-pink{background:#fce7f3;color:#be185d}
.chip{display:inline-block;padding:2px 9px;border-radius:6px;background:#f1f5f9;color:#475569;
 font-size:12px;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em;
 padding:8px 10px;border-bottom:2px solid var(--line)}
td{padding:9px 10px;border-bottom:1px solid var(--line)}
tr:last-child td{border-bottom:0}
.mono{font-variant-numeric:tabular-nums}
.muted{color:var(--muted)}.right{text-align:right}
.excl{background:#fee2e2;color:#b91c1c;padding:1px 7px;border-radius:6px;font-size:11px;font-weight:700}
"""


def _doc(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_CSS}</style></head><body><div class=wrap>"
        '<div class=brand><span class=dot></span><b>PayGuard</b>'
        "<span>· Payment Integrity</span></div>"
        f"{body}</div></body></html>"
    )


def _money(v: Any) -> str:
    try:
        return "${:,.2f}".format(float(v))
    except (TypeError, ValueError):
        return "—"


def _g(d: dict, *path, default="—"):
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur not in (None, "") else default


def _prio_badge(p: str) -> str:
    cls = {"HIGH": "b-high", "MEDIUM": "b-med", "LOW": "b-low"}.get(str(p).upper(), "b-low")
    return f'<span class="badge {cls}">{escape(str(p or "—"))}</span>'


def _kv(label: str, value: str) -> str:
    return f'<div class=kv><div class=l>{escape(label)}</div><div class=v>{value}</div></div>'


def _case_detail(d: dict) -> str:
    claim = d.get("claim") or {}
    prov = claim.get("rendering_provider") or {}
    excl = ' <span class=excl>EXCLUDED</span>' if prov.get("is_excluded") else ""
    head = (
        '<div class=card><div class="row">'
        f'<div><h1>Case {escape(str(_g(d,"case_number")))}</h1>'
        f'<div class=muted>{escape(str(_g(d,"primary_detector_name")))} · {escape(str(_g(d,"lob")))}</div></div>'
        f'<div style="text-align:right">{_prio_badge(d.get("priority"))}'
        f'<div style="margin-top:6px"><span class=chip>{escape(str(_g(d,"status")))}</span></div></div>'
        '</div></div>'
    )
    metrics = (
        '<div class=card><div class=grid>'
        + _kv("Amount billed", f'<span class=mono>{_money(d.get("amount_billed"))}</span>')
        + _kv("Amount at risk", f'<span class=mono>{_money(d.get("amount_at_risk"))}</span>')
        + _kv("Likelihood", escape(str(_g(d, "posterior_score", default=_g(d, "likelihood_score")))))
        + _kv("Deadline", escape(str(_g(d, "deadline"))))
        + _kv("Opened", escape(str(_g(d, "opened_at"))))
        + _kv("Assignee", escape(str(_g(d, "assignee", "full_name"))))
        + "</div></div>"
    )
    provider = (
        '<div class=card><h2>Provider</h2><div class=grid>'
        + _kv("Name", escape(str(_g(prov, "name"))) + excl)
        + _kv("Specialty", escape(str(_g(prov, "specialty"))))
        + _kv("NPI", f'<span class=mono>{escape(str(_g(prov, "npi")))}</span>')
        + _kv("Risk tier", escape(str(_g(prov, "risk_tier"))))
        + "</div></div>"
    )
    member = (
        '<div class=card><h2>Member</h2><div class=grid>'
        + _kv("Name", escape(str(_g(claim, "member", "name"))))
        + _kv("Member ID", f'<span class=mono>{escape(str(_g(claim, "member", "member_id")))}</span>')
        + _kv("DOB", escape(str(_g(claim, "member", "dob"))))
        + _kv("Claim #", f'<span class=mono>{escape(str(_g(claim, "claim_number")))}</span>')
        + "</div></div>"
    )
    return _doc(f'Case {_g(d, "case_number")}', head + metrics + provider + member)


def _case_list(d: dict) -> str:
    items = d.get("items") or []
    rows = []
    for c in items:
        claim = c.get("claim") or {}
        rows.append(
            "<tr>"
            f'<td class=mono>{escape(str(_g(c,"case_number")))}</td>'
            f"<td>{_prio_badge(c.get('priority'))}</td>"
            f'<td><span class=chip>{escape(str(_g(c,"status")))}</span></td>'
            f'<td>{escape(str(_g(claim,"rendering_provider","name")))}</td>'
            f'<td>{escape(str(_g(claim,"member","name")))}</td>'
            f'<td class="right mono">{_money(c.get("amount_at_risk"))}</td>'
            f'<td class=mono>{escape(str(_g(c,"deadline")))}</td>'
            f'<td class=muted>{escape(str(_g(c,"primary_detector_name")))}</td>'
            "</tr>"
        )
    body = (
        f'<div class=card><div class="row" style="margin-bottom:10px">'
        f"<h1>Cases</h1><span class=chip>{len(items)} shown</span></div>"
        "<table><thead><tr><th>Case</th><th>Priority</th><th>Status</th><th>Provider</th>"
        "<th>Member</th><th class=right>At risk</th><th>Deadline</th><th>Detector</th></tr></thead>"
        f"<tbody>{''.join(rows) or '<tr><td colspan=8 class=muted>No cases.</td></tr>'}</tbody></table></div>"
    )
    return _doc("Cases", body)


def _member_list(d: dict) -> str:
    items = d.get("items") or []
    rows = []
    for m in items:
        name = f'{m.get("first_name","")} {m.get("last_name","")}'.strip() or "—"
        rows.append(
            "<tr>"
            f'<td class=mono>{escape(str(_g(m,"member_number")))}</td>'
            f"<td>{escape(name)}</td>"
            f'<td class=mono>{escape(str(_g(m,"date_of_birth")))}</td>'
            f'<td><span class=chip>{escape(str(_g(m,"lob")))}</span></td>'
            f'<td class=mono>{escape(str(_g(m,"coverage_effective_date")))}</td>'
            "</tr>"
        )
    body = (
        f'<div class=card><div class="row" style="margin-bottom:10px">'
        f"<h1>Members</h1><span class=chip>{len(items)} shown</span></div>"
        "<table><thead><tr><th>Member #</th><th>Name</th><th>DOB</th><th>LOB</th>"
        "<th>Coverage from</th></tr></thead>"
        f"<tbody>{''.join(rows) or '<tr><td colspan=5 class=muted>No members.</td></tr>'}</tbody></table></div>"
    )
    return _doc("Members", body)


def format_html(tool_name: str, data: Any) -> str | None:
    """Return a styled HTML doc for a supported tool, else None (→ JSON)."""
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
        return None  # any rendering issue → fall back to JSON
    return None
