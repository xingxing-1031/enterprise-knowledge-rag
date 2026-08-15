# Trustworthy Agentic RAG v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the enterprise knowledge service into a bounded Agentic RAG pipeline with per-need semantic coverage, iterative retrieval, correct permission refusal, current-corpus evaluation, and interview-defensible evidence.

**Architecture:** Preserve the existing LangGraph, retrieval, authorization, and evidence boundaries. Move conversational rewriting before domain classification, enrich the parent-document representation, score evidence against each structured need, and let one bounded supplemental phase reroute only inside the authorized version set. Extend evaluation without rewriting historical reports or reusing the consumed holdout.

**Tech Stack:** Python 3.11, FastAPI, LangGraph, Pydantic v2, PostgreSQL/pgvector, BM25, BGE-M3, BGE Reranker, pytest, React/TypeScript/Vite.

## Global Constraints

- Keep all authorization and version decisions server-side.
- Never expose restricted document content or identifiers in public refusals.
- Limit evidence needs to four and retrieval phases to two.
- Keep final evidence within the configured item and token budgets.
- Preserve the old development and frozen-holdout files and reports as historical evidence.
- New resume metrics must identify the synthetic corpus, case count, model, snapshot, repetitions, and limitations.
- Real model/API calls are optional for local tests and required only for a new development experiment when the configured services are available.

---

### Task 1: Contextual Query Understanding and Domain Coverage

**Files:**
- Modify: `src/enterprise_knowledge_rag/runtime.py`
- Modify: `src/enterprise_knowledge_rag/workflow.py`
- Test: `tests/test_runtime_service.py`
- Test: `tests/test_workflow.py`

**Interfaces:**
- Consumes: `QueryRewriter.rewrite(question, history) -> str` and `DomainClassifier.is_in_scope(question) -> bool`.
- Produces: `ContextualQueryRewriter`, plus a workflow that rewrites before classifying the rewritten query.

- [ ] Add a failing test proving `退款申请需要多久内提交？`, `周度运营复盘需要看哪些指标？`, and `门店销售额下降时应该怎么复盘？` are in scope.
- [ ] Add a failing test proving history `报销期限是多久？` followed by `那票据呢？` rewrites to an independently searchable enterprise query.
- [ ] Add a failing workflow test proving domain classification receives the rewritten query rather than the raw pronoun-only follow-up.
- [ ] Run `./.venv/Scripts/python.exe -m pytest tests/test_runtime_service.py tests/test_workflow.py -q` and verify the new tests fail for the expected behavior.
- [ ] Replace `IdentityQueryRewriter` with a deterministic bounded rewriter that only prepends the latest user topic when the current question is a short referential follow-up; do not use an extra model call.
- [ ] Extend `ENTERPRISE_TERMS` with the current retail and operations vocabulary.
- [ ] Reorder the graph to `rewrite -> domain -> plan/retrieve` and preserve out-of-scope short-circuiting.
- [ ] Run the focused tests and verify they pass.
- [ ] Commit the vertical slice.

### Task 2: Parent Document Routing Representation

**Files:**
- Modify: `src/enterprise_knowledge_rag/documents/indexing.py`
- Test: `tests/test_incremental_indexing.py`
- Test: `tests/test_document_routing.py`

**Interfaces:**
- Consumes: parsed Markdown body and `DocumentRecord` metadata.
- Produces: bounded `document_search_text` containing metadata, H1/H2 headings, and the first paragraph under each H2.

- [ ] Add a failing indexing test with the asset policy and assert the routing representation contains `异常处理`, `遗失`, and `1 个工作日`.
- [ ] Add a failing router test proving `公司电脑丢失后最迟什么时候报备？` can lexically route the asset document when its section summary is indexed.
- [ ] Run both focused tests and verify red.
- [ ] Replace the H1-only builder with a line parser that includes H1/H2 headings and one normalized paragraph per H2, capped at 2,000 characters.
- [ ] Preserve stable ordering and deduplication so unchanged content produces unchanged parent embeddings.
- [ ] Run the focused tests and verify green.
- [ ] Commit the vertical slice.

### Task 3: Per-Need Semantic Coverage

