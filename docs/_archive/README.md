# Archived docs (moved 2026-06-29, Phase 1 doc hygiene)

These were moved out of the repo root to stop stale content from polluting AI context. **Nothing is deleted** — kept here for history. Purge when confident they're obsolete. Canonical info now lives in `CLAUDE.md` + `docs/codebase-map/`.

| File | Why archived |
|------|--------------|
| `ASSISTANT_CLEARLINK_SETUP.md` | "Integration Complete ✅" status note — shipped; see `docs/codebase-map/cross-cutting/mcp-inventory.md` |
| `ASSISTANT_OUTPUT_SANITIZATION.md` | Shipped safeguard notes — behavior now in code (`sanitizeAssistantOutput`) |
| `CROSS_APP_SSO_COMPLETE.md` | "Implementation Complete ✅" — superseded; real auth status in `docs/codebase-map/cross-cutting/patterns-and-decisions.md` §Identity |
| `IMPLEMENTATION_CHECKLIST.md` | Cross-app auth checklist — completed |
| `IMPLEMENTATION_PLAN_add_diagnosis.md` | Add-diagnosis tool plan — shipped (memory: add_diagnosis_tool, completed 2026-06-25) |
| `MCP_INTEGRATION_SUMMARY.md` | Superseded by `docs/codebase-map/cross-cutting/mcp-inventory.md` |
| `REEVALUATE_RULES_TOOL.md` | Shipped feature note (commit e98487e) |
| `SECURITY_RESTORED.md` | "Fully Restored" status note — point-in-time |
| `SOLUTION_SUMMARY.md` | Bearer-token solution summary — superseded by `API_KEY_SYSTEM.md` (kept in `docs/reference/`) |
| `FOUR_LAYER_PATTERN_*.{txt,md}` | 3 scratch variants of the same evidence-verification sketch; 0 code refs |
| `Vanessa_Guerrero_Surgical_Note_20241220.txt` | One-off test fixture; 0 code refs |
| `UPDATED.csv` | 83k-line NPI provider dump; untracked, 0 code refs — possible seed source, retained just in case |

Still-valid feature/plan docs were moved to `docs/reference/` instead: API_KEY_SYSTEM, CROSS_APP_AUTH, ENVIRONMENT_INDICATOR, PAYGUARD_CLAIMGUARD_COMPATIBILITY, ASSISTANT_STANDALONE_ARCHITECTURE, PERSISTENT_ASSISTANT_PLAN.
