import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from enterprise_knowledge_rag.models import DocumentRecord

FRONT_MATTER_PATTERN = re.compile(
    r"\A---\r?\n(?P<metadata>.*?)\r?\n---\r?\n(?P<body>.*)\Z",
    re.DOTALL,
)


class DocumentParseError(ValueError):
    """Raised when a source file cannot become a validated document."""


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    record: DocumentRecord
    body: str


def _normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"


def parse_document(
    path: Path,
    *,
    indexed_at: datetime | None = None,
) -> ParsedDocument:
    """Parse YAML front matter and body into a strict document contract."""

    try:
        raw_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DocumentParseError(f"cannot read document: {path.name}") from exc

    normalized = _normalize_text(raw_text)
    match = FRONT_MATTER_PATTERN.fullmatch(normalized)
    if match is None:
        raise DocumentParseError(f"invalid front matter: {path.name}")

    try:
        metadata: Any = yaml.safe_load(match.group("metadata"))
    except yaml.YAMLError as exc:
        raise DocumentParseError(f"invalid YAML metadata: {path.name}") from exc
    if not isinstance(metadata, dict):
        raise DocumentParseError(f"metadata must be a mapping: {path.name}")

    body = _normalize_text(match.group("body"))
    if not body.strip():
        raise DocumentParseError(f"empty document body: {path.name}")

    metadata["content_hash"] = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    metadata["indexed_at"] = indexed_at or datetime.now(UTC)

    try:
        record = DocumentRecord.model_validate(metadata)
    except ValidationError as exc:
        raise DocumentParseError(f"invalid metadata: {path.name}: {exc}") from exc

    return ParsedDocument(record=record, body=body)
