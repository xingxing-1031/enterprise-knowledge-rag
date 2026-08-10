from pathlib import Path

from fastapi.testclient import TestClient
from test_app import FakeService, FixedResolver

from enterprise_knowledge_rag.app import create_app
from enterprise_knowledge_rag.config import Settings
from enterprise_knowledge_rag.database import connection_pool_lifespan
from enterprise_knowledge_rag.migrations import discover_migrations
from scripts.index_knowledge import (
    DeterministicTestEmbeddings,
    build_embedding_provider,
)


class FakePool:
    def __init__(self) -> None:
        self.events: list[object] = []

    def open(self, *, wait: bool, timeout: float) -> None:
        self.events.append(("open", wait, timeout))

    def close(self) -> None:
        self.events.append("close")


def test_connection_pool_follows_application_lifecycle() -> None:
    pool = FakePool()
    app = create_app(
        FakeService(),
        session_resolver=FixedResolver(),
        lifespan=connection_pool_lifespan(pool, timeout_seconds=7.5),
    )

    assert pool.events == []
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert pool.events == [("open", True, 7.5)]
    assert pool.events == [("open", True, 7.5), "close"]


def test_migrations_are_sorted_and_content_addressed(tmp_path: Path) -> None:
    (tmp_path / "002_second.sql").write_text("SELECT 2;\n", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("ignored", encoding="utf-8")

    migrations = discover_migrations(tmp_path)

    assert [item.version for item in migrations] == ["001_first", "002_second"]
    assert all(len(item.checksum) == 64 for item in migrations)
    assert migrations[0].sql == "SELECT 1;\n"


def test_ingestion_migration_adds_import_jobs_and_parent_vectors() -> None:
    migration_path = (
        Path(__file__).parents[1]
        / "db"
        / "migrations"
        / "004_ingestion_and_document_routing.sql"
    )

    sql = migration_path.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS knowledge_imports" in sql
    assert "document_search_text" in sql
    assert "document_embedding vector(1024)" in sql
    assert "storage_path TEXT NOT NULL" in sql


def test_delivery_smoke_invokes_retrieval_script_as_module() -> None:
    workflow_path = Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"

    workflow = workflow_path.read_text(encoding="utf-8")

    assert "python -m scripts.retrieval_smoke" in workflow


def test_container_prepares_writable_model_cache_for_non_root_user() -> None:
    dockerfile_path = Path(__file__).parents[1] / "Dockerfile"

    dockerfile = dockerfile_path.read_text(encoding="utf-8")

    assert "/home/appuser/.cache/huggingface" in dockerfile


def test_container_build_allows_debian_mirror_overrides() -> None:
    project_root = Path(__file__).parents[1]
    dockerfile = (project_root / "Dockerfile").read_text(encoding="utf-8")
    compose = (project_root / "compose.yaml").read_text(encoding="utf-8")

    assert "ARG DEBIAN_MIRROR=" in dockerfile
    assert "ARG DEBIAN_SECURITY_MIRROR=" in dockerfile
    assert "DEBIAN_MIRROR: ${DEBIAN_MIRROR:-" in compose
    assert "DEBIAN_SECURITY_MIRROR: ${DEBIAN_SECURITY_MIRROR:-" in compose


def test_deterministic_embeddings_are_stable_and_ci_only(monkeypatch) -> None:
    provider = DeterministicTestEmbeddings(8)
    first = provider.embed_query("报销期限")

    assert first == provider.embed_query("报销期限")
    assert len(first) == 8

    monkeypatch.setenv("DETERMINISTIC_TEST_EMBEDDINGS", "true")
    try:
        build_embedding_provider(Settings(app_env="development"))
    except RuntimeError as exc:
        assert "APP_ENV=ci" in str(exc)
    else:
        raise AssertionError("test embeddings must be rejected outside CI")
