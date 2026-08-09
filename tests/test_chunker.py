from datetime import UTC, datetime
from pathlib import Path

from enterprise_knowledge_rag.documents import chunk_document, parse_document
from enterprise_knowledge_rag.documents.chunker import estimate_tokens

CORPUS_DIR = Path(__file__).parents[1] / "knowledge"


def parse_expense_policy():
    return parse_document(
        CORPUS_DIR / "finance" / "expense-policy-v2.md",
        indexed_at=datetime(2026, 8, 10, tzinfo=UTC),
    )


def test_chunks_preserve_heading_paths_and_table() -> None:
    chunks = chunk_document(parse_expense_policy(), max_tokens=80, overlap_tokens=8)
    paths = {tuple(chunk.section_path) for chunk in chunks}
    assert ("差旅与费用报销管理制度", "报销期限") in paths
    assert ("差旅与费用报销管理制度", "票据要求") in paths
    assert any(
        "| 费用类型 | 默认标准 | 例外审批 |" in chunk.content for chunk in chunks
    )


def test_chunks_do_not_cross_sections() -> None:
    chunks = chunk_document(parse_expense_policy(), max_tokens=80, overlap_tokens=8)
    for chunk in chunks:
        if "报销申请应关联真实行程" in chunk.content:
            assert chunk.section_path[-1] == "票据要求"
            assert "出差结束后 15 个自然日" not in chunk.content


def test_chunk_ids_are_stable() -> None:
    first = chunk_document(parse_expense_policy(), max_tokens=80, overlap_tokens=8)
    second = chunk_document(parse_expense_policy(), max_tokens=80, overlap_tokens=8)
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]


def test_chunk_budget_is_enforced() -> None:
    chunks = chunk_document(parse_expense_policy(), max_tokens=80, overlap_tokens=8)
    assert chunks
    assert all(estimate_tokens(chunk.content) <= 80 for chunk in chunks)
