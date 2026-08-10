# Deep Enterprise RAG Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a controlled enterprise document ingestion pipeline and replace flat one-shot retrieval with structured planning, hierarchical routing, and bounded two-hop evidence completion.

**Architecture:** Normalize supported files into one canonical document contract, require administrator review before indexing, and store both parent-document and child-section vectors in PostgreSQL/pgvector. A validated retrieval plan decomposes each question into explicit evidence needs; authorized document routing and section retrieval run separately, and a second hop occurs only for uncovered required needs. Evidence coverage and citation completeness remain deterministic services around the LLM.

**Tech Stack:** Python 3.11/3.12, Pydantic v2, FastAPI, LangGraph, psycopg 3, PostgreSQL 16, pgvector, pypdf, python-docx, charset-normalizer, sentence-transformers, React 18, TypeScript, Vitest, Playwright, pytest, Ruff, Docker Compose and GitHub Actions.

## Global Constraints

- Supported source formats are `.pdf`, `.docx`, `.md` and `.txt`; OCR is out of scope.
- Maximum source size is 15 MiB and maximum PDF length is 200 pages.
- Scanned, empty, damaged, unsupported or over-limit files are quarantined and never indexed.
- Department, visibility, allowed roles, version and effective dates require server-side administrator confirmation.
- User identity, access policy, query time and version validity never come from model output.
- Retrieval plans contain at most four evidence needs and `max_hops` is exactly `1` or `2`.
- The second hop repeats the same authorization, version and publication filters as the first hop.
- Final evidence contains at most six chunks and at most 1200 approximate tokens.
- GraphRAG, Neo4j, HyDE, unbounded Agentic Search, OCR, model fine-tuning and GRPO are out of scope.
- The frozen holdout dataset must not be executed during implementation.
- Do not write accuracy or improvement claims until real reports exist.

---

## File Map

### New backend files

- `src/enterprise_knowledge_rag/documents/source_models.py`: source, extraction, cleaning and import contracts.
- `src/enterprise_knowledge_rag/documents/extractors.py`: PDF, DOCX, Markdown and text adapters.
- `src/enterprise_knowledge_rag/documents/cleaning.py`: deterministic cleaning and diagnostic report.
- `src/enterprise_knowledge_rag/documents/import_repository.py`: import-job persistence.
- `src/enterprise_knowledge_rag/documents/ingestion.py`: preview, approve, quarantine and idempotency service.
- `src/enterprise_knowledge_rag/retrieval/planning.py`: evidence-needs retrieval plan and degraded fallback.
- `src/enterprise_knowledge_rag/retrieval/routing.py`: authorized parent-document routing.
- `src/enterprise_knowledge_rag/retrieval/coverage.py`: evidence-need coverage and supplemental-query construction.
- `src/enterprise_knowledge_rag/retrieval/hierarchical.py`: parent route, section retrieval and bounded second hop.
- `db/migrations/004_ingestion_and_document_routing.sql`: import records and parent vectors.

### Existing files with focused changes

- `src/enterprise_knowledge_rag/models.py`: retrieval evidence and workflow-facing contracts only.
- `src/enterprise_knowledge_rag/documents/indexing.py`: canonical-document and parent-vector indexing.
- `src/enterprise_knowledge_rag/documents/repository.py`: parent-vector persistence/search.
- `src/enterprise_knowledge_rag/retrieval/service.py`: authorized section retrieval within routed documents.
- `src/enterprise_knowledge_rag/workflow.py`: planning, routing, coverage and supplemental nodes.
- `src/enterprise_knowledge_rag/citations.py`: required-need citation completeness.
- `src/enterprise_knowledge_rag/runtime.py`: ingestion endpoints and workflow observations.
- `src/enterprise_knowledge_rag/app.py`: administrator import API and public stage labels.
- `src/enterprise_knowledge_rag/bootstrap.py`: dependency wiring.
- `frontend/src/components/KnowledgeView.tsx`: administrator import and review surface.
- `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/styles.css`: typed client and states.
- `evaluation/development.json`: development-only multi-hop cases.
- `README.md`, `docs/OPERATIONS.md`, `.env.example`, `compose.yaml`: delivery contract.

---

### Task 1: Add Source, Ingestion and Retrieval Plan Contracts

**Files:**
- Create: `src/enterprise_knowledge_rag/documents/source_models.py`
- Modify: `src/enterprise_knowledge_rag/models.py`
- Modify: `src/enterprise_knowledge_rag/documents/__init__.py`
- Create: `tests/test_source_models.py`
- Modify: `tests/test_models.py`

