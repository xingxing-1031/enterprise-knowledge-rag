# 企业知识库管理员控制台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目二收口为单管理员 RAG 管理控制面，提供文档生命周期、检索实验室、评测与审计，同时保持项目一内部证据接口兼容。

**Architecture:** FastAPI 继续提供公开健康检查和受令牌保护的内部证据接口，所有浏览器管理接口统一经过 `knowledge_admin` 会话。新增管理员控制服务承载统计、生命周期和安全检索调试，React 前端重组为总览、文档库、导入审核、检索实验室和评测中心。

**Tech Stack:** Python 3.12、FastAPI、PostgreSQL/pgvector、Pydantic、React 18、TypeScript、Vite、Vitest、Playwright、Lucide React。

## Global Constraints

- 只保留 `knowledge-admin-demo` 一个网页登录身份。
- `/internal/evidence` 继续使用 `X-Internal-Token`，请求和响应契约保持兼容。
- 永久删除由服务端校验确认标题，并级联删除文档、切片、向量和受管文件。
- 删除审计不得保存正文、切片、向量、原始文件路径或可恢复敏感元数据。
- UI 是高密度内部工具，不做普通聊天、营销 Hero、装饰性渐变或卡片嵌套。
- 桌面 1280x720 和手机 390x844 不得出现页面级横向滚动。
- 不引入新的前端组件库。

---

### Task 1: 单管理员认证与 API 边界

**Files:**
- Modify: `src/enterprise_knowledge_rag/config.py`
- Modify: `src/enterprise_knowledge_rag/app.py`
- Modify: `tests/test_auth.py`
- Modify: `tests/test_app.py`
- Modify: `.env.example`
- Modify: `.env.vps.example`

**Interfaces:**
- Consumes: `Settings.auth_knowledge_admin_*` 和签名 Cookie。
- Produces: `require_admin()` 保护的管理接口；内部令牌认证保持不变。

- [ ] **Step 1: 写失败测试**

```python
def test_login_accepts_only_knowledge_administrator() -> None:
    assert login("knowledge-admin-demo", "KnowledgeAdmin2026!").status_code == 200
    assert login("employee-demo", "EmployeeDemo2026!").status_code == 401


def test_management_metadata_requires_admin() -> None:
    assert unauthenticated.get("/documents").status_code == 401
    assert employee_client.get("/documents").status_code == 403
    assert employee_client.get("/evaluations/latest").status_code == 403
```

- [ ] **Step 2: 运行 `.venv\Scripts\python.exe -m pytest tests/test_auth.py tests/test_app.py -q`，确认员工仍可登录或接口权限测试失败。**

- [ ] **Step 3: 将 `_demo_accounts()` 收口为单一管理员账号。**

```python
def _demo_accounts(settings: Settings):
    return ((
        settings.auth_knowledge_admin_username,
        settings.auth_knowledge_admin_user_id,
        UserRole.KNOWLEDGE_ADMIN,
        settings.auth_knowledge_admin_departments,
        settings.auth_knowledge_admin_password_hash,
    ),)
```

- [ ] **Step 4: 为 `/documents`、`/evaluations/latest` 和所有导入、索引接口应用 `Depends(require_admin)`；删除浏览器 `/chat`、`/chat/stream`、`/chat/clear` 路由。**

- [ ] **Step 5: 删除员工和部门管理员密码设置与示例环境变量，但保留 `UserRole`，因为内部证据检索仍需模拟调用方权限。**

- [ ] **Step 6: 重新运行定点测试，确认管理接口 401/403/200 和 `/internal/evidence` 令牌测试通过。**

- [ ] **Step 7: 提交 `feat: restrict rag console to knowledge admins`。**

### Task 2: 文档生命周期与安全审计持久化

**Files:**
- Create: `db/migrations/005_admin_control_plane.sql`
- Create: `src/enterprise_knowledge_rag/admin_models.py`
- Modify: `src/enterprise_knowledge_rag/models.py`
- Modify: `src/enterprise_knowledge_rag/documents/repository.py`
- Create: `src/enterprise_knowledge_rag/admin_audit.py`
- Create: `tests/test_admin_control_repository.py`
- Create: `tests/test_admin_audit.py`

**Interfaces:**
- Produces: `AdminOverview`, `ManagedDocument`, `DeleteDocumentRequest`, `AdminAuditEvent`。
- Produces: `KnowledgeRepository.get_document_version()`、`set_document_status()`、`delete_document_version()`、`admin_overview()`。
- Produces: `AdminAuditRepository.record()`、`list_recent()`。

