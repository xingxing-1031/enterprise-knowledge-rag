# Job-Ready Enterprise RAG Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize evidence-need IDs, make bounded supplemental retrieval measurable, select the demo strategy from repeated development evidence, and produce a one-time frozen holdout report for recruiting.

**Architecture:** The LLM continues to propose evidence kinds and search text, while the server owns canonical need IDs and supplemental-hop budgets. Coverage uses a deterministic token-overlap threshold plus explicit need-scoped support, evaluation gold uses the same canonical contract, and repeated raw reports feed a structured summary before the frozen runner can be explicitly unlocked once.

**Tech Stack:** Python 3.11+, Pydantic v2, LangGraph, PostgreSQL/pgvector, sentence-transformers `bge-m3`, CrossEncoder `bge-reranker-v2-m3`, OpenAI-compatible Qwen, pytest, Ruff, React/Vitest/Vite, Docker Compose.

## Global Constraints

- Do not execute or modify `evaluation/frozen_holdout.json` during Tasks 1-6; its expected SHA-256 is `571616f9172881b0196c4d889a1d5d3691905fb7db035a14effb5f7d46cd465d`.
- Never print, stage, commit, or copy `.env` or `MODEL_API_KEY` into reports, logs, docs, or commands.
- The server, not the LLM, owns canonical `need_id` values.
- Supplemental retrieval remains bounded to one extra hop and the first-hop authorized route keys.
- Do not hard-code question text, document IDs, versions, or answers to make development cases pass.
- Keep all existing local `qwen3:4b` and `qwen-plus` raw reports; overwrite standard `r1` files only through a new controlled run after code changes are committed.
- Development reports must preserve all repetitions, including failures and cold-start outliers.
- Run frozen holdout exactly once only after code, prompt, corpus, default strategy, and development conclusions are committed.

---

## File Map

- `src/enterprise_knowledge_rag/retrieval/planning.py`: canonicalize model plans and derive the supplemental-hop budget.
- `src/enterprise_knowledge_rag/retrieval/coverage.py`: deterministic evidence-to-need matching with a minimum overlap ratio.
- `evaluation/development.json`: development-only canonical need IDs.
- `src/enterprise_knowledge_rag/config.py`, `bootstrap.py`, `.env.example`, `compose.yaml`: configurable default retrieval strategy.
- `src/enterprise_knowledge_rag/evaluation/summary.py`: validate and aggregate repeated raw development reports.
- `scripts/evaluation_support.py`: shared corpus snapshot and code-commit metadata helpers.
- `scripts/run_development_smoke.py`: run one named development case without writing or replacing reports.
- `scripts/run_development.py`: write all repetitions, the default-strategy latest report, and the aggregate summary.
- `scripts/run_final_holdout.py`: explicit one-time frozen acceptance entry point.
- `docs/INTERVIEW_GUIDE.md`, `docs/EVALUATION_PROTOCOL.md`, `docs/PROJECT_HANDOFF.md`, `README.md`: final evidence and honest recruiting claims.

### Task 1: Canonicalize Evidence Need IDs and Hop Budgets

**Files:**
- Modify: `src/enterprise_knowledge_rag/retrieval/planning.py`
- Modify: `tests/test_retrieval_planning.py`

**Interfaces:**
- Consumes: validated `RetrievalPlan` objects returned by `StructuredPlanProvider.generate()`.
- Produces: `normalize_retrieval_plan(plan: RetrievalPlan) -> RetrievalPlan` with server-owned IDs and consistent `requires_multi_hop` / `max_hops`.

- [x] **Step 1: Write failing canonicalization tests**

Add tests proving that arbitrary provider IDs are ignored, two required kinds enable two hops, duplicate kinds receive stable suffixes, and fallback remains one-hop:

