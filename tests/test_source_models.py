from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from enterprise_knowledge_rag.documents.source_models import (
    CleaningIssue,
    CleaningReport,
    EvidenceKind,
    EvidenceNeed,
    ImportMetadata,
    ImportPreview,
    IngestionStatus,
    IssueSeverity,
    RetrievalPlan,
)
from enterprise_knowledge_rag.models import DocumentType, UserRole, Visibility


def make_preview(**overrides: object) -> ImportPreview:
    now = datetime(2026, 8, 10, tzinfo=UTC)
    values: dict[str, object] = {
        "import_id": "import-001",
        "original_filename": "leave-policy.pdf",
        "source_hash": "a" * 64,
        "media_type": "application/pdf",
        "size_bytes": 4096,
        "page_count": 3,
        "status": IngestionStatus.NEEDS_REVIEW,
        "metadata": ImportMetadata(
            document_id="hr-leave-policy",
            title="员工请假制度",
            document_type=DocumentType.POLICY,
            department="hr",
            visibility=Visibility.RESTRICTED,
            allowed_roles={UserRole.EMPLOYEE},
            version="2.0",
            effective_from=now,
        ),
        "cleaning_report": CleaningReport(
            characters_before=1200,
            characters_after=1100,
            blocks_before=20,
            blocks_after=18,
            table_count=0,
            content_hash="b" * 64,
        ),
        "normalized_preview": "# 员工请假制度\n\n员工应按流程提交申请。",
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return ImportPreview.model_validate(values)


def test_retrieval_plan_rejects_more_than_four_needs() -> None:
    needs = [
        EvidenceNeed(need_id=f"n{i}", kind="rule", query=f"制度问题{i}")
        for i in range(5)
    ]

    with pytest.raises(ValidationError, match="evidence_needs"):
        RetrievalPlan(
            primary_query="请假规则是什么",
            topic="请假",
            departments={"hr"},
            evidence_needs=needs,
            requires_multi_hop=True,
            max_hops=2,
        )


def test_retrieval_plan_rejects_duplicate_need_ids() -> None:
    with pytest.raises(ValidationError, match="need_id"):
        RetrievalPlan(
            primary_query="请假需要什么材料",
            topic="请假",
            evidence_needs=[
                EvidenceNeed(
                    need_id="materials",
                    kind=EvidenceKind.MATERIAL,
                    query="请假材料",
                ),
                EvidenceNeed(
                    need_id="materials",
                    kind=EvidenceKind.EXCEPTION,
                    query="紧急情况",
                ),
            ],
            requires_multi_hop=True,
            max_hops=2,
        )


def test_retrieval_plan_requires_two_hops_when_marked_multi_hop() -> None:
    with pytest.raises(ValidationError, match="max_hops"):
        RetrievalPlan(
            primary_query="请假需要什么材料",
            topic="请假",
            evidence_needs=[
                EvidenceNeed(
                    need_id="materials",
                    kind=EvidenceKind.MATERIAL,
                    query="请假材料",
                )
            ],
            requires_multi_hop=True,
            max_hops=1,
        )


def test_quarantined_preview_cannot_be_approved() -> None:
    issue = CleaningIssue(
        code="scanned_pdf",
        severity=IssueSeverity.BLOCKING,
        message="PDF 缺少可提取文本，需要人工处理。",
    )
    report = make_preview().cleaning_report.model_copy(update={"issues": [issue]})
    preview = make_preview(
        status=IngestionStatus.QUARANTINED,
        cleaning_report=report,
    )

    assert preview.can_approve is False


def test_review_preview_with_non_blocking_warning_can_be_approved() -> None:
    issue = CleaningIssue(
        code="repeated_header",
        severity=IssueSeverity.WARNING,
        message="发现重复页眉，请核对清洗结果。",
    )
    report = make_preview().cleaning_report.model_copy(update={"issues": [issue]})

    assert make_preview(cleaning_report=report).can_approve is True


def test_import_preview_never_accepts_storage_path() -> None:
    values = make_preview().model_dump()
    values["storage_path"] = "data/uploads/private/source.pdf"

    with pytest.raises(ValidationError, match="storage_path"):
        ImportPreview.model_validate(values)
