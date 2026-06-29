# Reuse Map — duplication & extraction candidates

> Goal: when adding/fixing, reuse the canonical impl instead of forking. Each row = a capability duplicated across projects, the canonical location, and the extraction target.

## Backend logic duplication (OPA Python ↔ ClearLink Node)

| Capability | Canonical | Duplicate(s) | Action |
|------------|-----------|--------------|--------|
| **LLM fuzzy member search** (roster→Claude→IDs) | ClearLink `mcp/toolExecutor.js:11` `fuzzySearchMembers` + `routes/intake.js:27` `findMemberMatches` (exact/fuzzy layer) | OPA `services/intake_matching_service.py` | Single pattern (see [[member-fuzzy-search-pattern]]). Keep both impls in sync; treat ClearLink as reference. Do NOT add SQL-LIKE name search. |
| **PDF intake → extract → persist** | (parallel impls) | ClearLink `routes/intake.js` + `services/extractionPipeline` ↔ OPA `services/prepay_intake_service.py` + `ai_service.py` | Two full implementations of the same flow. When changing intake, change both or consolidate behind OPA. |
| **Claude/LLM prompts (analyze/extract/summary)** | OPA `ai_service.py` (ported verbatim from ClaimGuard) | ClaimGuard original (retired backend) | OPA is now canonical; delete ClaimGuard backend (Phase 3). |
| **Connector framework** (http/sql/mock registry) | ClearLink `agents/connectors/executor.js` `runConnector` + `agent_tools` table | OPA `services/connector_service.py` ("adapted from clearlink/server/agents") | Two registries (`agent_tools` vs `connectors`). Keep semantics aligned. |
| **X12 835/837 parsing** | OPA `edi_parser*.py` | likely mirrors ClearLink X12 ingest | Verify before editing either. |
| **ICD-10 validation / HCC lookup** | ClearLink `utils/claudeClient.js` + `icd_hcc_lookup` | OPA code seeds (`seed/seed_codes.py`) | Different mechanisms (LLM vs table). |
| **markdown → PDF + generic LLM doc-gen** | OPA `utils/markdown_pdf.py` + `services/document_generation_service.py` | — | Already centralized; reuse for any new doc output. |
| **Playwright provider-portal upload** | OPA `services/provider_portal_service.py` (Python) | mock-provider-portal `playwright-upload.js` (Node) | Two impls of same browser flow; Node one is `headless:false` (CI-unsafe). |
| **Two Claude clients (ClearLink internal)** | — | ClearLink `utils/claudeClient.js` (SDK, opus-4-8) vs axios calls (sonnet-4-6) in `toolExecutor.js`/`intake.js`/`charlie.js` | Consolidate to one client + one model config. |

## Frontend component duplication (5 React SPAs + OPA client)

| Component / pattern | Canonical-ish | Copied into | Extraction target |
|---------------------|---------------|-------------|-------------------|
| **`AssistantPanel` / chat SSE** (SSE parse, `ask_user` flow, `awaiting_confirmation` write-gate, `sanitizeAssistantOutput`) | OPA `client/src/components/assistant/AssistantPanel.tsx` | standalone `assistant/.../AssistantChat.tsx`, `siu`, `claimguard` `AssistantPanel.tsx` | Shared `useAssistantChat` hook (design doc defers this) |
| **`DemoGate`** (HMAC token login wall) | OPA `client/src/components/common/DemoGate.tsx` | iam, siu, claimguard, assistant, intake | Shared auth package |
| **`ActorPicker` + `X-User-Id`** identity selector | OPA client | iam, siu, claimguard, assistant | Shared package; note localStorage key differs per app (`iam.actorUserId`, `siu.currentUserId`, `claimguard.currentUserId`, `assistant_user_id`) |
| **`AppSwitcher`** (cross-app nav) | OPA `client/src/components/common/AppSwitcher.tsx` | iam, siu, claimguard, assistant, intake | Shared package; URL source inconsistent (env vars vs committed `appUrls.ts`) |
| **`appUrls.ts`** hardcoded URL map | (pattern repeated) | ALL frontends | Centralize; prod hosts = `*.penguinai.studio` |
| **CORS origin lists** | OPA `config.py` `_DEV/_PROD_CORS_ORIGINS` | mirrored in each frontend's appUrls | Single source |
| **`PdfHighlightViewer`** (highlight + stopwords) | ClaimGuard frontend | siu (copied) | Shared package |
| **`NoAccessGate`** (`user.apps.includes(app)`) | (pattern) | siu, claimguard | Shared package |
| **`authService.ts`** (cookie + BroadcastChannel) | — | siu, iam(absent), claimguard, assistant — **DEAD CODE everywhere except assistant which uses cookie JWT** | DELETE dead copies; they conflict with the live Bearer-token gate |

## Highest-value extractions (priority order)

1. **Shared frontend auth/identity package** (`DemoGate` + `ActorPicker` + `NoAccessGate` + `appUrls`) — touches all 5 SPAs, eliminates the biggest drift surface, and consolidates the X-User-Id security boundary in one place.
2. **`useAssistantChat` hook** — 4 copies of fragile SSE/tool-call parsing.
3. **Consolidate member fuzzy search** behind one service (OPA) and have ClearLink call it, or vice-versa — avoids two prompt variants drifting.
4. **One ClearLink Claude client + model config** — removes the sonnet/opus default conflict.
5. **Delete dead `authService.ts` copies** — pure liability.
