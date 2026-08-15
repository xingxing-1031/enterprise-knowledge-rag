from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.evaluation_support import code_commit, corpus_snapshot
from scripts.run_development_smoke import select_case
from scripts.run_final_holdout import (
    FROZEN_SHA256,
    require_frozen_confirmation,
    verify_frozen_hash,
)


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


def test_frozen_guard_requires_exact_confirmation(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="CONSUME_ONCE"):
        require_frozen_confirmation("", tmp_path / "final-holdout.json")


def test_frozen_guard_refuses_to_overwrite(tmp_path) -> None:
    output = tmp_path / "final-holdout.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError):
        require_frozen_confirmation("CONSUME_ONCE", output)


def test_v2_frozen_hash_matches_committed_dataset() -> None:
    project_root = Path(__file__).resolve().parents[1]

    verify_frozen_hash(project_root / "evaluation" / "frozen-holdout-v2.json")
    assert len(FROZEN_SHA256) == 64