**Interfaces:**
- Produces `SourceFile`, `ExtractedBlock`, `ExtractedDocument`, `CleanedDocument`, `CleaningIssue`, `CleaningReport`, `ImportMetadata`, `ImportPreview`, `IngestionStatus`, `EvidenceKind`, `EvidenceNeed` and `RetrievalPlan`.
- Extends `RetrievalEvidence` with `supports_need_ids: set[str]` and `retrieval_hop: Literal[1, 2]`, both with backward-compatible defaults.

- [ ] **Step 1: Write failing validation tests**

```python
def test_retrieval_plan_rejects_more_than_four_needs() -> None:
    needs = [
        EvidenceNeed(need_id=f"n{i}", kind="rule", query=f"问题{i}")
        for i in range(5)
    ]
    with pytest.raises(ValidationError):
        RetrievalPlan(
            primary_query="请假规则",
            topic="请假",
            departments={"hr"},
            evidence_needs=needs,
            requires_multi_hop=True,
            max_hops=2,
        )


def test_scanned_pdf_preview_cannot_be_approved() -> None:
    preview = make_preview(status=IngestionStatus.QUARANTINED)
    assert preview.can_approve is False
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_source_models.py tests/test_models.py -q`

Expected: collection fails because the contracts do not exist.

- [ ] **Step 3: Implement strict contracts**

```python
class EvidenceNeed(StrictModel):
    need_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    kind: EvidenceKind
    query: str = Field(min_length=2, max_length=300)
    required: bool = True


class RetrievalPlan(StrictModel):
    primary_query: str = Field(min_length=2, max_length=500)
    topic: str = Field(min_length=1, max_length=80)
    departments: set[str] = Field(default_factory=set)
    evidence_needs: list[EvidenceNeed] = Field(min_length=1, max_length=4)
    requires_multi_hop: bool = False
    max_hops: Literal[1, 2] = 1
```

Use enums for ingestion status and issue severity. Keep raw filesystem paths out of API models.

- [ ] **Step 4: Run focused and existing model tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_source_models.py tests/test_models.py -q`

Expected: all focused tests pass.

- [ ] **Step 5: Commit the contracts**

```powershell
git add src/enterprise_knowledge_rag/documents/source_models.py src/enterprise_knowledge_rag/documents/__init__.py src/enterprise_knowledge_rag/models.py tests/test_source_models.py tests/test_models.py
git commit -m "feat: define enterprise ingestion and retrieval contracts"
```

---

### Task 2: Implement File Extraction and Deterministic Cleaning

**Files:**
- Create: `src/enterprise_knowledge_rag/documents/extractors.py`
- Create: `src/enterprise_knowledge_rag/documents/cleaning.py`
- Create: `tests/test_document_extractors.py`
- Create: `tests/test_document_cleaning.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes `SourceFile` and produces `ExtractedDocument`.
- Produces `ExtractorRegistry.extract(source: SourceFile) -> ExtractedDocument`.
- Produces `DocumentCleaningService.clean(document: ExtractedDocument) -> CleanedDocument`.

- [ ] **Step 1: Add parser dependencies and failing tests**

Production dependencies:

```toml
"charset-normalizer>=3,<4",
"pypdf>=5,<7",
"python-docx>=1.1,<2",
"python-multipart>=0.0.9,<1",
```

Development dependency:

```toml
"reportlab>=4,<5",
```

Write tests that construct a DOCX with a heading and table, a PDF with text, a TXT file, and a low-text PDF. Assert structure, page count and blocking diagnostics.

```python
def test_docx_extractor_preserves_heading_and_table(tmp_path: Path) -> None:
    path = write_docx_fixture(tmp_path)
    extracted = ExtractorRegistry.default().extract(SourceFile.from_path(path))
    assert any(block.kind == "heading" for block in extracted.blocks)
    assert any(block.kind == "table" and "审批人" in block.text for block in extracted.blocks)
```

- [ ] **Step 2: Run extractor tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_document_extractors.py tests/test_document_cleaning.py -q`

Expected: imports or assertions fail.

- [ ] **Step 3: Implement format adapters and safety checks**

Implement exact extension/MIME/signature agreement, the 15 MiB limit, PDF 200-page limit, DOCX ZIP entry count and expanded-size limits, and no external-resource execution.

```python
class ExtractorRegistry:
    def extract(self, source: SourceFile) -> ExtractedDocument:
        extractor = next(
            (item for item in self._extractors if item.supports(source)),
            None,
        )
        if extractor is None:
            raise UnsupportedSourceError("unsupported enterprise document format")
        return extractor.extract(source)
