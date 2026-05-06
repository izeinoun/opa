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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
