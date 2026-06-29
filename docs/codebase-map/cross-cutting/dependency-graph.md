# Dependency Graph — service-to-service calls & data flows

> Source of truth = single OPA FastAPI backend (`:8001`). All 5 sibling React SPAs are thin clients of it. ClearLink is the only OTHER backend; OPA ↔ ClearLink is the cross-backend seam.

## Topology (who calls whom)

```
                        ┌─────────────────────────── Anthropic Claude API ──────────────────────────┐
                        │ (ANTHROPIC_API_KEY)                                                        │
                        ▲                                                ▲                            │
   React SPAs           │                                                │                            │
   ───────────          │  OPA backend (FastAPI :8001) ─── MCP /mcp ───► │  ClearLink (Node :8010)    │
   claimguard :5175 ──┐ │   server/app/                  X-API-Key       │  server/  (better-sqlite3) │
   assistant  :5179 ──┤ │   - routes/ services/ dao/     CLEARLINK_      │  /mcp (JSON-RPC)           │
   iam        :5177 ──┼─┴─►- detectors/ ml/              MCP_API_KEY     │  + REST /api/clearlink/    │
   siu        :5178 ──┤    - assistant/ (agent)  ────────REST add-diag──►│    add-diagnosis (NO AUTH) │
   intake     :5181 ──┘    - mcp_mount/_server/_remote   ◄──────────────┘  TELNYX / EMAILJS          │
   opa client :5174 ──►        │      │                                                               │
                               │      └── Playwright subprocess ──► mock-provider-portal (Node :3002) │
                               │           provider_portal_service.py                                 │
                               └── EmailJS (EMAILJS_*)                                                │
```

## Edges (directed, with mechanism + auth + code ref)

| From | To | Mechanism | Auth | Code ref (caller) |
|------|----|-----------|------|-------------------|
| claimguard SPA | OPA :8001 | Axios REST + SSE | `opa_demo_token` Bearer + `X-User-Id` | `claimguard/frontend/src/api/client.ts` |
| assistant SPA | OPA :8001 | REST + `POST /api/assistant/chat/stream` SSE | cookie JWT + `assistant_user_id` | `assistant/frontend/src/config/appUrls.ts` |
| iam SPA | OPA :8001 | Axios REST | `opa_demo_token` Bearer + `X-User-Id` + `actor_user_id` qparam | `iam/frontend/src/config/appUrls.ts:14` |
| siu SPA | OPA :8001 | Axios REST (TanStack Query) | `opa_demo_token` Bearer + `X-User-Id` | `siu/frontend/src/config/appUrls.ts:14-21` |
| intake-portal SPA | OPA :8001 | Axios multipart `POST /api/file-intake/upload` | `opa_demo_token` Bearer + `intake`-role `X-User-Id` | `intake-portal/src/api.ts` |
| opa client SPA | OPA :8001 | Axios REST + SSE | JWT/`X-User-Id` | `client/src/...` |
| OPA backend | Anthropic | SDK `messages.create` | `ANTHROPIC_API_KEY` | `server/app/services/ai_service.py:355`; `assistant/agent.py` |
| OPA backend | ClearLink MCP | JSON-RPC over HTTP `/mcp` | `X-API-Key` = `CLEARLINK_MCP_API_KEY` | `assistant/clearlink_integration.py:21`; `clearlink_proxy.py:48` |
| OPA backend | ClearLink REST | `POST /api/clearlink/add-diagnosis` | Bearer `CLEARLINK_API_KEY` (**route ignores it — no auth**) | `clearlink_proxy.py` |
| OPA backend | mock-provider-portal :3002 | Python Playwright (browser drive) | session `provider`/`password` | `server/app/services/provider_portal_service.py` |
| OPA backend | EmailJS | REST | `EMAILJS_*` | `server/app/...` (send_email MCP tool) |
| ClearLink | Anthropic | axios + SDK (TWO clients) | `ANTHROPIC_API_KEY` | `mcp/toolExecutor.js:37`, `routes/intake.js:64`, `agents/charlie.js:21`, `utils/claudeClient.js` |
| ClearLink | Telnyx / EmailJS | REST | `TELNYX_*` / `EMAILJS_*` | per-connector |

## Ports / hosts cheat-sheet

| Service | Dev port | Prod host (penguinai.studio) |
|---------|----------|------------------------------|
| OPA backend | 8001 | payguard.penguinai.studio |
| OPA client | 5174 | payguard.penguinai.studio |
| ClearLink | 8010 | (own Railway) |
| claimguard | 5175 | claimguard.penguinai.studio |
| iam | 5177 | (Railway PORT) |
| siu | 5178 | siu.penguinai.studio |
| assistant | 5179 | assistant.penguinai.studio |
| intake-portal | 5181 (README says 5180 — stale) | (Railway PORT, default 3000) |
| mock-provider-portal | 3002 | n/a (test target) |

## Key data flows

1. **Pre-pay claim intake (ClaimGuard pipeline):** intake-portal/claimguard SPA → `POST /api/file-intake/upload?category=claim_pdf` → `file_intake.py:297` delegates to `prepay_intake_service.ingest_extracted_claim` → `ai_service` extracts via Claude → rows on `claims`(pipeline_mode=pre_pay)+`claim_lines`+`documents`. **Rejects unknown members/providers** (reference-data-first).
2. **Post-pay audit (PayGuard pipeline):** seeded/intake claims → detector orchestrator → `findings` → case creation → posterior/priority → worklist → letter → recoupment → (Playwright) mock-provider-portal upload.
3. **Assistant turn:** assistant SPA or OPA client `AssistantPanel` → `POST /api/assistant/chat/stream` (SSE) → `assistant/agent.py` loop → calls OPA read-tools (tools.py) + ClearLink MCP tools → writes ONLY via `ask_user`/`present_view`/`confirm_action` UI tools.
4. **Diagnosis add (OPA↔ClearLink seam):** assistant decides → OPA `clearlink_proxy` → ClearLink `POST /api/clearlink/add-diagnosis` → ClearLink DB; this is the intended bidirectional seam (see [[clearlink-tool-architecture]] memory: ClearLink tools should flow only to ClearLink).

## Broken / missing edges (troubleshooting hotlist)

> Updated after Phase 0 verification (2026-06-29).

- ✅ claimguard `DenialPackageModal.tsx:42` / `ApprovalExportModal.tsx:24` → wrong path + no auth headers → **broken export (FE-only)**. Backend exists: `prepay_claims.py:1261/1300`, full path `/api/prepay/claims/{id}/export/denial|approval` (needs `claimguard` app grant).
- ✅ claimguard provider-message / evidence-search / ZIP-export → verify per-endpoint; some unported (ZIP export for denial/approval DOES exist now).
- ✅ claimguard `scripts/prewarm.sh` → targets retired **:8002**.
- ❌ ~~siu `GET /api/siu/dashboard` 404~~ → PHANTOM: endpoint exists in `siu_dashboard.py` (registered `main.py:176`). If FE fails, it's a 403 app-grant / trailing-slash issue.
- ❌ ~~ClearLink `search_members` uncallable~~ → PHANTOM: enabled row + LLM-fuzzy interception; it works.
