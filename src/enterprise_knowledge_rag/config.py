from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Portable runtime configuration; secrets are supplied by the environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8010, ge=1, le=65535)
    database_url: str = "postgresql://rag_user:change-me@127.0.0.1:5433/enterprise_rag"
    model_provider: str = "ollama"
    model_base_url: str = "http://127.0.0.1:11434/v1"
    model_name: str = "qwen3:4b"
    model_api_key: str = "ollama"
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    public_demo_mode: bool = True
    public_demo_max_rows: int = Field(default=20, ge=1, le=100)
    demo_user_id: str = "demo-employee"
    demo_role: str = "employee"
    demo_departments: str = "hr,finance,admin"
    allowed_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    request_max_bytes: int = Field(default=16_384, ge=1024, le=1_048_576)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
