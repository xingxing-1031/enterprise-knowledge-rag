from datetime import UTC, datetime
from pathlib import Path

import pytest

from enterprise_knowledge_rag.documents import DocumentParseError, parse_document

CORPUS_DIR = Path(__file__).parents[1] / "knowledge"
INDEXED_AT = datetime(2026, 8, 10, tzinfo=UTC)


def test_parse_document_adds_runtime_metadata() -> None:
    parsed = parse_document(
        CORPUS_DIR / "finance" / "expense-policy-v2.md",
        indexed_at=INDEXED_AT,
    )
    assert parsed.record.document_id == "finance-expense-policy"
    assert parsed.record.version == "2.0"
    assert parsed.record.indexed_at == INDEXED_AT
    assert len(parsed.record.content_hash) == 64
    assert parsed.body.startswith("# 差旅与费用报销管理制度")


def test_parse_document_is_deterministic_for_fixed_index_time() -> None:
    path = CORPUS_DIR / "hr" / "leave-policy-v2.md"
    first = parse_document(path, indexed_at=INDEXED_AT)
    second = parse_document(path, indexed_at=INDEXED_AT)
    assert first == second


def test_parse_document_rejects_missing_front_matter(tmp_path: Path) -> None:
    path = tmp_path / "invalid.md"
    path.write_text("# 只有正文", encoding="utf-8")
    with pytest.raises(DocumentParseError, match="front matter"):
        parse_document(path)


def test_parse_document_rejects_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "invalid.md"
    path.write_text("---\n[broken\n---\n# 正文\n", encoding="utf-8")
    with pytest.raises(DocumentParseError, match="YAML"):
        parse_document(path)
