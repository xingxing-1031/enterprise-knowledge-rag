from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Sequence

from enterprise_knowledge_rag.models import DocumentRecord, DocumentStatus


class VersionResolutionStatus(StrEnum):
    SELECTED = "selected"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class VersionResolution:
    status: VersionResolutionStatus
    document: DocumentRecord | None
    candidate_versions: tuple[str, ...] = ()


def _is_effective(document: DocumentRecord, as_of: datetime) -> bool:
    if document.status in {DocumentStatus.DRAFT, DocumentStatus.REVOKED}:
        return False
    if document.effective_from > as_of:
        return False
    return document.effective_to is None or as_of <= document.effective_to


def resolve_effective_versions(
    documents: Sequence[DocumentRecord],
    *,
    as_of: datetime,
    requested_version: str | None = None,
) -> VersionResolution:
    """Resolve one effective version for a single logical document."""

    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    document_ids = {document.document_id for document in documents}
    if len(document_ids) > 1:
        raise ValueError("documents must share one document_id")

    if requested_version is not None:
        matching = [
            document
            for document in documents
            if document.version == requested_version and _is_effective(document, as_of)
        ]
    else:
        matching = [
            document for document in documents if _is_effective(document, as_of)
        ]

    if not matching:
        return VersionResolution(VersionResolutionStatus.NOT_FOUND, None)
    if len(matching) > 1:
        return VersionResolution(
            VersionResolutionStatus.AMBIGUOUS,
            None,
            tuple(sorted(document.version for document in matching)),
        )
    return VersionResolution(
        VersionResolutionStatus.SELECTED,
        matching[0],
        (matching[0].version,),
    )
