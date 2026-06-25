# API Key System & Bearer Token Integration

## Overview

The OPA backend now supports multiple authentication methods:

1. **JWT Tokens** — From user login (expires in 12 hours)
2. **API Keys** — For external services and MCP integration (no expiry or custom expiry)
3. **X-User-Id Header** — For internal service-to-service calls
4. **httpOnly Cookies** — From cross-app sessions

All of these work as **Bearer tokens** in the `Authorization` header:
```
Authorization: Bearer <jwt_token>
Authorization: Bearer <api_key>
```

---

## How It Works Now (The Fix)

### Problem We Solved

The OPA Assistant (inside PayGuard) was getting 401 errors when calling tools because:
1. The assistant backend was making in-process calls with `X-User-Id` header
2. The middleware only checked for Bearer tokens or cookies
3. Result: tools got 401, assistant failed

### The Solution: Multi-Method Auth

The updated `middleware/auth.py` now checks (in order):

```python
1. Authorization header (Bearer token)
   ├─ Try JWT first
   └─ If invalid, try API key
   
2. X-User-Id header (internal service calls)

3. httpOnly cookie (cross-app sessions)

4. Fall back to system user (for background jobs)
```

**Result**: 
- ✅ Assistant tools work (use X-User-Id header)
- ✅ JWT tokens still work
- ✅ API keys work (for external parties)
- ✅ Cookies still work

---

## API Key Management

### Create an API Key

```bash
curl -X POST http://localhost:8001/api/api-keys/create \
  -H "Authorization: Bearer <your_jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "MCP Server",
    "expires_in_days": null
  }'
```

**Response:**
```json
{
  "api_key_id": "123e4567-e89b-12d3-a456-426614174000",
  "token": "IlX5c4V9...3mK2p7n8",
  "name": "MCP Server",
  "created_at": "2026-06-24T22:45:00.000000",
  "expires_at": null,
  "last_used_at": null,
  "is_active": true
}
```

**⚠️ Important**: The token is shown **only once**. Store it securely!

### Use the API Key

Once created, use it like a JWT token:

```bash
curl http://localhost:8001/api/cases \
  -H "Authorization: Bearer IlX5c4V9...3mK2p7n8"
```

### List Your API Keys

```bash
curl http://localhost:8001/api/api-keys/list \
  -H "Authorization: Bearer <your_jwt_token>"
```

### Revoke an API Key

```bash
curl -X POST http://localhost:8001/api/api-keys/revoke/123e4567-e89b-12d3-a456-426614174000 \
  -H "Authorization: Bearer <your_jwt_token>"
```

---

## MCP Server Integration

External MCP servers can now call the OPA backend with a fixed API key:

```python
# Python client example
import httpx

# Create an API key in the UI first
API_KEY = "IlX5c4V9...3mK2p7n8"

async with httpx.AsyncClient() as client:
    response = await client.get(
        "http://localhost:8001/api/cases",
        headers={"Authorization": f"Bearer {API_KEY}"}
    )
    cases = response.json()
```

### Benefits for MCP Server

1. **Persistent auth** — API key doesn't expire (unless you set expiry days)
2. **Simpler auth** — No JWT refresh loops needed
3. **Auditable** — Each key has a `last_used_at` timestamp
4. **Revocable** — Can revoke access instantly without user re-login
5. **Scoped** — Each API key belongs to a specific user's identity

---

## Assistant Tool Calls (Internal)

The OPA Assistant (running on the backend) now works because it passes the user context:

```python
# In agent.py, when making tool calls:
headers = {"X-User-Id": user.user_id}  # ✅ Now recognized by middleware!
```

**Flow:**
```
User in PayGuard (with cookie)
  ↓
/api/assistant/chat/stream (middleware checks cookie, sets user)
  ↓
Agent receives authenticated user
  ↓
Agent calls tool with X-User-Id header
  ↓
Middleware sees X-User-Id header
  ↓
Tool endpoint works ✅
```

---

## Authentication Priority

When multiple auth methods are present, they're checked in this order:

