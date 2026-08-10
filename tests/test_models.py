from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from enterprise_knowledge_rag.config import Settings
from enterprise_knowledge_rag.models import (
    ChunkRecord,
    DocumentRecord,
    DocumentStatus,
    DocumentType,
    RetrievalEvidence,
    UserContext,
    UserRole,
    Visibility,
)


def make_document(**overrides: object) -> DocumentRecord:
    values: dict[str, object] = {
        "document_id": "finance-expense-policy",
        "title": "费用报销管理制度",
        "document_type": DocumentType.POLICY,
        "department": "finance",
        "visibility": Visibility.PUBLIC,
        "allowed_roles": [],
        "version": "2.1",
        "status": DocumentStatus.ACTIVE,
        "effective_from": datetime(2026, 1, 1, tzinfo=UTC),
        "effective_to": None,
        "supersedes_id": "finance-expense-policy-v1",
        "content_hash": "a" * 64,
        "source_path": "finance/expense-policy-v2.1.md",
        "indexed_at": datetime(2026, 8, 10, tzinfo=UTC),
    }
    values.update(overrides)
    return DocumentRecord.model_validate(values)


def test_document_rejects_invalid_effective_range() -> None:
    with pytest.raises(ValidationError, match="effective_to"):
        make_document(effective_to=datetime(2025, 12, 31, tzinfo=UTC))


def test_restricted_document_requires_allowed_roles() -> None:
    with pytest.raises(ValidationError, match="allowed_roles"):
        make_document(visibility=Visibility.RESTRICTED, allowed_roles=[])


def test_models_forbid_unknown_fields() -> None:
    values = make_document().model_dump()
    values["company_name"] = "fictional-company"
    with pytest.raises(ValidationError, match="company_name"):
        DocumentRecord.model_validate(values)


def test_chunk_rejects_empty_stable_identifier() -> None:
    with pytest.raises(ValidationError, match="chunk_id"):
        ChunkRecord(
            chunk_id="",
            document_id="finance-expense-policy",
            document_version="2.1",
            section_path=["报销范围"],
            chunk_index=0,
            content="员工提交报销前应准备有效票据。",
            token_count=12,
            content_hash="b" * 64,
            embedding_model="BAAI/bge-m3",
        )


def test_user_context_normalizes_departments_and_roles() -> None:
    user = UserContext(
        user_id="demo-analyst",
        role=UserRole.EMPLOYEE,
        departments=["finance", "finance", "hr"],
    )
    assert user.departments == {"finance", "hr"}


def test_settings_have_portable_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("MODEL_BASE_URL", raising=False)
    settings = Settings()
    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.model_base_url == "http://127.0.0.1:11434/v1"
    assert "E:/" not in settings.embedding_model
    assert settings.upload_max_bytes == 15 * 1024 * 1024
    assert settings.pdf_max_pages == 200
    assert settings.document_route_limit == 4


def test_retrieval_evidence_has_backward_compatible_need_defaults() -> None:
    evidence = RetrievalEvidence(
        evidence_id="evidence-1",
        chunk_id="chunk-1",
        document_id="finance-expense-policy",
        title="费用报销管理制度",
        section_path=["报销范围"],
        version="2.1",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        quote="员工提交报销前应准备有效票据。",
        retrieval_rank=1,
    )

    assert evidence.supports_need_ids == set()
    assert evidence.retrieval_hop == 1


def test_retrieval_evidence_rejects_unbounded_hop_number() -> None:
    with pytest.raises(ValidationError, match="retrieval_hop"):
        RetrievalEvidence(
            evidence_id="evidence-1",
            chunk_id="chunk-1",
            document_id="finance-expense-policy",
            title="费用报销管理制度",
            section_path=["报销范围"],
            version="2.1",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            quote="员工提交报销前应准备有效票据。",
            retrieval_rank=1,
            retrieval_hop=3,
        )
