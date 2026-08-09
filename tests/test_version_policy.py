from datetime import UTC, datetime

import pytest

from enterprise_knowledge_rag.models import (
    DocumentRecord,
    DocumentStatus,
    DocumentType,
    Visibility,
)
from enterprise_knowledge_rag.policy import (
    VersionResolutionStatus,
    resolve_effective_versions,
)


def make_document(version, status, start, end=None, document_id="leave-policy"):
    return DocumentRecord(
        document_id=document_id,
        title="员工请假管理制度",
        document_type=DocumentType.POLICY,
        department="hr",
        visibility=Visibility.PUBLIC,
        version=version,
        status=status,
        effective_from=datetime.fromisoformat(start),
        effective_to=datetime.fromisoformat(end) if end else None,
        content_hash=(version.replace(".", "") * 64)[:64],
        source_path=f"hr/leave-v{version}.md",
        indexed_at=datetime(2026, 8, 10, tzinfo=UTC),
    )


DOCUMENTS = [
    make_document(
        "1.0",
        DocumentStatus.EXPIRED,
        "2025-01-01T00:00:00+00:00",
        "2026-02-28T23:59:59+00:00",
    ),
    make_document(
        "2.0",
        DocumentStatus.ACTIVE,
        "2026-03-01T00:00:00+00:00",
    ),
    make_document(
        "3.0",
        DocumentStatus.DRAFT,
        "2027-01-01T00:00:00+00:00",
    ),
]


def test_current_time_selects_active_version() -> None:
    result = resolve_effective_versions(
        DOCUMENTS,
        as_of=datetime(2026, 8, 10, tzinfo=UTC),
    )
    assert result.status is VersionResolutionStatus.SELECTED
    assert result.document.version == "2.0"


def test_historical_time_selects_expired_version() -> None:
    result = resolve_effective_versions(
        DOCUMENTS,
        as_of=datetime(2025, 8, 10, tzinfo=UTC),
    )
    assert result.document.version == "1.0"


def test_future_draft_is_not_selected() -> None:
    result = resolve_effective_versions(
        DOCUMENTS,
        as_of=datetime(2027, 2, 1, tzinfo=UTC),
        requested_version="3.0",
    )
    assert result.status is VersionResolutionStatus.NOT_FOUND


def test_overlapping_versions_are_ambiguous() -> None:
    overlapping = [
        DOCUMENTS[1],
        make_document(
            "2.1",
            DocumentStatus.ACTIVE,
            "2026-07-01T00:00:00+00:00",
        ),
    ]
    result = resolve_effective_versions(
        overlapping,
        as_of=datetime(2026, 8, 10, tzinfo=UTC),
    )
    assert result.status is VersionResolutionStatus.AMBIGUOUS
    assert result.candidate_versions == ("2.0", "2.1")


def test_mixed_document_ids_are_rejected() -> None:
    mixed = [
        DOCUMENTS[1],
        make_document(
            "1.0",
            DocumentStatus.ACTIVE,
            "2026-01-01T00:00:00+00:00",
            document_id="expense-policy",
        ),
    ]
    with pytest.raises(ValueError, match="document_id"):
        resolve_effective_versions(
            mixed,
            as_of=datetime(2026, 8, 10, tzinfo=UTC),
        )


def test_naive_as_of_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        resolve_effective_versions(DOCUMENTS, as_of=datetime(2026, 8, 10))
