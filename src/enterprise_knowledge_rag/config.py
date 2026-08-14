from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
    embedding_provider: Literal["local", "openai_compatible"] = "local"
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_batch_size: int = Field(default=20, ge=1, le=25)
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = Field(default=1024, ge=1, le=4096)
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_min_score: float = 0.0
    reranker_provider: Literal["local", "openai_compatible", "none"] = "local"
    reranker_base_url: str | None = None
    reranker_api_key: str | None = None
    retrieval_strategy: Literal[
        "vector_baseline",
        "hybrid_rrf",
        "hybrid_rrf_reranker",
    ] = "hybrid_rrf"
    model_timeout_seconds: float = Field(default=30.0, gt=0.0, le=120.0)
    knowledge_dir: Path = Path("knowledge")
    migrations_dir: Path = Path("db/migrations")
    frontend_dist_dir: Path = Path("frontend/dist")
    latest_evaluation_path: Path = Path("evaluation/reports/latest-development.json")
    upload_storage_dir: Path = Path("data/uploads")
    upload_max_bytes: int = Field(default=15 * 1024 * 1024, ge=1)
    pdf_max_pages: int = Field(default=200, ge=1, le=2_000)
    document_route_limit: int = Field(default=4, ge=1, le=20)
    evidence_max_items: int = Field(default=6, ge=1, le=20)
    evidence_max_tokens: int = Field(default=1200, ge=64, le=10_000)
    history_max_messages: int = Field(default=8, ge=2, le=20)
    public_demo_mode: bool = True
    auth_cookie_name: str = "rag_session"
    auth_session_secret: str = ""
    auth_session_ttl_seconds: int = Field(default=28_800, ge=300, le=86_400)
    auth_cookie_secure: bool = False
    internal_service_token: SecretStr | None = None
    auth_knowledge_admin_username: str = "knowledge-admin-demo"
    auth_knowledge_admin_user_id: str = "demo-knowledge-admin"
    auth_knowledge_admin_departments: str = "hr,finance,admin,procurement,security"
    auth_knowledge_admin_password_hash: str = (
        "pbkdf2_sha256$210000$P58H3UwiBzg4AnUzhAuvXg"
        "$oypDqCdnPuRTDe8PRlmv0f6bmpBM5Q1Js-xCVThzF-A"
    )
    admin_audit_secret: str = "local-admin-audit-secret-change-me"
    allowed_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    request_max_bytes: int = Field(default=16_384, ge=1024, le=1_048_576)

    @model_validator(mode="after")
    def validate_pool_bounds(self) -> "Settings":
        if self.database_pool_max_size < self.database_pool_min_size:
            raise ValueError("database_pool_max_size must be at least the minimum")
        if (
            self.reranker_provider == "none"
            and self.retrieval_strategy == "hybrid_rrf_reranker"
        ):
            raise ValueError(
                "reranker_provider=none is incompatible with hybrid_rrf_reranker"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