- [ ] **Step 1: 写停用后不召回、删除级联和审计脱敏失败测试。**

```python
def test_inactive_document_is_not_retrievable() -> None:
    repository.set_document_status("hr-policy", "2.0", DocumentStatus.INACTIVE)
    assert ("hr-policy", "2.0") not in authorized_keys(repository)


def test_delete_cascades_chunks_and_keeps_safe_tombstone() -> None:
    deleted = repository.delete_document_version("hr-policy", "2.0")
    assert deleted.chunk_count > 0
    assert repository.get_document_version("hr-policy", "2.0") is None
    assert audit.latest().document_ref_hash
    assert "hr-policy" not in audit.latest().model_dump_json()
```

- [ ] **Step 2: 运行新增测试并确认缺少模型和仓储方法。**

- [ ] **Step 3: 新增审计迁移。**

```sql
CREATE TABLE IF NOT EXISTS knowledge_admin_audit (
    event_id UUID PRIMARY KEY,
    action TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    document_ref_hash CHAR(64),
    version TEXT,
    result TEXT NOT NULL,
    reason_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_knowledge_admin_audit_created
    ON knowledge_admin_audit (created_at DESC);
```

- [ ] **Step 4: 在 `DocumentStatus` 增加 `INACTIVE = "inactive"`，并实现事务性查询、状态切换和删除；删除依赖外键级联清理 `knowledge_chunks`。**

- [ ] **Step 5: 使用 HMAC-SHA256 生成不可逆文档引用。**

```python
def document_reference_hash(document_id: str, secret: str) -> str:
    return hmac.new(secret.encode(), document_id.encode(), hashlib.sha256).hexdigest()
```

- [ ] **Step 6: 运行新增测试及 `tests/test_retrieval_service.py`，确认停用、删除和审计通过。**

- [ ] **Step 7: 提交 `feat: add governed document lifecycle`。**

### Task 3: 管理员控制服务与文档动作 API

**Files:**
- Create: `src/enterprise_knowledge_rag/admin_service.py`
- Modify: `src/enterprise_knowledge_rag/runtime.py`
- Modify: `src/enterprise_knowledge_rag/bootstrap.py`
- Modify: `src/enterprise_knowledge_rag/app.py`
- Create: `tests/test_admin_service.py`
- Modify: `tests/test_runtime_service.py`
- Modify: `tests/test_app.py`

**Interfaces:**
- Produces: `KnowledgeAdminService.overview()`、`documents()`、`deactivate()`、`restore()`、`reindex()`、`delete()`。
- Produces: `/admin/overview` 和文档停用、恢复、重建索引、永久删除路由。

- [ ] **Step 1: 写确认标题、文件边界、停用恢复和重复请求失败测试。**

```python
def test_delete_requires_exact_title(tmp_path: Path) -> None:
    with pytest.raises(DocumentConfirmationError):
        service.delete("hr-policy", "2.0", confirmation="wrong", actor=admin)
    result = service.delete("hr-policy", "2.0", confirmation="员工请假制度", actor=admin)
    assert result.deleted is True
```

- [ ] **Step 2: 运行 `.venv\Scripts\python.exe -m pytest tests/test_admin_service.py tests/test_runtime_service.py tests/test_app.py -q` 并确认失败。**

- [ ] **Step 3: 实现独立控制服务。**

```python
class KnowledgeAdminService:
    def overview(self, actor: UserContext) -> AdminOverview: ...
    def documents(self, actor: UserContext) -> tuple[ManagedDocument, ...]: ...
    def deactivate(self, document_id: str, version: str, actor: UserContext) -> ManagedDocument: ...
    def restore(self, document_id: str, version: str, actor: UserContext) -> ManagedDocument: ...
    def reindex(self, document_id: str, version: str, actor: UserContext) -> ManagedDocument: ...
    def delete(self, document_id: str, version: str, confirmation: str, actor: UserContext) -> DeleteResult: ...
```

- [ ] **Step 4: 删除文件前解析绝对路径并验证它位于 `knowledge_dir` 或 `upload_storage_dir`；越界路径拒绝删除。**

- [ ] **Step 5: 在 `build_runtime_service()` 复用同一个 Repository 和 IndexingService 注入控制服务，由 RuntimeChatService 委托。**

- [ ] **Step 6: 添加 `/admin/overview`、`deactivate`、`restore`、`reindex` 和 `DELETE` 路由，稳定映射 404、409、422、503。**

