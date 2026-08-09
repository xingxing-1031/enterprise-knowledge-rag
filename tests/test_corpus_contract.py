import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from enterprise_knowledge_rag.models import DocumentRecord

CORPUS_DIR = Path(__file__).parents[1] / "knowledge"


def read_front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"missing front matter: {path}"
    _, raw, body = text.split("---", 2)
    assert body.strip(), f"empty document body: {path}"
    metadata = yaml.safe_load(raw) or {}
    metadata["content_hash"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    metadata["indexed_at"] = datetime(2026, 8, 10, tzinfo=UTC)
    return metadata


def test_manifest_lists_existing_synthetic_documents() -> None:
    manifest = yaml.safe_load(
        (CORPUS_DIR / "manifest.yaml").read_text(encoding="utf-8")
    )
    assert manifest["synthetic"] is True
    listed = {CORPUS_DIR / item for item in manifest["documents"]}
    assert listed
    assert all(path.exists() for path in listed)
    assert {path.suffix for path in listed} == {".md"}


def test_documents_satisfy_metadata_contract() -> None:
    manifest = yaml.safe_load(
        (CORPUS_DIR / "manifest.yaml").read_text(encoding="utf-8")
    )
    records = [
        DocumentRecord.model_validate(read_front_matter(CORPUS_DIR / item))
        for item in manifest["documents"]
    ]
    assert len(records) == 10
    assert {record.status.value for record in records} >= {"active", "expired", "draft"}
    assert any(record.visibility.value == "restricted" for record in records)


def test_active_versions_are_not_duplicated_for_same_as_of_date() -> None:
    manifest = yaml.safe_load(
        (CORPUS_DIR / "manifest.yaml").read_text(encoding="utf-8")
    )
    records = [
        DocumentRecord.model_validate(read_front_matter(CORPUS_DIR / item))
        for item in manifest["documents"]
    ]
    as_of = datetime.fromisoformat("2026-08-10T00:00:00+08:00")
    active_keys = {
        record.document_id
        for record in records
        if record.status.value == "active"
        and record.effective_from <= as_of
        and (record.effective_to is None or as_of <= record.effective_to)
    }
    assert len(active_keys) == len(
        [
            record
            for record in records
            if record.status.value == "active"
            and record.effective_from <= as_of
            and (record.effective_to is None or as_of <= record.effective_to)
        ]
    )


@pytest.mark.parametrize("path", (CORPUS_DIR / "finance").glob("*.md"))
def test_policy_body_contains_headings(path: Path) -> None:
    body = path.read_text(encoding="utf-8").split("---", 2)[-1]
    assert "## " in body
