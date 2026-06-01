from functools import lru_cache
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
    # CORS — comma-separated list of allowed frontend origins. Empty (the
    # default) falls back to the local dev allow-list below, so local dev and
    # tests need no config. Railway sets CORS_ALLOW_ORIGINS to the real
    # deployed frontend hosts (e.g. "https://payguard.example.com,https://...").
    cors_allow_origins: str = ""
    # Shared-login demo gate. When set (e.g. on the public deploy), every /api
    # route requires a token obtained from POST /api/auth/login with this
    # password. Empty (the default) DISABLES the gate, so local dev and the
    # test suite need no login. Set DEMO_PASSWORD on any public deployment.
    demo_password: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        """Resolved allow-list: the env override if set, else the dev defaults."""
        if self.cors_allow_origins.strip():
            return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]
        return _DEV_CORS_ORIGINS


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
    # Generic dev
    "http://localhost:3000",
]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