```

- [ ] **Step 4: Implement deterministic cleaning**

Clean Unicode/newlines/control characters, repeated short page headers/footers, pure page numbers, consecutive exact duplicates and whitespace. Preserve headings, lists and tables. Return counts and issues instead of silently dropping uncertain content.

- [ ] **Step 5: Run focused tests and Ruff**

Run: `.venv\Scripts\python.exe -m pytest tests/test_document_extractors.py tests/test_document_cleaning.py -q`

Run: `.venv\Scripts\python.exe -m ruff check src tests`

Expected: all pass.

- [ ] **Step 6: Commit extraction and cleaning**

```powershell
git add pyproject.toml src/enterprise_knowledge_rag/documents/extractors.py src/enterprise_knowledge_rag/documents/cleaning.py tests/test_document_extractors.py tests/test_document_cleaning.py
git commit -m "feat: parse and clean enterprise documents"
```

---

### Task 3: Persist Import Jobs and Parent Document Vectors

**Files:**
- Create: `db/migrations/004_ingestion_and_document_routing.sql`
- Create: `src/enterprise_knowledge_rag/documents/import_repository.py`
- Modify: `src/enterprise_knowledge_rag/documents/repository.py`
- Modify: `src/enterprise_knowledge_rag/config.py`
- Create: `tests/test_import_repository.py`
- Modify: `tests/test_postgres_retrieval_store.py`
- Modify: `tests/integration/test_pgvector_repository.py`

**Interfaces:**
- Produces `ImportRepository.create/get/list/update_status`.
- Produces `KnowledgeRepository.upsert_document(..., document_embedding=...)`.
- Produces `KnowledgeRepository.search_documents(query_vector, document_keys, limit)`.

- [ ] **Step 1: Write failing repository contract tests**

```python
def test_import_repository_maps_safe_preview_without_storage_path() -> None:
    preview = repository.get_import(IMPORT_ID)
    assert preview.import_id == IMPORT_ID
    assert "storage" not in preview.model_dump_json()


def test_parent_vector_search_respects_authorized_document_keys() -> None:
    results = repository.search_documents(
        [0.0] * 1024,
        document_keys=frozenset({("hr-leave-policy", "2.0")}),
        limit=4,
    )
    assert {(item.document_id, item.version) for item in results} == {
        ("hr-leave-policy", "2.0")
    }
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_import_repository.py tests/test_postgres_retrieval_store.py -q`

- [ ] **Step 3: Add migration**

Create `knowledge_imports` with UUID primary key, hash uniqueness, safe status fields, JSONB cleaning report and audit timestamps. Add `document_search_text`, `document_embedding_model` and `document_embedding vector(1024)` to `knowledge_documents`, plus an HNSW index for parent vectors.

- [ ] **Step 4: Implement repositories and configuration**

Add settings:

```python
upload_storage_dir: Path = Path("data/uploads")
upload_max_bytes: int = 15 * 1024 * 1024
pdf_max_pages: int = 200
document_route_limit: int = 4
```

Use SQL parameters for all metadata and document-key filters. Never expose `storage_path` in API DTOs.

- [ ] **Step 5: Run repository and migration tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_import_repository.py tests/test_postgres_retrieval_store.py tests/test_incremental_indexing.py -q`

Run with PostgreSQL when available: `$env:RUN_PGVECTOR_TESTS='1'; .venv\Scripts\python.exe -m pytest tests/integration/test_pgvector_repository.py -q`

- [ ] **Step 6: Commit persistence**

```powershell
git add db/migrations/004_ingestion_and_document_routing.sql src/enterprise_knowledge_rag/documents/import_repository.py src/enterprise_knowledge_rag/documents/repository.py src/enterprise_knowledge_rag/config.py tests/test_import_repository.py tests/test_postgres_retrieval_store.py tests/integration/test_pgvector_repository.py
git commit -m "feat: persist document imports and parent vectors"
```

---

### Task 4: Build the Administrator Ingestion State Machine and API

**Files:**
- Create: `src/enterprise_knowledge_rag/documents/ingestion.py`
- Modify: `src/enterprise_knowledge_rag/runtime.py`
- Modify: `src/enterprise_knowledge_rag/app.py`
- Modify: `src/enterprise_knowledge_rag/bootstrap.py`
- Create: `tests/test_ingestion_service.py`
- Modify: `tests/test_app.py`
- Modify: `tests/test_runtime_service.py`

**Interfaces:**
- Produces `IngestionService.preview(source, metadata, actor) -> ImportPreview`.
- Produces `IngestionService.approve(import_id, metadata, actor) -> ImportPreview`.
- Adds `POST/GET /knowledge/imports` and `POST /knowledge/imports/{id}/approve`.

