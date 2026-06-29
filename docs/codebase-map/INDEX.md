# Codebase Map — INDEX (read me first)

> Machine-readable context map for the whole `/Users/issamzeinoun/claude/` suite (8 projects). Built for an AI coding agent's fast, precise lookup — not human prose. Generated 2026-06-29 via 8 parallel deep-profiling agents. **Re-verify against code before acting on any single line** (codebase drifts; this is a snapshot).

## Suite at a glance

| Project | Path | Role | Stack | Backend | Dev port | MCP |
|---------|------|------|-------|---------|----------|-----|
| **opa** (PayGuard) | `overcoding/opa` | HUB — post-pay + pre-pay backend & client | FastAPI Py + React TS | **own** | 8001 / 5174 | server + client |
| **clearlink** | `clearlink` | Clinical/diagnosis backend + MCP reference | Node/Express + better-sqlite3 / React | **own** | 8010 | server |
| **claimguard** | `claimguard` | Pre-pay review SPA (backend merged into OPA) | React19/Vite8 | → OPA | 5175 | — |
| **assistant** | `assistant` | Standalone assistant chat SPA | React18/Vite6 | → OPA | 5179 | — |
| **iam** | `iam` | Admin UI over OPA users (not real SSO) | React18/Vite6 | → OPA | 5177 | — |
| **siu** | `siu` | FWA/SIU investigations SPA | React18/Vite6 | → OPA | 5178 | — |
| **intake-portal** | `intake-portal` | PDF intake upload SPA | React19/Vite8 | → OPA | 5181 | — |
| **mock-provider-portal** | `overcoding/mock-provider-portal` | Test target for recoup-notice delivery | Node/Express | none | 3002 | — |

**One-liner:** OPA is the single backend; 5 React SPAs are thin clients of it; ClearLink is a second backend that OPA calls (MCP + REST) for clinical data; mock-provider-portal is a Playwright target. Prod = `*.penguinai.studio`, OPA = `payguard.penguinai.studio`.

## Files in this map

### Per-project profiles (`projects/`)
Full structural detail: routes, models, services, env, file:line refs.
- `projects/opa.md` (499 lines — the hub; read for any backend work)
- `projects/clearlink.md` (MCP system, connector framework, fuzzy search)
- `projects/claimguard.md` (+ merger gap analysis)
- `projects/assistant.md` · `projects/iam.md` · `projects/siu.md` · `projects/intake-portal.md` · `projects/mock-provider-portal.md`

### Action plan & history
- `ACTION-PLAN.md` — **sequenced remediation + enhancement roadmap** (verify → docs cleanup → P0/P1/P2 bugs → enhancements → guardrails). Followable checklist.
- `CHANGELOG.md` — **cross-cutting change history** since the map was created (incl. the 2026-06-29 identifier rename + master verification). Record suite-wide changes here.

### Cross-cutting (`cross-cutting/`)
- `dependency-graph.md` — who calls whom, ports, data flows, broken edges
- `mcp-inventory.md` — every MCP server/tool/transport/auth + gaps
- `data-models.md` — entity ownership, OPA vs ClearLink tables, ID-type mismatch, finding taxonomy
- `reuse-map.md` — duplication & extraction candidates (prioritized)
- `patterns-and-decisions.md` — conventions to follow + the decisions behind them
- `risks-and-bugs.md` — **consolidated live-bug hotlist (check first when debugging)**

## Task → where to look

| I need to… | Start at |
|------------|----------|
| Debug a broken feature | `cross-cutting/risks-and-bugs.md` then the project profile |
| Trace a request across services | `cross-cutting/dependency-graph.md` |
| Add/modify an MCP tool | `cross-cutting/mcp-inventory.md` + `projects/clearlink.md` (registry pattern) |
| Add a feature, maximize reuse | `cross-cutting/reuse-map.md` (find canonical impl first) |
| Touch detectors/scoring | `projects/opa.md` §DETECTORS + `patterns-and-decisions.md` §Detectors |
| Touch auth/identity | `patterns-and-decisions.md` §Identity + `projects/iam.md` |
| Member name search | [[member-fuzzy-search-pattern]] (memory) + `clearlink.md` §MCP |
| Work on ClaimGuard merger | `projects/claimguard.md` MERGER_TODO |
| Change schema | `patterns-and-decisions.md` §Data (server_default rule, alembic) |
| Anything LLM/model-id | `claude-api` skill (don't guess model IDs) |

## Top facts to never forget (the gotchas that cause bugs)

1. **OPA migrations are DISABLED at startup** (`main.py:106-108`) — schema may not build despite CLAUDE.md claiming it does.
2. **`X-User-Id` is trusted, not auth** — never expose OPA publicly without a real gate.
3. **Detector orchestrator swallows exceptions** — "missing findings" = check logs for detector errors first.
4. **ClearLink tools are DB-registered** (`agent_tools` rows) — adding code isn't enough (that's why `search_members` is uncallable).
5. **Assistant write-gate**: agent mutates ONLY via `ask_user`/`present_view`/`confirm_action`.
6. **API URLs are committed in `appUrls.ts`, not env** — change + rebuild.
7. **Single DB, `pipeline_mode` discriminator** (post_pay/pre_pay); FWA is a disposition, not a mode.
8. **`server_default` rule** — NOT NULL cols omitted by raw seeds need it on the model.
9. **Doc≠impl drift is significant** — 23 detectors not 6, `CG-BASIC-V1` not `AI-CLAUDE-V1`, etc. Verify code.
10. **OPA and ClearLink have SEPARATE member DBs** — bridged only via add-diagnosis seam.

## Maintenance

When code changes materially, update the relevant `projects/*.md` and the cross-cutting file, and bump facts here. Record non-obvious decisions in persistent memory (`MEMORY.md`, `type: project`/`feedback`). This map was generated from a snapshot — stale lines are expected over time.