**Files:**
- Modify: `src/enterprise_knowledge_rag/retrieval/coverage.py`
- Modify: `src/enterprise_knowledge_rag/bootstrap.py`
- Test: `tests/test_evidence_coverage.py`

**Interfaces:**
- Introduce: `EvidenceNeedScoreProvider.score(query: str, passages: Sequence[str]) -> list[float]`.
- Preserve: `EvidenceCoverageService.cover(plan, candidates) -> CoverageResult`.
- Produce: coverage annotations based on independent need-to-passage decisions.

- [ ] Add a failing test proving one medical-certificate paragraph cannot cover both `material` and `exception` merely because it matches the primary query.
- [ ] Add a failing test using a deterministic multilingual scorer proving English `expense submission deadline` covers the Chinese `报销期限` paragraph.
- [ ] Add a failing test proving scores below the semantic threshold do not create support.
- [ ] Run `./.venv/Scripts/python.exe -m pytest tests/test_evidence_coverage.py -q` and verify red.
- [ ] Batch-score every unresolved need against eligible passages and annotate each candidate only with needs whose lexical or semantic threshold passes.
- [ ] Restrict the primary-query bridge to plans with exactly one required need.
- [ ] If no scorer is configured, use lexical coverage only; never trust stale `supports_need_ids` from a previous phase.
- [ ] Inject the existing reranker score provider into coverage from `build_runtime_service`, without creating a second model instance.
- [ ] Run focused coverage and bootstrap tests and verify green.
- [ ] Commit the vertical slice.

### Task 4: Bounded Iterative Retrieval and Permission Refusal