```python
def test_planner_normalizes_provider_need_ids_and_enables_two_hops() -> None:
    provider = FakeStructuredProvider(
        {
            "primary_query": "extended sick leave",
            "topic": "leave",
            "evidence_needs": [
                {
                    "need_id": "certificate_req",
                    "kind": "material",
                    "query": "medical certificate",
                },
                {
                    "need_id": "emergency_proc",
                    "kind": "exception",
                    "query": "emergency submission",
                },
            ],
            "requires_multi_hop": False,
            "max_hops": 1,
        }
    )

    planned = RetrievalPlanner(provider).plan("extended sick leave", [])

    assert [need.need_id for need in planned.plan.evidence_needs] == [
        "material",
        "exception",
    ]
    assert planned.plan.requires_multi_hop is True
    assert planned.plan.max_hops == 2


def test_normalization_suffixes_duplicate_kinds_stably() -> None:
    plan = RetrievalPlan(
        primary_query="two rules",
        topic="policy",
        evidence_needs=[
            {"need_id": "first", "kind": "rule", "query": "first rule"},
            {"need_id": "second", "kind": "rule", "query": "second rule"},
        ],
        requires_multi_hop=False,
        max_hops=1,
    )

    normalized = normalize_retrieval_plan(plan)

    assert [need.need_id for need in normalized.evidence_needs] == [
        "rule",
        "rule_2",
    ]
```

- [x] **Step 2: Run the tests and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_retrieval_planning.py -q
```

Expected: failures because provider IDs are still preserved and `normalize_retrieval_plan` does not exist.

- [x] **Step 3: Implement minimal server normalization**

In `planning.py`, add a public pure function and apply it only to successful provider plans:

```python
def normalize_retrieval_plan(plan: RetrievalPlan) -> RetrievalPlan:
    kind_counts: dict[str, int] = {}
    normalized_needs: list[EvidenceNeed] = []
    for need in plan.evidence_needs:
        base = need.kind.value
        count = kind_counts.get(base, 0) + 1
        kind_counts[base] = count
        need_id = base if count == 1 else f"{base}_{count}"
        normalized_needs.append(need.model_copy(update={"need_id": need_id}))

    required_count = sum(need.required for need in normalized_needs)
    allows_supplemental = plan.requires_multi_hop or required_count >= 2
    return RetrievalPlan(
        primary_query=plan.primary_query,
        topic=plan.topic,
        departments=plan.departments,
        evidence_needs=normalized_needs,
        requires_multi_hop=allows_supplemental,
        max_hops=2 if allows_supplemental else 1,
    )
```

Return `normalize_retrieval_plan(plan)` from the success path. Do not normalize `_fallback()`; its existing `rule` ID and one-hop budget are already safe.

- [x] **Step 4: Clarify the planner prompt**

Replace the free-ID instruction with:

```text
- kind 只能是 rule、procedure、material、exception、approver、deadline、scope。
- need_id 只需在当前计划内唯一；服务端会根据 kind 重新生成最终 ID。
- 金额门槛和适用条件使用 rule；登记证件和提交材料使用 material。
```

- [x] **Step 5: Run focused and neighboring tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_retrieval_planning.py tests\test_source_models.py tests\test_workflow.py -q
```

Expected: all pass.

- [x] **Step 6: Commit Task 1**

```powershell
git add src/enterprise_knowledge_rag/retrieval/planning.py tests/test_retrieval_planning.py
git commit -m "fix: canonicalize retrieval evidence needs"
```

### Task 2: Tighten Coverage and Exercise Real Supplemental Retrieval

**Files:**
- Modify: `src/enterprise_knowledge_rag/retrieval/coverage.py`
- Modify: `tests/test_evidence_coverage.py`
- Modify: `tests/test_hierarchical_retrieval.py`

**Interfaces:**
- Consumes: canonical `RetrievalPlan` and retrieved `RetrievalCandidate` objects.
- Produces: `EvidenceCoverageService(min_query_token_overlap: float = 0.5)` that accepts explicit need support or sufficient lexical overlap.

- [x] **Step 1: Write failing overlap tests**

Add tests that distinguish meaningful overlap from one generic shared token:

