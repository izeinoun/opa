from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

# Load .env into os.environ so SDKs that read it directly (e.g. anthropic)
# pick up keys without each call having to consult pydantic-settings.
from dotenv import load_dotenv  # noqa: E402
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

from .database import create_all_tables
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_all_tables()
    yield


app = FastAPI(
    title="OPA — Overpayment Agent",
    description="Healthcare payment integrity auditing platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # PayGuard UI (OPA client)
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        # ClaimGuard UI (now hitting the unified backend)
        "http://localhost:5175",
        "http://localhost:5176",
        "http://127.0.0.1:5175",
        "http://127.0.0.1:5176",
        # IAM admin UI
        "http://localhost:5177",
        "http://127.0.0.1:5177",
        # SIU UI (planned port)
        "http://localhost:5178",
        "http://127.0.0.1:5178",
        # Generic dev
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers — each router already carries its own /api prefix
from .routes import cases, claims, letters, dashboard, admin, analyze, members, ml, fee_schedules, findings, notifications, supervisor, recoupments, contacts, dashboard_me, provider_risk  # noqa: E402
from .routes import prepay_claims, documents, runtime_config, users, prepay_reports, evidence, siu, connectors  # noqa: E402

app.include_router(cases.router)
app.include_router(claims.router)
app.include_router(letters.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
app.include_router(analyze.router)
app.include_router(members.router)
app.include_router(ml.router)
app.include_router(fee_schedules.router)
app.include_router(findings.router)
app.include_router(notifications.router)
app.include_router(supervisor.router)
app.include_router(recoupments.router)
app.include_router(contacts.router)
app.include_router(dashboard_me.router)
app.include_router(provider_risk.router)
# Pre-pay pipeline (ported from ClaimGuard)
app.include_router(prepay_claims.router)
app.include_router(prepay_reports.router)
app.include_router(documents.router)
app.include_router(runtime_config.router)
app.include_router(users.router)
app.include_router(users.apps_router)
app.include_router(users.roles_router)
app.include_router(evidence.router)
# SIU workspace (post-FWA-rename)
app.include_router(siu.router)
# Connectors (HTTP / SFTP / internal / webhook) — admin-only
app.include_router(connectors.router)


@app.get("/health", tags=["health"])
async def health_check():
    return {
        "status": "ok",
        "environment": settings.environment,
        "db": "sqlite",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


SERVER_ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIST_CANDIDATES = [
    SERVER_ROOT / "static",
    SERVER_ROOT.parent / "client" / "dist",
]
CLIENT_DIST = next((p for p in CLIENT_DIST_CANDIDATES if p.is_dir()), None)
print(f"[startup] client dist resolved to: {CLIENT_DIST}", flush=True)

if CLIENT_DIST is not None:
    app.mount("/assets", StaticFiles(directory=CLIENT_DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(CLIENT_DIST / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": "NotFound"})
        candidate = CLIENT_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(CLIENT_DIST / "index.html")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "ValidationError",
            "detail": exc.errors(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "detail": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