- [ ] **Step 1: Write failing state and authorization tests**

```python
def test_employee_cannot_upload_enterprise_document(client) -> None:
    response = client.post(
        "/knowledge/imports",
        files={"file": ("policy.txt", b"policy body", "text/plain")},
        data=valid_metadata_form(),
    )
    assert response.status_code == 403


def test_scanned_pdf_is_quarantined_and_never_indexed(service) -> None:
    preview = service.preview(scanned_pdf(), metadata(), KNOWLEDGE_ADMIN)
    assert preview.status is IngestionStatus.QUARANTINED
    with pytest.raises(ImportNotApprovableError):
        service.approve(preview.import_id, metadata(), KNOWLEDGE_ADMIN)
    assert service.indexer.calls == []
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ingestion_service.py tests/test_app.py tests/test_runtime_service.py -q`

- [ ] **Step 3: Implement state transitions and idempotency**

Store source bytes under a random import ID, parse and clean once, persist a preview, and allow only `needs_review -> approved -> indexed`. A repeated upload with the same SHA-256 returns the existing safe preview; repeated approval must not duplicate chunks or vectors.

- [ ] **Step 4: Implement typed multipart API**

Keep the chat JSON request limit. Apply the 15 MiB upload limit only to `/knowledge/imports`, validate metadata through Pydantic, and return stable Chinese errors. Inject `knowledge_admin` through the existing server-trusted session resolver.

- [ ] **Step 5: Run focused API tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ingestion_service.py tests/test_app.py tests/test_runtime_service.py -q`

- [ ] **Step 6: Commit ingestion API**

```powershell
git add src/enterprise_knowledge_rag/documents/ingestion.py src/enterprise_knowledge_rag/runtime.py src/enterprise_knowledge_rag/app.py src/enterprise_knowledge_rag/bootstrap.py tests/test_ingestion_service.py tests/test_app.py tests/test_runtime_service.py
git commit -m "feat: add reviewed enterprise document ingestion"
```

---

### Task 5: Add the Knowledge Administrator Import Experience

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/components/KnowledgeView.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/api.test.ts`
- Modify: `frontend/e2e/responsive.spec.ts`

**Interfaces:**
- Consumes `SessionInfo.role` and import DTOs.
- Produces typed `uploadKnowledgeDocument`, `fetchKnowledgeImports` and `approveKnowledgeImport` functions.

- [ ] **Step 1: Write failing UI and API tests**

```tsx
it("shows import controls only to knowledge administrators", async () => {
  render(<App />);
  expect(await screen.findByRole("button", { name: "导入企业文档" })).toBeVisible();
});

it("shows cleaning warnings before approval", async () => {
  render(<KnowledgeView {...adminPropsWithWarning} />);
  expect(screen.getByText("发现重复页眉")).toBeVisible();
  expect(screen.getByRole("button", { name: "确认并建立索引" })).toBeVisible();
});
```

- [ ] **Step 2: Run Vitest and verify RED**

Run: `npm --prefix frontend run test -- --run`

- [ ] **Step 3: Implement typed upload, metadata and preview states**

Use one unframed management section with a file picker, metadata fields, extraction summary, normalized preview, warning list and approval command. Provide loading, empty, failed, quarantined, review and indexed states. Do not display filesystem paths or raw backend exceptions.

- [ ] **Step 4: Add responsive behavior**

Desktop uses a document table plus right-side review panel; mobile stacks the form and opens preview in a full-height sheet. Keep controls within 360 px width and preserve stable button dimensions.

- [ ] **Step 5: Run frontend tests, type check and build**

Run: `npm --prefix frontend run test -- --run`

Run: `npm --prefix frontend run lint`

Run: `npm --prefix frontend run build`

- [ ] **Step 6: Commit the administrator UI**

```powershell
git add frontend/src frontend/e2e/responsive.spec.ts
git commit -m "feat: add reviewed knowledge import workspace"
```

---

### Task 6: Index and Route Parent Documents

**Files:**
- Create: `src/enterprise_knowledge_rag/retrieval/routing.py`
- Modify: `src/enterprise_knowledge_rag/documents/indexing.py`
- Modify: `src/enterprise_knowledge_rag/documents/repository.py`
- Modify: `src/enterprise_knowledge_rag/retrieval/__init__.py`
- Create: `tests/test_document_routing.py`
- Modify: `tests/test_incremental_indexing.py`
- Modify: `tests/test_delivery.py`