```python
def test_coverage_does_not_mark_a_need_from_one_generic_shared_token() -> None:
    plan = RetrievalPlan(
        primary_query="new supplier",
        topic="procurement",
        evidence_needs=[
            EvidenceNeed(
                need_id="rule",
                kind="rule",
                query="supplier purchase threshold",
            ),
            EvidenceNeed(
                need_id="material",
                kind="material",
                query="supplier registration package",
            ),
        ],
        requires_multi_hop=True,
        max_hops=2,
    )
    threshold = make_candidate(
        "supplier:threshold",
        title="Supplier policy",
        content="A new supplier purchase threshold is 30,000 yuan.",
    )

    result = EvidenceCoverageService(min_query_token_overlap=0.5).cover(
        plan,
        [threshold],
    )

    assert result.covered_need_ids == frozenset({"rule"})
    assert result.missing_required_need_ids == frozenset({"material"})
```

Add constructor validation tests for values below `0` and above `1`.

- [x] **Step 2: Run coverage tests and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_evidence_coverage.py -q
```

Expected: constructor rejects the new argument or incorrectly marks both needs covered.

- [x] **Step 3: Implement ratio-based matching**

Store the validated threshold and replace any-token matching with:

```python
overlap = len(query_tokens.intersection(haystack_tokens)) / len(query_tokens)
if overlap >= self._min_query_token_overlap:
    matched.add(need.need_id)
```

Explicit `supports_need_ids` must continue to count regardless of lexical overlap, subject to the existing Reranker score gate.

- [x] **Step 4: Strengthen hierarchical tests**

Update the existing two-hop fixture so the first candidate covers only `material`, the second call explicitly returns `exception`, and assert:

```python
assert len(sections.calls) == 2
assert result.hop_count == 2
assert result.coverage.covered_need_ids == frozenset({"material", "exception"})
assert result.coverage.missing_required_need_ids == frozenset()
```

Keep the assertion that every call receives only the authorized `leave-policy` key and never the restricted payment key.

- [x] **Step 5: Run retrieval tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_evidence_coverage.py tests\test_hierarchical_retrieval.py tests\test_citations.py tests\test_evidence_builder.py -q
```

Expected: all pass.

- [x] **Step 6: Commit Task 2**

```powershell
git add src/enterprise_knowledge_rag/retrieval/coverage.py tests/test_evidence_coverage.py tests/test_hierarchical_retrieval.py
git commit -m "fix: require meaningful evidence need coverage"
```

### Task 3: Align Development Gold with Canonical IDs

**Files:**
- Modify: `evaluation/development.json`
- Modify: `tests/test_evaluation_dataset_contract.py`
- Test: `tests/test_evaluation_graders.py`

**Interfaces:**
- Consumes: canonical need IDs generated in Task 1.
- Produces: development gold IDs restricted to `EvidenceKind` values with optional numeric suffixes.

- [x] **Step 1: Add a failing development contract test**

```python
import re

from enterprise_knowledge_rag.documents.source_models import EvidenceKind


def test_development_need_ids_use_server_canonical_vocabulary() -> None:
    dataset = load_dataset(PROJECT_ROOT / "evaluation" / "development.json")
    allowed = {kind.value for kind in EvidenceKind}
    for case in dataset.cases:
        for need_id in case.required_need_ids:
            base = re.sub(r"_\d+$", "", need_id)
            assert base in allowed, (case.case_id, need_id)
```

- [x] **Step 2: Run the contract test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation_dataset_contract.py -q
```

Expected: `dev-procurement-supplier-two-hop` fails for `threshold` and `registration`.

- [x] **Step 3: Update development-only gold**

Change only this case:

```json
"required_need_ids": ["rule", "material"]
```

Do not edit `evaluation/frozen_holdout.json`.

- [x] **Step 4: Verify graders and frozen hash**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation_dataset_contract.py tests\test_evaluation_graders.py tests\test_evaluation_runner.py -q
Get-FileHash evaluation\frozen_holdout.json -Algorithm SHA256
```

Expected: tests pass and hash remains `571616F9172881B0196C4D889A1D5D3691905FB7DB035A14EFFB5F7D46CD465D`.

- [x] **Step 5: Commit Task 3**

```powershell
git add evaluation/development.json tests/test_evaluation_dataset_contract.py
git commit -m "test: align development evidence need contract"
```

### Task 4: Make Hybrid RRF the Configurable Demo Default

