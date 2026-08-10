from types import SimpleNamespace

import pytest

from scripts.evaluation_support import code_commit, corpus_snapshot
from scripts.run_development_smoke import select_case


def test_code_commit_prefers_explicit_container_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("EVAL_CODE_COMMIT", "abc1234")

    assert code_commit(tmp_path) == "abc1234"


def test_corpus_snapshot_ignores_knowledge_readme(tmp_path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "policy.md").write_text("policy-v1", encoding="utf-8")
    (knowledge / "README.md").write_text("first", encoding="utf-8")

    before = corpus_snapshot(tmp_path)
    (knowledge / "README.md").write_text("second", encoding="utf-8")

    assert corpus_snapshot(tmp_path) == before
    assert before.startswith("sha256:")


def test_select_case_requires_exactly_one_match() -> None:
    wanted = SimpleNamespace(case_id="wanted")

    assert select_case([SimpleNamespace(case_id="other"), wanted], "wanted") is wanted
    with pytest.raises(LookupError, match="exactly one"):
        select_case([SimpleNamespace(case_id="other")], "wanted")
    with pytest.raises(LookupError, match="exactly one"):
        select_case([wanted, wanted], "wanted")