- [ ] **Step 7: 运行服务、接口和索引回归测试。**

- [ ] **Step 8: 提交 `feat: add knowledge administrator controls`。**

### Task 4: 安全检索实验室

**Files:**
- Modify: `src/enterprise_knowledge_rag/admin_models.py`
- Modify: `src/enterprise_knowledge_rag/retrieval/service.py`
- Modify: `src/enterprise_knowledge_rag/admin_service.py`
- Modify: `src/enterprise_knowledge_rag/app.py`
- Create: `tests/test_retrieval_debug.py`
- Modify: `tests/test_app.py`

**Interfaces:**
- Produces: `RetrievalDebugRequest`、`SafeDebugCandidate`、`RetrievalDebugStage`、`RetrievalDebugResponse`。
- Produces: `RetrievalService.debug_retrieve()` 和 `POST /admin/retrieval/debug`。

- [ ] **Step 1: 写阶段顺序、分数和未授权正文不泄露测试。**

```python
def test_debug_trace_is_explainable_without_leaking_hidden_text() -> None:
    result = service.debug_retrieve("付款审批", user=employee, top_k=5)
    assert [stage.name for stage in result.stages] == [
        "authorization", "bm25", "vector", "rrf", "rerank", "evidence"
    ]
    assert result.stages[0].excluded_count == 1
    assert "秘密付款" not in result.model_dump_json()
```

- [ ] **Step 2: 运行新增测试并确认 `debug_retrieve` 不存在。**

- [ ] **Step 3: 复用现有检索组件收集每阶段候选数、授权候选的渠道排名、融合分数、重排分数和耗时；授权阶段只暴露数量与稳定原因代码。**

```python
class RetrievalDebugStage(StrictModel):
    name: Literal["authorization", "bm25", "vector", "rrf", "rerank", "evidence"]
    candidate_count: int = Field(ge=0)
    excluded_count: int = Field(default=0, ge=0)
    duration_ms: int = Field(ge=0)
    candidates: tuple[SafeDebugCandidate, ...] = ()
```

- [ ] **Step 4: 管理员可模拟员工或管理员的角色与部门，但模拟上下文只进入本次检索，不创建登录身份。**

- [ ] **Step 5: 添加 `/admin/retrieval/debug` 和 `/admin/audit`，全部要求管理员会话。**

- [ ] **Step 6: 运行检索、API 和内部证据回归测试。**

- [ ] **Step 7: 提交 `feat: expose safe retrieval diagnostics`。**

### Task 5: 管理控制台应用壳与视觉系统

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/LoginPage.tsx`
- Modify: `frontend/src/components/Navigation.tsx`
- Create: `frontend/src/components/OverviewView.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Produces: `AppView = "overview" | "documents" | "imports" | "retrieval" | "evaluation"`。
- Produces: 管理 API TypeScript 类型和请求函数。

- [ ] **Step 1: 使用 `ui-ux-pro-max` 查询企业管理后台设计系统、可访问导航和 React 栈建议，并读取 `references/pro-rules.md`。**

- [ ] **Step 2: 写只显示管理员导航的失败测试。**

```tsx
it("shows only administrator navigation", async () => {
  render(<App />);
  expect(await screen.findByRole("button", { name: "总览" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "检索实验室" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "智能助手" })).not.toBeInTheDocument();
});
```

- [ ] **Step 3: 删除 Chat、SSE 和证据抽屉前端状态，新增管理员总览、文档、调试和审计类型。**

- [ ] **Step 4: 登录页只提供管理员演示身份，应用默认进入总览，侧栏提供五个入口和退出。**

- [ ] **Step 5: 采用深石墨导航、冷白工作区、蓝色动作、绿色成功、琥珀待审和红色危险 Token；圆角最大 8px，图标使用 Lucide。**

```css
:root {
  --nav: #172033;
  --ground: #f5f7fa;
  --surface: #ffffff;
  --ink: #172033;
  --muted: #667085;
  --line: #d9e0e8;
  --action: #2563eb;
  --success: #16805d;
  --warning: #b36b00;
  --danger: #c83b3b;
  --radius: 8px;
}
```

- [ ] **Step 6: 运行 `npm test -- --run` 和 `npm run build`。**

- [ ] **Step 7: 提交 `feat: establish rag administrator console`。**

### Task 6: 文档库、导入审核和危险操作