**Files:**
- Modify: `src/enterprise_knowledge_rag/config.py`
- Modify: `src/enterprise_knowledge_rag/bootstrap.py`
- Modify: `.env.example`
- Modify: `compose.yaml`
- Modify: `tests/test_bootstrap.py`
- Modify: `tests/test_models.py`

**Interfaces:**
- Consumes: `Settings.retrieval_strategy` string validated to one of the three `RetrievalStrategy` values.
- Produces: `_resolve_retrieval_strategy(settings, override) -> RetrievalStrategy`; explicit evaluation overrides remain unchanged.

- [x] **Step 1: Write failing settings and bootstrap tests**

```python
def test_settings_default_to_hybrid_rrf_without_local_env() -> None:
    settings = Settings(_env_file=None)
    assert settings.retrieval_strategy == "hybrid_rrf"


def test_bootstrap_resolves_configured_strategy_and_explicit_override() -> None:
    settings = Settings(_env_file=None, retrieval_strategy="vector_baseline")
    assert _resolve_retrieval_strategy(settings, None) is RetrievalStrategy.VECTOR_BASELINE
    assert (
        _resolve_retrieval_strategy(settings, RetrievalStrategy.HYBRID_RRF_RERANKER)
        is RetrievalStrategy.HYBRID_RRF_RERANKER
    )
```

- [x] **Step 2: Run focused tests and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_bootstrap.py tests\test_models.py -q
```

Expected: missing field and helper failures.

- [x] **Step 3: Implement configuration and resolver**

Add to `Settings`:

```python
retrieval_strategy: Literal[
    "vector_baseline",
    "hybrid_rrf",
    "hybrid_rrf_reranker",
] = "hybrid_rrf"
```

Add to `bootstrap.py`:

```python
def _resolve_retrieval_strategy(
    settings: Settings,
    override: RetrievalStrategy | None,
) -> RetrievalStrategy:
    return override or RetrievalStrategy(settings.retrieval_strategy)
```

Change `build_runtime_service(... retrieval_strategy=None)` and pass the resolved enum into `WorkflowDependencies`.

- [x] **Step 4: Expose the environment setting**

Add `RETRIEVAL_STRATEGY=hybrid_rrf` to `.env.example` and this Compose mapping:

```yaml
RETRIEVAL_STRATEGY: ${RETRIEVAL_STRATEGY:-hybrid_rrf}
```

Do not modify the ignored local `.env` during this task.

- [x] **Step 5: Run bootstrap, runtime, and configuration tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_bootstrap.py tests\test_models.py tests\test_runtime_service.py tests\test_workflow.py -q
```

Expected: all pass.

- [x] **Step 6: Commit Task 4**

```powershell
git add src/enterprise_knowledge_rag/config.py src/enterprise_knowledge_rag/bootstrap.py .env.example compose.yaml tests/test_bootstrap.py tests/test_models.py
git commit -m "feat: configure the default retrieval strategy"
```

### Task 5: Aggregate Repeated Development Reports

**Files:**
- Create: `src/enterprise_knowledge_rag/evaluation/summary.py`
- Create: `scripts/evaluation_support.py`
- Create: `scripts/run_development_smoke.py`
- Create: `tests/test_evaluation_summary.py`
- Create: `tests/test_evaluation_scripts.py`
- Modify: `src/enterprise_knowledge_rag/evaluation/__init__.py`
- Modify: `scripts/run_development.py`

**Interfaces:**
- Produces: `summarize_development_reports(reports: Sequence[EvaluationReport]) -> DevelopmentSummary`.
- Produces: `corpus_snapshot(project_root: Path) -> str` and `code_commit(project_root: Path) -> str`.
- Produces: `build_live_services(settings, connection_factory) -> Mapping[EvaluationStrategy, RuntimeChatService]` shared by development, smoke, and final runners.
- Writes: `evaluation/reports/development-summary.json` after all requested repetitions finish.

- [x] **Step 1: Write failing summary tests**

Create two reports for each strategy with known values and assert:

