from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Portable runtime configuration; secrets are supplied by the environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8010, ge=1, le=65535)
    database_url: str = "postgresql://rag_user:change-me@127.0.0.1:5433/enterprise_rag"
    database_pool_min_size: int = Field(default=1, ge=1, le=20)
    database_pool_max_size: int = Field(default=4, ge=1, le=50)
    database_pool_timeout_seconds: float = Field(default=10.0, gt=0.0, le=60.0)
    model_provider: str = "ollama"
    model_base_url: str = "http://127.0.0.1:11434/v1"
    model_name: str = "qwen3:4b"
    model_api_key: str = "ollama"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = Field(default=1024, ge=1, le=4096)
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_min_score: float = 0.0
    model_timeout_seconds: float = Field(default=30.0, gt=0.0, le=120.0)
    knowledge_dir: Path = Path("knowledge")
    migrations_dir: Path = Path("db/migrations")
    frontend_dist_dir: Path = Path("frontend/dist")
    latest_evaluation_path: Path = Path("evaluation/reports/latest-development.json")
    history_max_messages: int = Field(default=8, ge=2, le=20)
    public_demo_mode: bool = True
    public_demo_max_rows: int = Field(default=20, ge=1, le=100)
    demo_user_id: str = "demo-employee"
    demo_role: str = "employee"
    demo_departments: str = "hr,finance,admin"
    allowed_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    request_max_bytes: int = Field(default=16_384, ge=1024, le=1_048_576)

    @model_validator(mode="after")
    def validate_pool_bounds(self) -> "Settings":
        if self.database_pool_max_size < self.database_pool_min_size:
            raise ValueError("database_pool_max_size must be at least the minimum")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