| Priority | Method | Use Case |
|----------|--------|----------|
| 1 | Authorization Bearer (JWT/API Key) | User login or external integrations |
| 2 | X-User-Id header | Internal service-to-service calls |
| 3 | httpOnly cookie | Cross-app sessions |
| 4 | System user | Background jobs (legacy fallback) |

**Example**: If a request has both a Bearer token AND `X-User-Id`, the Bearer token wins.

---

## Security Model

### Tokens (JWT & API Keys)

- **Stored**: Hashed with SHA256 (not plaintext)
- **Lifetime**: JWT = 12h, API Key = configurable
- **Transport**: Bearer in Authorization header or httpOnly cookie
- **Scope**: Each token/key belongs to one user (inherited access)

### X-User-Id Header

- **Trusted only internally** — backend service-to-service calls only
- **Can't be forged from the internet** — only internal (in-process ASGI calls)
- **Used by**: Assistant agent, batch jobs, internal tools

### Best Practices

1. **API Keys for External Integrations**
   - Create a dedicated user account for the integration
   - Create an API key for that account
   - Rotate keys periodically
   - Revoke immediately if compromised

2. **Store Keys Securely**
   - Use environment variables: `export OPA_API_KEY=...`
   - Don't commit to git
   - Don't log or print tokens
   - Rotate regularly

3. **Monitor Usage**
   - Check `last_used_at` in the API key list to detect unused keys
   - Audit logs track who accessed what (future: implement)

---

## Endpoints Reference

All endpoints require authentication (via JWT, API Key, cookie, or X-User-Id).

### Create API Key
```
POST /api/api-keys/create
Body: { "name": "...", "expires_in_days": null or number }
Response: { api_key_id, token, name, created_at, expires_at, is_active }
```

### List API Keys
```
GET /api/api-keys/list
Response: [ { api_key_id, name, created_at, expires_at, last_used_at, is_active }, ... ]
```

### Revoke API Key
```
POST /api/api-keys/revoke/{api_key_id}
Response: { "status": "revoked" }
```

---

## Migration & Rollout

### Database
- ✅ New table `api_keys` created with migration
- ✅ Alembic migration applied: `add_api_keys_table`

### Backend
- ✅ Middleware updated to check X-User-Id and API keys
- ✅ APIKeyService created for management
- ✅ Routes `/api/api-keys/*` added
- ✅ Agent tool calls fixed (now use X-User-Id)

### Frontend
- 🟡 No changes needed (still use JWT login)
- 🟡 UI to manage API keys: could add to admin panel (future)

---

## Testing

### Test 1: API Key Creation & Use

```bash
# 1. Login to get JWT
JWT=$(curl -s -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"ana.chen","password":"ana.chen"}' \
  | jq -r '.access_token')

# 2. Create API key
RESPONSE=$(curl -s -X POST http://localhost:8001/api/api-keys/create \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Key"}')

API_KEY=$(echo $RESPONSE | jq -r '.token')
echo "API Key: $API_KEY"

# 3. Use the API key to call an endpoint
curl -s http://localhost:8001/api/cases?limit=1 \
  -H "Authorization: Bearer $API_KEY" \
  | jq '.items[0].case_number'
```

**Expected**: Should return a case number (or empty list if no cases).

### Test 2: Assistant Tool Calls

```bash
# 1. In PayGuard, open a case
# 2. In the assistant panel, ask: "Who is the provider for this case?"
# 3. Should see the provider name (no 401 error)
```

**Expected**: Assistant successfully calls `get_case` tool.

---

## Future Enhancements

- [ ] Web UI to manage API keys (in admin panel)
- [ ] API key scopes (e.g., "read-only", "write-limited-to-cases")
- [ ] Audit logging for API key usage
- [ ] Automatic key rotation with retention
- [ ] Rate limiting per API key
- [ ] IP whitelisting per key

---

## Questions?

See `/CROSS_APP_AUTH.md` for the JWT/cookie system.
See `middleware/auth.py` for the authentication logic.