```python
summary = summarize_development_reports(reports)

hybrid = next(
    item for item in summary.strategies
    if item.strategy is EvaluationStrategy.HYBRID_RRF
)
assert hybrid.repetitions == [1, 2]
assert hybrid.metrics["core_pass_rate"].mean == pytest.approx(0.75)
assert hybrid.metrics["core_pass_rate"].minimum == 0.5
assert hybrid.metrics["core_pass_rate"].maximum == 1.0
assert hybrid.metrics["core_pass_rate"].population_stddev == 0.25
```

Add failure tests for mixed dataset IDs, corpus snapshots, LLM models, and duplicate `(strategy, repetition)` pairs.

- [x] **Step 2: Run the summary test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation_summary.py -q
```

Expected: import failure because the module does not exist.

- [x] **Step 3: Implement structured aggregation**

Define strict models in `summary.py`:

```python
class MetricDistribution(StrictModel):
    count: int = Field(ge=1)
    mean: float
    minimum: float
    maximum: float
    population_stddev: float = Field(ge=0.0)


class StrategyDevelopmentSummary(StrictModel):
    strategy: EvaluationStrategy
    repetitions: list[int]
    metrics: dict[str, MetricDistribution]


class DevelopmentSummary(StrictModel):
    dataset_id: str
    dataset_version: str
    corpus_snapshot: str
    code_commit: str
    llm_model: str
    strategies: list[StrategyDevelopmentSummary]
```

Aggregate these report metrics: execution success, core pass, Recall@5, citation accuracy, leakage, evidence coverage, second-hop trigger accuracy, second-hop success, irrelevant evidence ratio, P50, P95, and model calls. Reject missing strategies or repetition gaps.

- [x] **Step 4: Extract shared report metadata helpers**

Move the corpus hash, commit lookup, and shared live service construction from `run_development.py` into `scripts/evaluation_support.py`. The commit helper must prefer an explicit container value:

```python
def code_commit(project_root: Path) -> str:
    override = os.getenv("EVAL_CODE_COMMIT", "").strip()
    if override:
        return override
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_root,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown0"
```

Test the override without exposing any secret.

Create `run_development_smoke.py`. It must read `EVAL_CASE_ID`, default to `dev-hr-leave-emergency-two-hop`, load only `evaluation/development.json`, select exactly one matching case, run only the configured default strategy, print a JSON object containing case ID, status, hop count, canonical required/covered IDs, citations, and routed document keys, and write no report file. A missing or duplicate case ID must fail before any model or database client is constructed.

- [x] **Step 5: Integrate the summary into the development runner**

Collect all generated `EvaluationReport` objects, write every raw `rN` report, and after the loops write:

```python
summary = summarize_development_reports(generated_reports)
(reports_dir / "development-summary.json").write_text(
    summary.model_dump_json(indent=2),
    encoding="utf-8",
)
```

Write `latest-development.json` only for the strategy selected by `settings.retrieval_strategy`; after three repetitions it therefore points to repetition 3 of the demo default.

- [x] **Step 6: Run evaluation unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation_summary.py tests\test_evaluation_scripts.py tests\test_evaluation_runner.py -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts
```

Expected: all pass and Ruff reports no violations.

- [x] **Step 7: Commit Task 5**

```powershell
git add src/enterprise_knowledge_rag/evaluation scripts/run_development.py scripts/run_development_smoke.py scripts/evaluation_support.py tests/test_evaluation_summary.py tests/test_evaluation_scripts.py
git commit -m "feat: summarize repeated development evaluations"
```

### Task 6: Add an Explicit One-Time Frozen Runner

**Files:**
- Create: `scripts/run_final_holdout.py`
- Modify: `tests/test_evaluation_scripts.py`
- Modify: `docs/EVALUATION_PROTOCOL.md`

**Interfaces:**
- Consumes: committed default `Settings.retrieval_strategy`, frozen SHA-256 constant, and `FROZEN_HOLDOUT_CONFIRM=CONSUME_ONCE`.
- Writes: `evaluation/reports/final-holdout.json`; refuses to overwrite an existing report.

- [x] **Step 1: Write failing guard tests without running any dataset**

Extract a pure guard in the new script and test:

```python
def test_frozen_guard_requires_exact_confirmation(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="CONSUME_ONCE"):
        require_frozen_confirmation("", tmp_path / "final-holdout.json")


def test_frozen_guard_refuses_to_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "final-holdout.json"
    output.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        require_frozen_confirmation("CONSUME_ONCE", output)
```