**Interfaces:**
- Produces `DocumentRouter.route(query, document_keys, limit=4) -> tuple[DocumentRouteCandidate, ...]`.
- Defines `DocumentRouteCandidate` in `retrieval/routing.py` with `document_id`, `version`, `title`, lexical/vector ranks and fused score.
- Indexing persists deterministic `document_search_text` and its vector together with child chunks.

- [ ] **Step 1: Write failing parent-route tests**

```python
def test_router_never_returns_document_outside_authorized_keys() -> None:
    routes = router.route(
        "紧急病假材料",
        document_keys=frozenset({("hr-leave-policy", "2.0")}),
        limit=4,
    )
    assert {(route.document_id, route.version) for route in routes} == {
        ("hr-leave-policy", "2.0")
    }
```

- [ ] **Step 2: Run route and indexing tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_document_routing.py tests/test_incremental_indexing.py tests/test_delivery.py -q`

- [ ] **Step 3: Implement deterministic parent search text and embedding**

Build search text from title, type, department, top-level headings and approved tags. Embed it with the same configured model, store the model identifier, and make `/ready` require a current parent vector and child vectors for every indexed active document.

- [ ] **Step 4: Implement filtered BM25/vector parent routing with RRF**

Parent routing only receives document keys resolved by access and version policy. Preserve lexical/vector ranks and expose no restricted metadata.

- [ ] **Step 5: Run focused and readiness tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_document_routing.py tests/test_incremental_indexing.py tests/test_delivery.py -q`

- [ ] **Step 6: Commit parent routing**

```powershell
git add src/enterprise_knowledge_rag/retrieval/routing.py src/enterprise_knowledge_rag/retrieval/__init__.py src/enterprise_knowledge_rag/documents/indexing.py src/enterprise_knowledge_rag/documents/repository.py tests/test_document_routing.py tests/test_incremental_indexing.py tests/test_delivery.py
git commit -m "feat: add authorized parent document routing"
```

---

### Task 7: Generate a Validated Retrieval Plan with Deterministic Fallback

**Files:**
- Create: `src/enterprise_knowledge_rag/retrieval/planning.py`
- Modify: `src/enterprise_knowledge_rag/providers.py`
- Modify: `src/enterprise_knowledge_rag/bootstrap.py`
- Create: `tests/test_retrieval_planning.py`
- Modify: `tests/test_model_providers.py`
- Modify: `tests/test_bootstrap.py`

**Interfaces:**
- Produces `RetrievalPlanner.plan(question, history) -> PlannedRetrieval`.
- Defines `PlannedRetrieval` in `retrieval/planning.py`; it carries `plan`, `status` (`planned` or `degraded`) and `model_call_count`.

- [ ] **Step 1: Write failing plan and fallback tests**

```python
def test_planner_decomposes_material_and_exception_needs() -> None:
    planned = planner.plan("病假超过两天交什么材料，紧急就医怎么办？", [])
    assert {need.kind for need in planned.plan.evidence_needs} == {
        EvidenceKind.MATERIAL,
        EvidenceKind.EXCEPTION,
    }
    assert planned.plan.max_hops == 2


def test_planner_failure_falls_back_to_one_rule_need() -> None:
    planned = failing_planner.plan("出差怎么报销？", [])
    assert planned.status == "degraded"
    assert planned.plan.max_hops == 1
    assert planned.plan.evidence_needs[0].query == "出差怎么报销？"
```

- [ ] **Step 2: Run planner tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retrieval_planning.py tests/test_model_providers.py tests/test_bootstrap.py -q`

- [ ] **Step 3: Implement the structured planner**

Use `OpenAICompatibleStructuredProvider` with `RetrievalPlan`, a Chinese prompt that defines evidence kinds, and no access/time/version fields in the schema. Normalize duplicate need IDs and cap needs/hops through Pydantic. On provider or validation failure, return the deterministic single-need plan.

- [ ] **Step 4: Run focused tests and Ruff**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retrieval_planning.py tests/test_model_providers.py tests/test_bootstrap.py -q`

Run: `.venv\Scripts\python.exe -m ruff check src tests scripts`

- [ ] **Step 5: Commit retrieval planning**

```powershell
git add src/enterprise_knowledge_rag/retrieval/planning.py src/enterprise_knowledge_rag/providers.py src/enterprise_knowledge_rag/bootstrap.py tests/test_retrieval_planning.py tests/test_model_providers.py tests/test_bootstrap.py
git commit -m "feat: plan explicit enterprise evidence needs"
```

---

### Task 8: Implement Hierarchical Retrieval and Bounded Evidence Completion

