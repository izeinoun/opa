from functools import lru_cache
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./opa.db"
    anthropic_api_key: str = ""
    aws_profile: str = "default"
    aws_region: str = "us-east-1"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    secret_key: str = "dev-secret-key-change-in-production"
    environment: str = "development"
    ml_models_dir: str = "./ml_models"
    # When true, the app seeds the demo dataset on startup IF the DB is empty.
    # Off by default so local dev and the test suite (which trigger the lifespan
    # via TestClient) never auto-seed. Railway sets SEED_ON_EMPTY=1 so each
    # deploy onto its ephemeral filesystem comes up with a populated demo.
    seed_on_empty: bool = False
    # CORS — the known dev + prod frontend origins are baked into the lists
    # below (in code, not a deployment variable), so cross-origin calls from
    # every deployed app work with zero dashboard config. This optional
    # comma-separated var only ADDS extra origins on top if ever needed; it is
    # never required.
    cors_allow_origins: str = ""
    # Shared-login demo gate. When set (e.g. on the public deploy), every /api
    # route requires a token obtained from POST /api/auth/login with this
    # password. Empty (the default) DISABLES the gate, so local dev and the
    # test suite need no login. Set DEMO_PASSWORD on any public deployment.
    demo_password: str = ""
    # Single source of truth for the LLM model id used by all claim / evidence /
    # FWA / document-generation reasoning. Services read settings.llm_model
    # instead of hardcoding. Override with env LLM_MODEL (CLAIMGUARD_MODEL is
    # accepted as a back-compat alias).
    llm_model: str = Field(
        default="claude-sonnet-4-6",
        validation_alias=AliasChoices("LLM_MODEL", "CLAIMGUARD_MODEL"),
    )
    # The in-app assistant uses a smaller/faster model. Override with ASSISTANT_MODEL.
    assistant_model: str = Field(
        default="claude-haiku-4-5-20251001",
        validation_alias=AliasChoices("ASSISTANT_MODEL"),
    )
    # Dollar gate above which a terminal case decision (recoup / not-for-recoup)
    # is held for supervisor approval instead of executing immediately. Single
    # source of truth — read by both the enforcement path (case_service) and the
    # case-guidance engine so the UI never disagrees with what is enforced.
    # Override with env HIGH_DOLLAR_THRESHOLD.
    high_dollar_threshold: float = Field(
        default=2000.0,
        validation_alias=AliasChoices("HIGH_DOLLAR_THRESHOLD"),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        """Allowed origins. The known dev + prod hosts are baked in here (in
        code, not a deployment variable) so CORS works without any env config.
        An optional CORS_ALLOW_ORIGINS only ADDS extra origins on top."""
        extra = [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]
        return [*_DEV_CORS_ORIGINS, *_PROD_CORS_ORIGINS, *extra]


# Local dev frontend ports for each app (PayGuard/ClaimGuard/IAM/SIU + generic).
# Used when CORS_ALLOW_ORIGINS is unset.
_DEV_CORS_ORIGINS = [
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
    # OPA Assistant (standalone full-page assistant app)
    "http://localhost:5179",
    "http://127.0.0.1:5179",
    # File Intake Portal (standalone secure file-drop)
    "http://localhost:5180",
    "http://127.0.0.1:5180",
    # Generic dev
    "http://localhost:3000",
]


# Known production frontend origins. Committed here (NOT a Railway variable) so
# cross-origin calls from the deployed apps work without any dashboard config.
# Mirror of the PROD hosts in each frontend's src/config/appUrls.ts — keep in
# sync if a host changes.
_PROD_CORS_ORIGINS = [
    "https://payguard.penguinai.studio",
    "https://claimguard.penguinai.studio",
    "https://iam.penguinai.studio",
    "https://siu.penguinai.studio",
    "https://assistant.penguinai.studio",
    "https://intake.penguinai.studio",
]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


# Bearer guard for the mounted MCP endpoint (/mcp).
#
# Left EMPTY (open) on purpose: Claude's custom connectors authenticate via
# OAuth, not a static Authorization header — there's no field to paste a bearer
# — so a static-token gate just breaks the connector. /mcp serves only READ-ONLY
# synthetic demo data, so open access is acceptable here. The guard code remains
# (mcp_mount.py); set a non-empty value to re-enable it for clients that CAN
# send `Authorization: Bearer <token>` (e.g. scripts/curl). Real per-user auth =
# OAuth, a separate effort.
MCP_BEARER_TOKEN = ""