- [x] **Step 2: Run guard tests and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation_scripts.py -q
```

Expected: import failure because `run_final_holdout.py` does not exist.

- [x] **Step 3: Implement the final runner**

The script must:

1. Verify the frozen file SHA-256 equals the global constraint.
2. Verify exact confirmation and output absence before opening the database or model clients.
3. Use `build_live_services()` and select only the configured default strategy for execution.
4. Call `EvaluationRunner(executor, allow_frozen=True)` once for all 8 cases.
5. Set experiment repetition to `1` and record real commit/model metadata.
6. Write `final-holdout.json` only after the report completes.

Keep all operational code inside `main()` so importing the guard in tests cannot connect to external services.

- [x] **Step 4: Document the irreversible command but do not run it**

Add this exact gate to `docs/EVALUATION_PROTOCOL.md`:

```powershell
$env:FROZEN_HOLDOUT_CONFIRM = "CONSUME_ONCE"
.\.venv\Scripts\python.exe scripts\run_final_holdout.py
```

State that the command is forbidden until Task 7 development conclusions are committed.

- [x] **Step 5: Run script tests and confirm frozen remains untouched**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation_scripts.py tests\test_evaluation_runner.py -q
Get-FileHash evaluation\frozen_holdout.json -Algorithm SHA256
git diff --exit-code -- evaluation/frozen_holdout.json
```

Expected: tests pass, hash matches, and Git shows no frozen diff.

- [x] **Step 6: Commit Task 6**

```powershell
git add scripts/run_final_holdout.py tests/test_evaluation_scripts.py docs/EVALUATION_PROTOCOL.md
git commit -m "feat: gate the final frozen evaluation"
```

### Task 7: Run Controlled Experiments, Freeze, and Finish Recruiting Docs

**Files:**
- Generate: `evaluation/reports/development-*-r1.json`
- Generate: `evaluation/reports/development-*-r2.json`
- Generate: `evaluation/reports/development-*-r3.json`
- Generate: `evaluation/reports/development-summary.json`
- Generate once: `evaluation/reports/final-holdout.json`
- Modify: `evaluation/reports/latest-development.json`
- Modify: `README.md`
- Modify: `docs/INTERVIEW_GUIDE.md`
- Modify: `docs/EVALUATION_PROTOCOL.md`
- Modify: `docs/PROJECT_HANDOFF.md`

**Interfaces:**
- Consumes: Tasks 1-6, the existing Docker database/model cache, and ignored local Bailian credentials.
- Produces: committed repeated development evidence, one frozen report, and consistent recruiting claims.

- [x] **Step 1: Run all deterministic verification before external evaluation**

Run in parallel where possible:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts
npm --prefix frontend run test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build
```

Expected: all commands exit 0; document any intentional skip.

- [x] **Step 2: Run a Docker development smoke**

Use one development answer case through the same mounted source, database, local Embedding, and remote `qwen-plus`. Do not load frozen:

```powershell
$env:POSTGRES_PASSWORD = "development-only-password"
$env:EVAL_CASE_ID = "dev-hr-leave-emergency-two-hop"
$repoPath = (Resolve-Path ".").Path
docker compose -p enterprise-rag-dev run -T --rm --no-deps `
  --volume "${repoPath}:/app" `
  --env PYTHONPATH=/app/src `
  --env EVAL_CASE_ID=$env:EVAL_CASE_ID `
  api python scripts/run_development_smoke.py
```

Expected: the JSON output contains canonical `material` / `exception` IDs, no forbidden document, at least one valid citation, and the observed hop count needed for development diagnosis.

- [x] **Step 3: Commit the fixed code and configuration before the full experiment**

If Task 1-6 commits are already complete and the tree is clean, record:

```powershell
$evalCommit = git rev-parse --short HEAD
```

Do not evaluate an uncommitted source tree.

- [ ] **Step 4: Run three development repetitions in one Docker process**

```powershell
$env:POSTGRES_PASSWORD = "development-only-password"
$env:EVAL_REPETITIONS = "3"
$env:EVAL_CODE_COMMIT = git rev-parse --short HEAD
$repoPath = (Resolve-Path ".").Path
docker compose -p enterprise-rag-dev run -T --rm --no-deps `
  --volume "${repoPath}:/app" `
  --env PYTHONPATH=/app/src `
  --env EVAL_REPETITIONS=3 `
  --env EVAL_CODE_COMMIT=$env:EVAL_CODE_COMMIT `
  api python scripts/run_development.py
```

