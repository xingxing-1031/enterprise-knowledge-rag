# Enterprise Knowledge RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: execute this plan task-by-task with a test-first workflow and review each task before proceeding.

**Goal:** Build a reproducible enterprise policy and process RAG assistant that enforces document version, effective-date and role visibility constraints, returns verifiable citations, refuses unsupported answers, and can be demonstrated and evaluated without claiming fictional enterprise deployment.

**Architecture:** Keep deterministic document, access, version, retrieval and citation rules in focused Python services. Use LangGraph only to orchestrate query preparation, retrieval, evidence construction, answer generation and validation. Store document metadata, chunks and vectors in PostgreSQL/pgvector; expose the workflow through FastAPI and a React client.

**Tech Stack:** Python 3.11/3.12, FastAPI, Pydantic v2, LangGraph, psycopg 3, PostgreSQL 16, pgvector, jieba, rank-bm25, sentence-transformers, OpenAI-compatible Qwen/Ollama, React 18, TypeScript, Vite, pytest, Ruff, Docker Compose and GitHub Actions.

## Global Constraints

- New repository: `E:\qiuzhaoxiangmu\enterprise-knowledge-rag`.
- Do not modify or delete `E:\chongqing-wenlv-assistant`.
- All enterprise documents are explicitly labelled synthetic project data; never claim a real company source or user rollout.
- User-facing copy is Chinese; technical IDs, model names and algorithm names may remain English.
- Client-supplied roles are never trusted; roles enter the workflow from server-side session context.
- Permission filtering happens before any candidate text reaches the LLM or public trace.
- Reranker only reorders recalled candidates and cannot repair missing recall.
- Generated answers use only validated `RetrievalEvidence`; insufficient evidence must not fall back to model knowledge.
- Development and frozen holdout data stay separate. A consumed holdout cannot be called unseen again.
- Resume and README metrics must come from committed raw evaluation reports.
- Each task ends with focused tests and a Git commit.

---

## File Map

