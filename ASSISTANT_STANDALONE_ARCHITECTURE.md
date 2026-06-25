# Standalone Assistant Backend Architecture (Next Phase)

## Overview

This document outlines the vision for extracting the assistant backend into a **totally standalone application** that serves as an orchestration layer connecting PayGuard, ClearLink, and other healthcare applications.

**Current State (Phase 1):** Assistant backend is embedded in OPA/PayGuard project, with direct database access and tight coupling.

**Future State (Phase 2+):** Assistant backend is a standalone service that connects to PayGuard, ClearLink, and other systems via MCP (Model Context Protocol) or clean APIs.

## Vision

The standalone assistant backend becomes a **multi-system orchestration hub**:

```
┌─────────────────────────────────────┐
│   Standalone Assistant Backend      │
│  (Independent Microservice)         │
├─────────────────────────────────────┤
│ • Dynamic Tool Discovery            │
│ • System Prompt Builder             │
│ • Conversation Management           │
│ • Multi-System Orchestration        │
└────────┬────────────────────────────┘
         │
    ┌────┴────┬────────┬─────────┬──────────┐
    │          │        │         │          │
    ▼          ▼        ▼         ▼          ▼
┌────────┐ ┌────────┐ ┌────┐ ┌──────┐ ┌────────┐
│PayGuard│ │ClearLink│ │SIU │ │Future│ │[New]   │
│        │ │        │ │    │ │Apps  │ │System  │
└────────┘ └────────┘ └────┘ └──────┘ └────────┘
```

## Benefits

### 1. Clean Separation of Concerns
- Assistant logic decoupled from PayGuard domain logic
- Each system can evolve independently
- Easier testing and maintenance
- Clear API boundaries

### 2. Multi-System Integration Hub
- Assistant orchestrates across all connected healthcare systems
- All external integrations flow through the assistant
- Single point of tool discovery
- Easy to add new data sources (SIU, EHR integrations, etc.)

### 3. Independent Scaling & Deployment
- Assistant scales separately from PayGuard
- Deploy assistant updates without affecting PayGuard
- Different SLAs and resource requirements possible
- Easier to operate (dedicated observability, metrics, alerts)

### 4. Tool Discovery & Dynamic Integration
- Each connected system exposes tools via MCP
- Assistant dynamically discovers available tools from ALL systems
- No hardcoding of tool lists in prompts
- New integrations add automatically

### 5. Reusability & Multi-Frontend
- Same backend serves:
  - OPA web UI (PayGuard)
  - ClaimGuard UI
  - Mobile apps (future)
  - CLI integrations
  - Third-party integrations
- Single source of truth for assistant logic

### 6. Team Ownership & Governance
- Dedicated team can own the assistant service
- Different deployment cadence from PayGuard
- Clear API contract between systems
- Easier onboarding of new integrations

## Current State (Embedded)

```
OPA (PayGuard + ClaimGuard) Backend
├── Assistant Service
│   ├── System Prompt (hardcoded tool list)
│   ├── Tool Execution Layer
│   └── OPA Tools (in-process)
│
├── PayGuard Services
│   └── Direct database access
│
├── ClearLink MCP Client
│   └── External HTTP calls
│
└── [Other integrations scattered across codebase]
```

**Issues:**
- Tool list hardcoded in prompt (now fixed with dynamic discovery, but still embedded)
- Assistant tightly coupled to OPA implementation
- Hard to add new systems without modifying OPA
- Difficult to scale or version independently

## Proposed State (Standalone)

```
┌─────────────────────────────────────────┐
│  Standalone Assistant Backend Service   │
│  (New independent application)          │
├─────────────────────────────────────────┤
│                                         │
│  Routes:                                │
│  ├── POST /api/assistant/chat           │
│  ├── POST /api/assistant/chat/stream    │
│  ├── GET /api/assistant/tools           │
│  └── [Admin endpoints]                  │
│                                         │
│  Core Components:                       │
│  ├── System Prompt Builder              │
│  │   └── Dynamic tool discovery         │
│  ├── Message History Manager            │
│  ├── Tool Executor                      │
│  └── Multi-System Orchestrator          │
│                                         │
│  MCP Clients:                           │
│  ├── PayGuard MCP Client                │
│  ├── ClearLink MCP Client               │
│  ├── SIU MCP Client                     │
│  └── [Pluggable for new systems]        │
│                                         │
└─────────────────────────────────────────┘
         ↓              ↓            ↓
    ┌────────┐    ┌─────────┐  ┌────────┐
    │PayGuard│    │ClearLink│  │SIU/etc │
    └────────┘    └─────────┘  └────────┘
```

**Architecture:**
- Independent Python/FastAPI service (same as OPA, for consistency)
- Connects to each system via MCP or clean REST APIs
- Dynamic tool discovery from all connected systems
- Stateless message processing (conversation history stored in frontend or DB)
- Configurable system integrations (environment-based activation)