**Files:**
- Create: `src/enterprise_knowledge_rag/retrieval/coverage.py`
- Create: `src/enterprise_knowledge_rag/retrieval/hierarchical.py`
- Modify: `src/enterprise_knowledge_rag/retrieval/service.py`
- Modify: `src/enterprise_knowledge_rag/retrieval/__init__.py`
- Modify: `src/enterprise_knowledge_rag/evidence.py`
- Create: `tests/test_evidence_coverage.py`
- Create: `tests/test_hierarchical_retrieval.py`
- Modify: `tests/test_retrieval_service.py`
- Modify: `tests/test_evidence_builder.py`

**Interfaces:**
- Produces `EvidenceCoverageService.cover(plan, candidates) -> CoverageResult`.
- Produces `HierarchicalRetrievalService.retrieve(plan, user, as_of, strategy) -> HierarchicalRetrievalResult`.
- Defines `CoverageResult` in `retrieval/coverage.py` with covered and missing required need IDs plus annotated candidates.
- Defines `HierarchicalRetrievalResult` in `retrieval/hierarchical.py` with status, routes, evidence candidates, coverage and hop count.
- Section retrieval accepts an explicit routed `document_keys` set and cannot expand it.

- [ ] **Step 1: Confirm public test seams**

Test only `EvidenceCoverageService.cover()` and `HierarchicalRetrievalService.retrieve()` for this task. Do not assert internal method calls except security-critical forwarded document keys.

- [ ] **Step 2: Write failing one-hop, two-hop and security tests**

```python
def test_missing_exception_need_triggers_one_supplemental_hop() -> None:
    result = service.retrieve(MATERIAL_AND_EXCEPTION_PLAN, USER, AS_OF)
    assert result.hop_count == 2
    assert result.coverage.missing_required_need_ids == frozenset()
    assert {item.retrieval_hop for item in result.evidence_candidates} == {1, 2}


def test_second_hop_cannot_query_restricted_document() -> None:
    result = service.retrieve(RESTRICTED_SUPPLEMENT_PLAN, EMPLOYEE, AS_OF)
    assert RESTRICTED_KEY not in backend.received_document_keys
    assert result.status is RetrievalStatus.PERMISSION_DENIED
```

- [ ] **Step 3: Run hierarchical tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_evidence_coverage.py tests/test_hierarchical_retrieval.py tests/test_retrieval_service.py tests/test_evidence_builder.py -q`

- [ ] **Step 4: Implement coverage and supplemental query construction**

Match needs against section path, candidate content and reranker threshold. Supplemental queries contain the original topic, missing need kind/query and only already authorized route titles. Do not call the LLM to invent a second-hop query.

- [ ] **Step 5: Implement hierarchical retrieval and evidence allocation**

Resolve authorization and versions once per hop using the same policy service, route at most four parent documents, retrieve/rerank child sections per need, merge by stable chunk ID/content hash, reject conflicting versions, then allocate one supporting chunk per required need before remaining budget.

- [ ] **Step 6: Run focused tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_evidence_coverage.py tests/test_hierarchical_retrieval.py tests/test_retrieval_service.py tests/test_evidence_builder.py -q`

- [ ] **Step 7: Commit hierarchical retrieval**

```powershell
git add src/enterprise_knowledge_rag/retrieval/coverage.py src/enterprise_knowledge_rag/retrieval/hierarchical.py src/enterprise_knowledge_rag/retrieval/service.py src/enterprise_knowledge_rag/retrieval/__init__.py src/enterprise_knowledge_rag/evidence.py tests/test_evidence_coverage.py tests/test_hierarchical_retrieval.py tests/test_retrieval_service.py tests/test_evidence_builder.py
git commit -m "feat: retrieve hierarchical two-hop evidence"
```

---

### Task 9: Orchestrate Planning, Retrieval, Coverage and Citation Completeness

**Files:**
- Modify: `src/enterprise_knowledge_rag/workflow.py`
- Modify: `src/enterprise_knowledge_rag/citations.py`
- Modify: `src/enterprise_knowledge_rag/tracing.py`
- Modify: `src/enterprise_knowledge_rag/app.py`
- Modify: `src/enterprise_knowledge_rag/generation.py`
- Modify: `tests/test_workflow.py`
- Modify: `tests/test_citations.py`
- Modify: `tests/test_sse.py`
- Modify: `tests/test_tracing.py`

**Interfaces:**
- `run_chat()` remains the end-to-end public seam.
- `validate_citations(draft, evidence, required_need_ids=...)` enforces need coverage.
- `WorkflowRun` exposes safe plan, routes, hop count and model-call count for evaluation.

- [ ] **Step 1: Write failing end-to-end tests**