**Files:**
- Create: `frontend/src/components/DocumentLibraryView.tsx`
- Modify: `frontend/src/components/KnowledgeImportWorkspace.tsx`
- Create: `frontend/src/components/ImportReviewView.tsx`
- Create: `frontend/src/components/DeleteDocumentDialog.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `ManagedDocument[]` 和文档动作 API。
- Produces: 筛选表格、详情检查器、导入审核和确认删除对话框。

- [ ] **Step 1: 写筛选、停用恢复和删除确认失败测试。**

```tsx
it("requires exact title before permanent deletion", async () => {
  await user.click(screen.getByRole("button", { name: "永久删除" }));
  expect(screen.getByRole("button", { name: "确认永久删除" })).toBeDisabled();
  await user.type(screen.getByLabelText("输入文档标题确认"), "员工请假制度");
  expect(screen.getByRole("button", { name: "确认永久删除" })).toBeEnabled();
});
```

- [ ] **Step 2: 实现搜索、部门、类型、可见范围和状态筛选；桌面为表格加详情检查器，移动端为摘要列表加详情抽屉。**

- [ ] **Step 3: 将现有上传、元数据、清洗预览和批准逻辑拆为独立导入审核一级页面。**

- [ ] **Step 4: 对话框明确删除源文件、版本、切片和向量；失败后保持打开，不乐观移除列表。**

- [ ] **Step 5: 运行前端测试和构建。**

- [ ] **Step 6: 提交 `feat: add administrator document operations`。**

### Task 7: 检索流水线与评测中心

**Files:**
- Create: `frontend/src/components/RetrievalLabView.tsx`
- Modify: `frontend/src/components/EvaluationView.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Create: `frontend/src/components/RetrievalLabView.test.tsx`

**Interfaces:**
- Consumes: `debugRetrieval()` 和 `fetchLatestEvaluation()`。
- Produces: 可解释检索流水线和评测方案对比。

- [ ] **Step 1: 写候选阶段变化失败测试。**

```tsx
it("renders retrieval stages", async () => {
  await user.type(screen.getByLabelText("测试问题"), "付款审批制度是什么？");
  await user.click(screen.getByRole("button", { name: "运行检索" }));
  expect(await screen.findByText("BM25 召回")).toBeInTheDocument();
  expect(screen.getByText("RRF 融合")).toBeInTheDocument();
  expect(screen.getByText("Rerank 重排")).toBeInTheDocument();
});
```

- [ ] **Step 2: 查询区包含问题、模拟角色、部门、时间点、策略和 Top-K；阶段轨道展示候选数、耗时和分数变化。**

- [ ] **Step 3: 评测中心展示当前报告、三种策略对比、核心指标和失败用例；无报告时保持 `not_run`。**

- [ ] **Step 4: 运行组件测试和生产构建。**

- [ ] **Step 5: 提交 `feat: visualize governed rag retrieval`。**

### Task 8: 响应式、文档与部署交付

**Files:**
- Modify: `frontend/e2e/responsive.spec.ts`
- Modify: `tests/test_delivery.py`
- Modify: `README.md`
- Modify: `docs/OPERATIONS.md`
- Modify: `docs/INTERVIEW_GUIDE_RAG.md`
- Modify: `docs/DEPLOY_VPS.md`
- Modify: `compose.vps.yaml`
- Modify: `.github/workflows/*` only if removed account variables are referenced

**Interfaces:**
- Validates: 390x844 手机和 1280x720 桌面布局。
- Documents: 单管理员、内部证据边界、文档生命周期和检索实验室演示路径。

- [ ] **Step 1: 更新 Playwright 契约，覆盖五个页面、详情抽屉、检索流水线和删除对话框。**

```ts
expect(await page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth
)).toBeLessThanOrEqual(0);
```

- [ ] **Step 2: 更新 README、运维、部署和面试指南，删除不再使用的员工与部门管理员部署变量。**

- [ ] **Step 3: 运行完整验证。**

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
npm test -- --run
npm run build
npm run test:e2e
```

- [ ] **Step 4: 运行 `git diff --check`、`git status --short` 和敏感信息扫描，确认没有令牌、模型密钥或私钥进入提交。**

- [ ] **Step 5: 提交 `docs: deliver administrator rag control plane` 并推送 `main` 触发既有部署。**

- [ ] **Step 6: 线上验证健康检查、管理员登录、五个页面、停用恢复、检索实验室和项目一内部证据调用；使用临时文档验证永久删除后列表、切片和向量均不存在。**