```text
enterprise-knowledge-rag/
|-- src/enterprise_knowledge_rag/
|   |-- config.py                 # environment settings
|   |-- models.py                 # shared Pydantic contracts
|   |-- app.py                    # FastAPI boundary and trusted session
|   |-- workflow.py               # LangGraph orchestration only
|   |-- documents/
|   |   |-- parser.py             # front matter and Markdown parsing
|   |   |-- chunker.py            # heading-aware chunks
|   |   |-- indexing.py           # deduplication and incremental indexing
|   |   `-- repository.py         # PostgreSQL persistence
|   |-- retrieval/
|   |   |-- lexical.py            # BM25 adapter
|   |   |-- vector.py             # pgvector adapter
|   |   |-- rrf.py                # rank fusion
|   |   |-- reranker.py           # Cross-Encoder adapter
|   |   `-- service.py            # filtered retrieval pipeline
|   |-- policy/
|   |   |-- access.py             # visibility and role rules
|   |   `-- versioning.py         # effective version resolution
|   |-- evidence.py               # minimal sufficient evidence
|   |-- generation.py             # OpenAI-compatible answer adapter
|   |-- citations.py              # citation and claim validation
|   |-- tracing.py                # safe structured stage events
|   `-- evaluation/               # gold models, graders and runner
|-- db/migrations/                # pgvector schema
|-- knowledge/                    # synthetic policy corpus
|-- evaluation/                   # development, frozen and reports
|-- frontend/                     # React demonstration client
|-- tests/                        # Python unit and integration tests
|-- docs/learning/                # consistent study logs
|-- docs/superpowers/             # design and implementation plans
|-- compose.yaml
|-- Dockerfile
|-- pyproject.toml
`-- README.md
```

### Task 1: Reproducible Python Foundation and Domain Contracts

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `src/enterprise_knowledge_rag/__init__.py`
- Create: `src/enterprise_knowledge_rag/config.py`
- Create: `src/enterprise_knowledge_rag/models.py`
- Create: `tests/test_models.py`
- Create: `docs/learning/README.md`
- Create: `docs/learning/W1-1-project-foundation.md`

**Interfaces:**
- Produces `DocumentRecord`, `ChunkRecord`, `UserContext`, `RetrievalCandidate`, `RetrievalEvidence`, `Citation`, `ChatRequest`, `ChatResult` and `RefusalReason`.
- Produces `Settings.from_env()` with no hard-coded local paths or secrets.

- [ ] Write model tests for version/status validation, active-date ranges, restricted visibility, stable IDs and forbidden extra fields.
- [ ] Run `python -m pytest tests/test_models.py -v` and verify the tests initially fail because the package is absent.
- [ ] Add a `src` layout package, Pydantic v2 models and environment settings with explicit defaults for local development.
- [ ] Add dependency groups: runtime, `retrieval`, `models`, and `dev`; pin compatible major versions rather than machine-specific paths.
- [ ] Write a concise README that identifies the project as synthetic enterprise policy data and lists the four fixed demonstration scenarios.
- [ ] Add the shared learning-log template: objective, business problem, implementation, tests, failures, trade-offs, oral questions and standard answer.
- [ ] Run `pytest`, `ruff check src tests` and `ruff format --check src tests`.
- [ ] Commit as `chore: establish enterprise RAG foundation`.

### Task 2: Versioned Synthetic Enterprise Corpus

**Files:**
- Create: `knowledge/hr/*.md`
- Create: `knowledge/finance/*.md`
- Create: `knowledge/procurement/*.md`
- Create: `knowledge/security/*.md`
- Create: `knowledge/admin/*.md`
- Create: `knowledge/README.md`
- Create: `tests/fixtures/knowledge_cases.json`
- Create: `tests/test_corpus_contract.py`
- Create: `docs/learning/W1-2-enterprise-corpus.md`

**Interfaces:**
- Each Markdown file starts with validated YAML metadata matching `DocumentRecord` fields.
- Each file contains stable heading paths that later become citation anchors.

- [ ] Write a corpus contract test that rejects missing IDs, invalid dates, duplicate active versions, missing replacement links and unlabelled restricted documents.
- [ ] Create synthetic policies covering leave, overtime, onboarding, reimbursement, travel, invoices, purchasing, supplier access, account permissions, device use, seals and assets.
- [ ] Include active, expired, revoked and future versions, plus department-only and restricted examples.
- [ ] Include table, list, exception and cross-reference sections so chunking is not tested only on paragraphs.
- [ ] Add a manifest stating that all organizations, amounts and processes are constructed for this project.
- [ ] Run corpus contract tests and save the actual document/version counts in the learning log.
- [ ] Commit as `data: add versioned synthetic policy corpus`.

### Task 3: Heading-Aware Parsing and Chunking

**Files:**
- Create: `src/enterprise_knowledge_rag/documents/__init__.py`
- Create: `src/enterprise_knowledge_rag/documents/parser.py`
- Create: `src/enterprise_knowledge_rag/documents/chunker.py`
- Create: `tests/test_document_parser.py`
- Create: `tests/test_chunker.py`
- Create: `docs/learning/W2-1-document-processing.md`

**Interfaces:**
- `parse_document(path: Path) -> ParsedDocument`
- `chunk_document(document: ParsedDocument, max_tokens: int, overlap_tokens: int) -> list[ChunkRecord]`

- [ ] Test UTF-8 front matter, nested headings, tables, lists, malformed metadata and deterministic stable IDs.
- [ ] Parse front matter through a YAML parser rather than string splitting.
- [ ] Preserve `section_path` and avoid crossing top-level section boundaries.
- [ ] Use token-aware limits with paragraph/list/table boundaries before fallback splitting.
- [ ] Compute content hashes from normalized content and metadata used by retrieval.
- [ ] Verify repeated parsing produces identical document and chunk IDs.
- [ ] Commit as `feat: parse and chunk structured policy documents`.

### Task 4: PostgreSQL/pgvector Schema and Incremental Indexing

**Files:**
- Create: `db/migrations/001_extensions.sql`
- Create: `db/migrations/002_knowledge_schema.sql`
- Create: `db/migrations/003_indexes.sql`
- Create: `src/enterprise_knowledge_rag/documents/repository.py`
- Create: `src/enterprise_knowledge_rag/documents/indexing.py`
- Create: `tests/test_incremental_indexing.py`
- Create: `tests/integration/test_pgvector_repository.py`
- Create: `compose.yaml`
- Create: `docs/learning/W2-2-incremental-indexing.md`

**Interfaces:**
- `KnowledgeRepository.upsert_document(record, chunks, embeddings) -> IndexingSummary`
- `IndexingService.index_paths(paths: list[Path]) -> IndexingRun`

- [ ] Test new, unchanged, changed, superseded and duplicate documents with a fake repository.
- [ ] Create tables for documents, chunks, embeddings and indexing runs with foreign keys and unique content hashes.
- [ ] Store the embedding model/version with each vector.
- [ ] Delete obsolete chunks only inside the same document update transaction.
- [ ] Add a Compose PostgreSQL 16 pgvector service and a readiness check.
- [ ] Run integration tests against an empty temporary database and again against already indexed data.
- [ ] Commit as `feat: persist incremental pgvector knowledge index`.

### Task 5: Deterministic Access and Version Policy

**Files:**
- Create: `src/enterprise_knowledge_rag/policy/__init__.py`
- Create: `src/enterprise_knowledge_rag/policy/access.py`
- Create: `src/enterprise_knowledge_rag/policy/versioning.py`
- Create: `tests/test_access_policy.py`
- Create: `tests/test_version_policy.py`
- Create: `docs/learning/W3-1-policy-boundaries.md`

**Interfaces:**
- `can_access(user: UserContext, document: DocumentRecord) -> bool`
- `resolve_effective_versions(documents, as_of: datetime, requested_version: str | None) -> VersionResolution`

- [ ] Test public, department and restricted access without exposing hidden titles.
- [ ] Test active, expired, revoked, future, historical and ambiguous versions.
- [ ] Ensure administrator access does not revive revoked or not-yet-effective policy by default.
- [ ] Make denial reasons structured for internal trace and generic for public responses.
- [ ] Commit as `feat: enforce document access and effective versions`.

### Task 6: BM25, Vector Recall and RRF Fusion

**Files:**
- Create: `src/enterprise_knowledge_rag/retrieval/__init__.py`
- Create: `src/enterprise_knowledge_rag/retrieval/lexical.py`
- Create: `src/enterprise_knowledge_rag/retrieval/vector.py`
- Create: `src/enterprise_knowledge_rag/retrieval/rrf.py`
- Create: `tests/test_lexical_retrieval.py`
- Create: `tests/test_vector_retrieval.py`
- Create: `tests/test_rrf.py`
- Create: `docs/learning/W3-2-hybrid-retrieval.md`

**Interfaces:**
- `LexicalRetriever.search(query, filters, limit) -> list[RetrievalCandidate]`
- `VectorRetriever.search(query_vector, filters, limit) -> list[RetrievalCandidate]`
- `reciprocal_rank_fusion(rankings, k=60) -> list[RetrievalCandidate]`

- [ ] Test BM25 exact policy names, identifiers and Chinese tokenization.
- [ ] Test vector adapter filter forwarding and score normalization boundaries.
- [ ] Test RRF with disjoint, overlapping and duplicate rankings; assert original channel ranks remain observable.
- [ ] Apply access, status and effective-date filters before candidate content leaves the repository.
- [ ] Do not add incomparable BM25 and cosine scores directly.
- [ ] Commit as `feat: add filtered hybrid retrieval with RRF`.

### Task 7: Reranking and Minimal Sufficient Evidence

**Files:**
- Create: `src/enterprise_knowledge_rag/retrieval/reranker.py`
- Create: `src/enterprise_knowledge_rag/retrieval/service.py`
- Create: `src/enterprise_knowledge_rag/evidence.py`
- Create: `tests/test_reranker.py`
- Create: `tests/test_retrieval_service.py`
- Create: `tests/test_evidence_builder.py`
- Create: `docs/learning/W4-1-evidence-retrieval.md`

**Interfaces:**
- `Reranker.rerank(query, candidates, limit) -> list[RetrievalCandidate]`
- `RetrievalService.retrieve(query, user, as_of) -> RetrievalResult`
- `build_minimal_evidence(question, candidates) -> list[RetrievalEvidence]`

- [ ] Test that reranking never introduces an unseen chunk.
- [ ] Test same-section deduplication, conflicting-version removal and evidence budget limits.
- [ ] Return a structured insufficient-evidence result when no candidate clears configured thresholds.
- [ ] Keep deterministic fake Embedding and Reranker adapters for CI; load real models only through runtime configuration.
- [ ] Commit as `feat: construct reranked minimal evidence`.

### Task 8: Answer Generation, Citation Validation and Refusal

**Files:**
- Create: `src/enterprise_knowledge_rag/generation.py`
- Create: `src/enterprise_knowledge_rag/citations.py`
- Create: `tests/test_generation.py`
- Create: `tests/test_citations.py`
- Create: `tests/test_refusal.py`
- Create: `docs/learning/W4-2-grounded-answering.md`

**Interfaces:**
- `AnswerGenerator.generate(question, evidence, history) -> DraftAnswer`
- `validate_citations(draft, evidence) -> CitationValidation`

- [ ] Require structured output with answer paragraphs and cited `evidence_id` values.
- [ ] Test nonexistent citations, wrong versions, uncited numbers, dates and approval levels.
- [ ] Permit one bounded regeneration after citation validation failure.
- [ ] On a second failure, return a trusted evidence summary with a degradation reason.
- [ ] Never call generation for permission denial, out-of-scope or empty evidence.
- [ ] Commit as `feat: validate grounded answers and refusals`.

### Task 9: LangGraph Workflow and Safe Trace

**Files:**
- Create: `src/enterprise_knowledge_rag/workflow.py`
- Create: `src/enterprise_knowledge_rag/tracing.py`
- Create: `tests/test_workflow.py`
- Create: `tests/test_tracing.py`
- Create: `docs/learning/W5-1-rag-workflow.md`

**Interfaces:**
- `build_workflow(dependencies: WorkflowDependencies) -> CompiledStateGraph`
- `run_chat(request, user) -> ChatResult`

- [ ] Define state for original query, rewritten query, trusted user, retrieval, evidence, draft, validation, status and trace.
- [ ] Add domain, rewrite, retrieve, evidence, generate, validate and finalize nodes with explicit conditional edges.
- [ ] Add finite retries and total time budget only to transient model operations.
- [ ] Ensure traces include counts, ranks and timings but never hidden chunk text or secrets.
- [ ] Test success, historical version, permission denial, insufficient evidence and degraded generation paths.
- [ ] Commit as `feat: orchestrate auditable RAG workflow`.

### Task 10: FastAPI, Trusted Sessions and SSE

**Files:**
- Create: `src/enterprise_knowledge_rag/app.py`
- Create: `tests/test_app.py`
- Create: `tests/test_sse.py`
- Create: `docs/learning/W5-2-api-streaming.md`

**Interfaces:**
- Provide `/health`, `/ready`, `/session`, `/chat`, `/chat/stream`, `/chat/clear`, `/documents`, `/documents/index` and `/evaluations/latest`.

- [ ] Test that request bodies cannot escalate roles.
- [ ] Test public mode hides restricted document existence and raw internal errors.
- [ ] Emit stable Chinese SSE stage labels without exposing chain-of-thought.
- [ ] Separate refusal, failure and degradation HTTP/result semantics.
- [ ] Restrict CORS through configuration and validate request sizes.
- [ ] Commit as `feat: expose trusted chat and streaming API`.

### Task 11: Controlled Evaluation Harness

**Files:**
- Create: `src/enterprise_knowledge_rag/evaluation/models.py`
- Create: `src/enterprise_knowledge_rag/evaluation/graders.py`
- Create: `src/enterprise_knowledge_rag/evaluation/runner.py`
- Create: `evaluation/development.json`
- Create: `evaluation/frozen_holdout.json`
- Create: `tests/test_evaluation_graders.py`
- Create: `docs/EVALUATION_PROTOCOL.md`
- Create: `docs/learning/W6-1-evaluation.md`

**Interfaces:**
- `EvaluationRunner.run(dataset, strategy, snapshot) -> EvaluationReport`
- Stage scores: domain, recall, ranking, access, version, citation, refusal and answer.

- [ ] Create gold cases for exact terms, paraphrases, versions, permissions, cross-section answers and refusal.
- [ ] Keep frozen answers inaccessible to runtime code and mark consumption metadata in reports.
- [ ] Implement Recall@K, MRR, nDCG, version accuracy, citation accuracy, correct refusal, false refusal, latency and model calls.
- [ ] Compare vector baseline, hybrid RRF and hybrid RRF plus Reranker with all other variables frozen.
- [ ] Run a smoke subset before a full development experiment.
- [ ] Do not consume frozen holdout until the application and evaluation code are reviewed and fixed.
- [ ] Commit as `test: add controlled enterprise RAG evaluation`.

### Task 12: React Demonstration Client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/styles.css`
- Create: focused components under `frontend/src/components/`
- Create: `frontend/src/*.test.tsx`
- Create: `docs/learning/W7-1-demo-client.md`

**Interfaces:**
- Consume the Task 10 API unchanged.
- Display answer, references, versions, safe retrieval stages and status.

- [ ] Build a desktop workbench with navigation, conversation, evidence and evaluation views.
- [ ] Use a single-column mobile layout with evidence and retrieval details in bottom sheets.
- [ ] Add success, loading, refusal, failure, degraded and empty states.
- [ ] Keep user text Chinese and technical identifiers selectable and copyable.
- [ ] Validate 1440px, 390px and 360px viewports with Playwright screenshots and no horizontal overflow.
- [ ] Commit as `feat: add enterprise knowledge workbench`.

### Task 13: Packaging, CI and Clean-Environment Verification

**Files:**
- Create: `Dockerfile`
- Modify: `compose.yaml`
- Create: `.dockerignore`
- Create: `.github/workflows/ci.yml`
- Create: `scripts/migrate.py`
- Create: `scripts/index_knowledge.py`
- Create: `docs/OPERATIONS.md`
- Create: `docs/learning/W7-2-delivery.md`

**Interfaces:**
- One migration command and one indexing command work locally and in containers.
- API serves the built frontend from the same origin for simple public demonstration.

- [ ] Run Python 3.11/3.12 tests and Ruff in CI.
- [ ] Run TypeScript tests and production build in CI.
- [ ] Start PostgreSQL from an empty CI volume, apply migrations, index corpus and execute retrieval smoke tests.
- [ ] Build the final Docker image without local model caches or secrets.
- [ ] Verify `/ready` only succeeds after database schema and knowledge snapshot are ready.
- [ ] Commit as `ci: verify enterprise RAG in clean environments`.

### Task 14: Final Holdout, Handoff and Resume Evidence

**Files:**
- Create: `evaluation/reports/final_holdout.json`
- Create: `docs/FINAL_ACCEPTANCE.md`
- Create: `docs/PROJECT_HANDOFF.md`
- Create: `docs/INTERVIEW_GUIDE.md`
- Modify: `README.md`
- Modify: all learning logs with actual evidence

**Interfaces:**
- Final report records corpus hash, code commit, model versions, parameters and holdout consumption time.

- [ ] Review all development failures and freeze code/configuration before the holdout run.
- [ ] Run frozen holdout exactly once and preserve raw per-case results, including failures.
- [ ] Update README and resume evidence only from actual reports and deployed state.
- [ ] Add interview questions covering chunking, BM25/vector differences, RRF, Reranker limits, pre-filtering, versions, citations, refusals and evaluation leakage.
- [ ] Record known boundaries: synthetic corpus, demonstration identity, no multi-tenant SSO and no production users.
- [ ] Run full Python, database, frontend and Docker verification.
- [ ] Commit as `docs: record final enterprise RAG acceptance`.

## Execution Order and Review Gates

- Gate A after Tasks 1-3: domain contracts and document pipeline are understandable without LLM or database availability.
- Gate B after Tasks 4-7: filtered retrieval returns version-correct evidence and cannot leak restricted text.
- Gate C after Tasks 8-10: end-to-end chat handles the four fixed scenarios with stable statuses and citations.
- Gate D after Tasks 11-13: controlled evaluation and clean-environment delivery are reproducible.
- Gate E after Task 14: final claims match raw evidence; only then write the final resume bullets.

Implementation proceeds inline in the current project conversation because the user requested immediate execution and no parallel subagent work is authorized. Each gate gets a concise user-facing learning checkpoint before the next phase.