```python
def test_multihop_workflow_returns_complete_multi_document_citations() -> None:
    run = run_chat(multihop_graph, REQUEST, USER, as_of=AS_OF)
    assert run.result.status == "success"
    assert run.retrieval_hops == 2
    assert {item.document_id for item in run.result.evidence} == {
        "hr-leave-policy",
        "hr-medical-certificate-process",
    }


def test_incomplete_required_need_refuses_before_generation() -> None:
    run = run_chat(incomplete_graph, REQUEST, USER, as_of=AS_OF)
    assert run.result.refusal_reason is RefusalReason.INSUFFICIENT_EVIDENCE
    assert "generate" not in {event.component for event in run.trace}
```

- [ ] **Step 2: Run workflow/citation/SSE tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_workflow.py tests/test_citations.py tests/test_sse.py tests/test_tracing.py -q`

- [ ] **Step 3: Add LangGraph nodes and safe public labels**

Use nodes `retrieval_plan`, `document_route`, `section_retrieve`, `evidence_coverage`, conditional `supplemental_retrieve`, `evidence`, `generate`, and `finalize`. Emit only plan status, counts, hop and safe IDs in Trace; do not emit chain-of-thought or denied metadata.

- [ ] **Step 4: Enforce citation completeness**

Collect need IDs supported by each claim's evidence. If required needs are absent, retry generation once. If evidence was complete but generation remains invalid, return grouped evidence summary; if evidence was incomplete, refuse before generation.

- [ ] **Step 5: Run focused tests and the Python suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_workflow.py tests/test_citations.py tests/test_sse.py tests/test_tracing.py -q`

Run: `.venv\Scripts\python.exe -m pytest -q`

- [ ] **Step 6: Commit workflow orchestration**

```powershell
git add src/enterprise_knowledge_rag/workflow.py src/enterprise_knowledge_rag/citations.py src/enterprise_knowledge_rag/tracing.py src/enterprise_knowledge_rag/app.py src/enterprise_knowledge_rag/generation.py tests/test_workflow.py tests/test_citations.py tests/test_sse.py tests/test_tracing.py
git commit -m "feat: orchestrate auditable multi-hop evidence"
```

---

### Task 10: Extend Development Evaluation for Routing and Multi-Hop Behavior

**Files:**
- Add: `knowledge/hr/medical-certificate-process.md`
- Add: `knowledge/procurement/supplier-onboarding-process.md`
- Modify: `knowledge/manifest.yaml`
- Modify: `evaluation/development.json`
- Modify: `src/enterprise_knowledge_rag/evaluation/models.py`
- Modify: `src/enterprise_knowledge_rag/evaluation/graders.py`
- Modify: `src/enterprise_knowledge_rag/evaluation/executor.py`
- Modify: `src/enterprise_knowledge_rag/evaluation/runner.py`
- Modify: `tests/test_evaluation_dataset_contract.py`
- Modify: `tests/test_evaluation_graders.py`
- Modify: `tests/test_evaluation_executor.py`
- Modify: `tests/test_evaluation_runner.py`

**Interfaces:**
- Adds observation fields `routed_document_keys`, `retrieval_hops`, `required_need_ids` and `covered_need_ids`.
- Adds metrics `document_route_recall`, `evidence_need_coverage`, `second_hop_trigger_accuracy`, `second_hop_success` and `irrelevant_evidence_ratio`.

- [ ] **Step 1: Write synthetic cross-document documents and gold cases**

Add explicit front matter marking both documents synthetic. Add development cases for:

1. leave material plus emergency submission process, requiring two documents;
2. procurement threshold plus supplier onboarding process, requiring two documents;
3. a single-hop deadline that must not trigger hop two;
4. a missing exception that must refuse after hop two;
5. a supplemental query that must not leak a restricted document.

Do not change `evaluation/frozen_holdout.json`.

- [ ] **Step 2: Write failing evaluator tests**

```python
def test_two_hop_case_requires_all_gold_evidence_and_expected_hop() -> None:
    metrics = grade_case(TWO_HOP_CASE, COMPLETE_OBSERVATION, k=5)
    assert metrics.evidence_need_coverage == 1.0
    assert metrics.second_hop_success == 1.0
    assert metrics.core_pass is True
```