## Implementation Phases

### Phase 2a: Prepare (Low Risk)
1. Document all assistant APIs currently in OPA
2. Define MCP interface that PayGuard will expose
3. Create clean API boundary between PayGuard and Assistant
4. Add integration tests for the API boundary
5. No code changes to OPA yet

### Phase 2b: Extract (Medium Risk)
1. Create new `assistant` project (separate Git repo or monorepo module)
2. Copy assistant service code from OPA
3. Replace OPA direct calls with MCP calls to PayGuard
4. Test extensively with both embedded and standalone modes
5. Deploy standalone in staging

### Phase 2c: Switch (Low Risk After 2b)
1. Flip traffic from embedded to standalone assistant
2. Keep embedded assistant as fallback
3. Monitor performance and errors closely
4. Once stable, deprecate embedded assistant in OPA

### Phase 3+: Add New Systems
1. Define MCP for SIU system
2. Register SIU tools in assistant
3. Add SIU examples to system prompt
4. No changes to PayGuard or ClearLink needed

## Technical Details

### Data Flow
```
User Message
    ↓
[Assistant Backend]
    ↓
1. Fetch available tools from all connected MCP servers
2. Build system prompt with dynamic tool list
3. Call Claude with message + tools
4. Execute tools (remote calls to each system)
5. Return assistant response
```

### System Integrations (Pluggable)

Each system registers via environment configuration:

```yaml
ASSISTANT_INTEGRATIONS:
  - name: payguard
    type: mcp
    url: http://payguard:8001/mcp
    api_key: ${PAYGUARD_MCP_KEY}
    
  - name: clearlink
    type: mcp
    url: http://clearlink:8010/mcp
    api_key: ${CLEARLINK_MCP_KEY}
    
  - name: siu
    type: mcp
    url: http://siu:8020/mcp
    api_key: ${SIU_MCP_KEY}
    enabled: false  # Will enable in Phase 3
```

### Tool Discovery Flow

```python
async def _get_available_tools():
    tools = []
    for integration in INTEGRATIONS:
        if integration.enabled:
            remote_tools = await fetch_tools_from_mcp(integration)
            tools.extend(remote_tools)
    
    # System prompt built with current tools
    return build_system_prompt(tools)
```

## Migration Strategy

### Backward Compatibility
- Embedded assistant in OPA stays functional during transition
- Both can exist side-by-side for A/B testing
- Frontend can switch between them via feature flag

### Monitoring & Safety
- New standalone assistant proxied through OPA initially (for auth/rate-limiting)
- Gradual traffic shift (5% → 25% → 50% → 100%)
- Rollback plan: flip traffic back to embedded assistant
- Detailed metrics on tool execution, errors, latency

### Dependencies
- PayGuard must expose MCP interface (/mcp/tools, /mcp/tools/{name}/call)
- ClearLink MCP already exists (port 8010)
- SIU system: will need MCP implementation when added

## Trigger Conditions for Phase 2

Start this refactor when:
1. ✅ ClearLink MCP is stable and tested (Done)
2. ✅ Dynamic tool discovery is working in embedded assistant (Done)
3. ⏳ Third system (SIU or other) is being integrated
4. ⏳ Assistant deployment needs differ from PayGuard (scale, versioning, team)
5. ⏳ Team bandwidth is available for careful migration

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Network latency between services | Cache tool schemas, monitor SLAs, use fast MCP protocol |
| Auth/security across systems | Use API keys, mTLS, network isolation in production |
| Version mismatch between systems | Semantic versioning of MCP interfaces, compatibility tests |
| Single point of failure | Assistant HA setup, fallback to embedded version |
| Operational complexity | Clear deployment playbooks, monitoring dashboards |

## Success Metrics

- ✅ Tool discovery works for 3+ systems without hardcoding
- ✅ Assistant response latency <2s (P95)
- ✅ 99.9% uptime SLA
- ✅ Easy to add new systems (< 1 day integration)
- ✅ Can deploy assistant independently from PayGuard
- ✅ Frontend can support multiple assistant backends (embedded/standalone)

## Related Documents

- `CLAUDE.md` — Current architecture and setup
- `MCP.md` — MCP protocol and implementation
- `ASSISTANT_CLEARLINK_SETUP.md` — ClearLink integration (current Phase 1)

## Next Steps (Post Phase 1)

1. Review this plan with team
2. Plan Phase 2a scope and timeline
3. Create `ASSISTANT_STANDALONE_ROADMAP.md` with detailed milestones
4. Begin Phase 2a (API definition, MCP interface preparation)

---

**Status:** Vision document for Phase 2+ (not active yet)  
**Last Updated:** 2026-06-25  
**Owner:** Architecture team  
**Phase:** Future enhancement