Expected: nine raw reports and one summary, with all three strategies present for repetitions 1-3.

- [ ] **Step 5: Validate reports and select the final default**

Programmatically assert:

- all JSON parses;
- every report uses the same dataset, corpus snapshot, commit, models, Prompt version, and repetition set;
- every strategy has exactly three repetitions;
- access leakage is 0 in every repetition;
- the two answer multi-hop cases are inspected individually;
- API Key text is absent from every report.

Select the default in this order: leakage, execution/core pass, second-hop/citation quality, then P50/P95/calls. If the aggregate winner differs from `hybrid_rrf`, update `RETRIEVAL_STRATEGY` default, run configuration tests, commit the change, and rerun development three times because the declared fixed configuration changed.

- [ ] **Step 6: Update and commit development conclusions**

Update README and the three docs with exact report-derived means, variation, cold/warm behavior, remaining failures, and the selected default. Commit raw reports and docs:

```powershell
git add evaluation/reports README.md docs/INTERVIEW_GUIDE.md docs/EVALUATION_PROTOCOL.md docs/PROJECT_HANDOFF.md
git commit -m "test: record repeated RAG development evidence"
```

- [ ] **Step 7: Verify the frozen gate preconditions**

Confirm:

```powershell
git status --short
Get-FileHash evaluation\frozen_holdout.json -Algorithm SHA256
Test-Path evaluation\reports\final-holdout.json
```

Expected: clean tree, expected hash, and `False` for the final output.

- [ ] **Step 8: Consume frozen exactly once through Docker**

Run the final script in the same image, mounted committed source, model cache, and database network. Do not retry a completed report or tune from individual failures:

```powershell
$env:POSTGRES_PASSWORD = "development-only-password"
$env:EVAL_CODE_COMMIT = git rev-parse --short HEAD
$repoPath = (Resolve-Path ".").Path
docker compose -p enterprise-rag-dev run -T --rm --no-deps `
  --volume "${repoPath}:/app" `
  --env PYTHONPATH=/app/src `
  --env EVAL_CODE_COMMIT=$env:EVAL_CODE_COMMIT `
  --env FROZEN_HOLDOUT_CONFIRM=CONSUME_ONCE `
  api python scripts/run_final_holdout.py
```

- [ ] **Step 9: Validate and commit final acceptance evidence**

Assert the report split is `frozen_holdout`, case count is 8, `holdout_consumed_at` is set, model/strategy/commit metadata is correct, and the API Key is absent. Update docs with exact results and commit:

```powershell
git add evaluation/reports/final-holdout.json README.md docs/INTERVIEW_GUIDE.md docs/EVALUATION_PROTOCOL.md docs/PROJECT_HANDOFF.md
git commit -m "test: record final RAG holdout evidence"
```

- [ ] **Step 10: Run final verification**

Run fresh full pytest, Ruff, frontend tests/lint/build, Docker readiness, and a standard chat smoke. Confirm `git status --short` is empty and relay the final commits and report-derived interview claims.

---

## Plan Self-Review

- Spec coverage: canonical IDs, bounded two-hop retrieval, leakage protection, configurable default, three repetitions, cold-start evidence, frozen one-time gate, docs, secrets, and full verification are each assigned to a task.
- Placeholder scan: every implementation and failure path has an explicit action.
- Type consistency: Tasks 1-3 use existing `EvidenceNeed`, `RetrievalPlan`, and `EvidenceKind`; Tasks 5-7 use existing `EvaluationReport`, `EvaluationStrategy`, and experiment metadata names.
- Scope: project one, resume generation, applications, and interview drills are intentionally excluded until this plan is complete.