- [ ] **Step 3: Run dataset and grader tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_evaluation_dataset_contract.py tests/test_evaluation_graders.py tests/test_evaluation_executor.py tests/test_evaluation_runner.py -q`

- [ ] **Step 4: Extend observations, grading and report aggregation**

Keep failures in the denominator. Preserve existing metrics and report metadata. New optional fields must allow old single-hop reports to validate.

- [ ] **Step 5: Run all evaluation tests without executing datasets**

Run: `.venv\Scripts\python.exe -m pytest tests/test_evaluation_dataset_contract.py tests/test_evaluation_graders.py tests/test_evaluation_executor.py tests/test_evaluation_runner.py -q`

Expected: tests validate both datasets structurally but do not submit frozen cases to the Agent.

- [ ] **Step 6: Commit corpus and evaluation contracts**

```powershell
git add knowledge evaluation/development.json src/enterprise_knowledge_rag/evaluation tests/test_evaluation_dataset_contract.py tests/test_evaluation_graders.py tests/test_evaluation_executor.py tests/test_evaluation_runner.py
git commit -m "test: evaluate hierarchical multi-hop RAG behavior"
```

---

### Task 11: Delivery, Documentation and Full Verification

**Files:**
- Modify: `.env.example`
- Modify: `.gitignore`
- Modify: `compose.yaml`
- Modify: `Dockerfile`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `docs/OPERATIONS.md`
- Modify: `docs/EVALUATION_PROTOCOL.md`
- Modify: `docs/PROJECT_HANDOFF.md`
- Modify: `docs/INTERVIEW_GUIDE.md`
- Add: `docs/learning/W8-1-document-ingestion.md`
- Add: `docs/learning/W8-2-hierarchical-multihop-rag.md`

**Interfaces:**
- Delivery starts from an empty volume and verifies migrations, existing Markdown indexing, parent vectors, `/ready` and one deterministic hierarchical retrieval smoke.
- Documentation states measured results only.

- [ ] **Step 1: Update delivery configuration**

Add an ignored `data/uploads/` path and a named Compose upload volume. Configure upload limits, routing limits, evidence limits and deterministic CI embeddings. Ensure the container user can write the upload directory without running as root.

- [ ] **Step 2: Extend CI delivery smoke**

CI must:

1. apply migration `004` on an empty database;
2. index the committed synthetic Markdown corpus;
3. verify every active document has a current parent vector and child vectors;
4. run one deterministic parent-route/section-retrieval smoke;
5. run Python 3.11/3.12, Ruff, frontend test/type/build/audit and responsive checks;
6. remove CI volumes in `if: always()` cleanup.

- [ ] **Step 3: Update documentation and learning logs**

Document the safe upload flow, supported formats, quarantine behavior, hierarchy, two-hop trigger, metrics and honest boundaries. Update the interview guide to answer “召回的是什么”“为什么需要第二跳”“如何证明不是越权检索”。 Do not write unmeasured accuracy.

- [ ] **Step 4: Run fresh Python verification**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: all deterministic tests pass; the real pgvector test may skip unless explicitly enabled.

Run: `.venv\Scripts\python.exe -m ruff check src tests scripts`

Expected: `All checks passed!`

- [ ] **Step 5: Run fresh frontend verification**

Run: `npm --prefix frontend run test -- --run`

Run: `npm --prefix frontend run lint`

Run: `npm --prefix frontend run build`

Run: `npm --prefix frontend audit --audit-level=high`

- [ ] **Step 6: Run browser verification**

Run: `npm --prefix frontend run test:e2e`

Verify 360, 390 and 1440 px widths, no horizontal overflow, import form text fitting, and visible loading/empty/quarantined/review/indexed states.

- [ ] **Step 7: Run database delivery smoke when Docker is available**

Run: `docker compose up -d --build --wait --wait-timeout 600`

Run: `docker compose exec -T api python scripts/retrieval_smoke.py`

Run: `curl --fail http://127.0.0.1:8010/ready`

Do not use `docker compose down --volumes` against a data-bearing local environment. CI may remove its own isolated volumes.

- [ ] **Step 8: Review claims against generated artifacts**

Confirm README and interview text contain no production-user count, real-enterprise claim, frozen result, accuracy or improvement percentage without a matching report under `evaluation/reports/`.

- [ ] **Step 9: Commit delivery and documentation**

```powershell
git add .env.example .gitignore compose.yaml Dockerfile .github/workflows/ci.yml README.md docs
git commit -m "docs: deliver deep enterprise RAG upgrade"
```

---

## Final Acceptance Sequence

After all eleven tasks and fresh verification pass:

1. Push the branch and require GitHub Actions to pass.
2. Start a real PostgreSQL/pgvector environment and index with the configured real Embedding model.
3. Run a small development smoke, inspect routes, hops, evidence and citations.
4. Run the full development comparison with fixed code, corpus, models, prompts and repetition count.
5. Review failure categories before changing any strategy.
6. Freeze code, prompts, models and corpus.
7. Run frozen holdout exactly once through a separate explicit final-acceptance entry point.
8. Only then add measured numbers to README and resume material.