**Files:**
- Modify: `src/enterprise_knowledge_rag/retrieval/hierarchical.py`
- Modify: `src/enterprise_knowledge_rag/retrieval/routing.py`
- Test: `tests/test_hierarchical_retrieval.py`
- Test: `tests/test_access_policy.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Preserve: `HierarchicalRetrievalService.retrieve(...) -> HierarchicalRetrievalResult`.
- Produce: supplemental routing for missing needs and a query-related denied metadata count.

- [ ] Add a failing test in which the first route contains only the certificate document and the missing exception need reroutes to a second authorized document.
- [ ] Add a failing test proving supplemental routes never contain unauthorized document keys.
- [ ] Add a failing integrated test proving an employee asking for the restricted payment approval table receives `permission_denied`, while an uncovered bonus question receives `insufficient_evidence`.
- [ ] Add an API test proving `/internal/evidence` preserves the refusal reason and returns no restricted evidence.
- [ ] Run focused tests and verify red.
- [ ] Retain sanitized route sources for effective but unauthorized documents and compute query-related denied matches without loading chunks.
- [ ] For each missing required need, reroute `topic + kind + query` over the full authorized version set, merge new route keys, and retrieve once.
- [ ] Return permission denial only when final authorized evidence is absent and sanitized denied metadata matches the query.
- [ ] Preserve route, item, token, version, and two-phase limits.
- [ ] Run focused tests and verify green.
- [ ] Commit the vertical slice.

### Task 5: Evaluation Observability and Metrics v2

**Files:**
- Modify: `src/enterprise_knowledge_rag/evaluation/models.py`
- Modify: `src/enterprise_knowledge_rag/evaluation/graders.py`
- Modify: `src/enterprise_knowledge_rag/evaluation/runner.py`
- Modify: `src/enterprise_knowledge_rag/evaluation/executor.py`
- Modify: `src/enterprise_knowledge_rag/evaluation/summary.py`
- Modify: `scripts/evaluation_support.py`
- Test: `tests/test_evaluation_graders.py`
- Test: `tests/test_evaluation_runner.py`
- Test: `tests/test_evaluation_summary.py`
- Test: `tests/test_evaluation_executor.py`

**Interfaces:**
- Extend `EvaluationObservation` with safe stage timings and stage error code.
- Extend `CaseMetrics`/`AggregateMetrics` with citation recall, fact completeness, refusal confusion counts, need coverage precision, timeout rate, and p99 latency.
- Add report freshness comparison against the current corpus snapshot.

- [ ] Add a failing grader test for citation recall when only one of two gold citations is cited.
- [ ] Add a failing grader test for need coverage precision when the runtime claims unsupported need IDs.
- [ ] Add a failing runner test proving timeout and safe stage code remain in the denominator without exposing provider messages.
- [ ] Add a failing aggregate test for P99 and refusal reason confusion counts.
- [ ] Add a failing freshness test when report snapshot differs from the current corpus snapshot.
- [ ] Run focused evaluation tests and verify red.
- [ ] Implement the smallest compatible model extensions with defaults so historical JSON reports remain readable.
- [ ] Derive stage timings from workflow trace and map model boundary failures to safe stage codes.
- [ ] Add the new fields to development summary distributions.
- [ ] Run focused tests and verify green.
- [ ] Commit the vertical slice.

### Task 6: Evaluation Datasets v2

**Files:**
- Create: `evaluation/development-v2.json`
- Create: `evaluation/frozen-holdout-v2.json`
- Modify: `src/enterprise_knowledge_rag/evaluation/models.py`
- Modify: `tests/test_evaluation_dataset_contract.py`
- Modify: `scripts/run_development.py`
- Create: `scripts/run_final_holdout_v2.py`

**Interfaces:**
- Preserve the existing `EvaluationDataset` schema while adding optional case tags for capability slicing.
- `run_development.py` loads development-v2 by default.
- `run_final_holdout_v2.py` requires `FROZEN_HOLDOUT_V2_CONFIRM=CONSUME_V2_ONCE` and refuses to overwrite an existing report.

- [ ] Add failing contract tests requiring 60-80 development cases, all 24 logical document IDs in positive gold coverage, every role, every department, at least 12 multi-hop cases, at least 8 refusal cases, and the planned robustness tags.
- [ ] Add a failing test proving the v2 holdout is locked and has 20-30 unique, non-development questions.
- [ ] Run dataset contract tests and verify red.
- [ ] Build development-v2 from independently verified facts in the current Markdown corpus; include case tags for document, role, version, language, robustness, and retrieval depth.
- [ ] Build a new locked holdout-v2 without copying development questions or the consumed holdout questions.
- [ ] Update runners without modifying historical dataset files or reports.
- [ ] Run contract tests and verify green.
- [ ] Commit the vertical slice.

### Task 7: Full Verification and Current-Snapshot Experiment

**Files:**
- Update only generated reports produced by successful commands under `evaluation/reports/`.
- Modify documentation files in Task 8 after evidence exists.

**Interfaces:**
- Verification commands are the source of truth; no metric is written manually.

- [ ] Run `./.venv/Scripts/python.exe -m ruff check src tests scripts`.
- [ ] Run `./.venv/Scripts/python.exe -m pytest -q`.
- [ ] Run PostgreSQL/pgvector integration tests when Docker and the configured database are available.
- [ ] Run `npm test`, `npm run lint`, and `npm run build` in `frontend/`.
- [ ] Verify the database has indexed all current manifest documents and current parent embeddings.
- [ ] If model, embedding, reranker, and database services are available, run a development-v2 smoke test, then three equal repetitions across all strategies.
- [ ] Do not consume frozen-holdout-v2 during development.
- [ ] Inspect per-case failures and report actual outcomes; do not tune against the new holdout.

### Task 8: Documentation, Resume Evidence, and Delivery

**Files:**
- Modify: `docs/EVALUATION_PROTOCOL.md`
- Modify: `docs/RESUME_EVIDENCE_RAG.md`
- Modify: `docs/INTERVIEW_GUIDE_RAG.md`
- Modify: `docs/PROJECT_HANDOFF.md`
- Modify: `README.md`

**Interfaces:**
- Documentation consumes only committed tests and generated evaluation reports.

- [ ] Document Agentic RAG, Query Decomposition, Iterative Retrieval, and Multi-hop Retrieval, while explaining that two phases are a bounded runtime budget.
- [ ] Record the development-v2 dataset composition, snapshot, model, repetitions, actual metrics, failures, and limitations.
- [ ] Add interview explanations for why per-need coverage, supplemental routing, permission-aware refusal, and frozen evaluation matter.
- [ ] Update the resume evidence wording using only measured results.
- [ ] Run link/path checks, `git diff --check`, full tests, and frontend build once more.
- [ ] Review `git diff` for secrets, stale Qixi names, untracked files, and accidental historical report changes.
- [ ] Commit the final documentation and verified generated evidence.
- [ ] Push `main` to `origin` after all verification succeeds.

