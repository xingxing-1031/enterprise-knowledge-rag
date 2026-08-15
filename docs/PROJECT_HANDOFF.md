# Enterprise Knowledge RAG 项目交接

> 更新时间：2026-08-15
> 当前版本：Agentic RAG v2 与一次性冻结验收

## 1. 项目定位

这是一个面向企业运营人员的制度与流程知识库助手。项目使用脱敏、合成的企业制度语料，重点证明以下工程能力：

- 版本化知识库与生效时间解析
- 部门和角色权限过滤
- 关键词、向量、RRF 混合检索和可选重排
- 最小充分证据、引用校验、拒答和降级
- LangGraph 工作流、FastAPI、SSE 和 React 工作台
- 可审计 trace、评测日志和可重复交付
- 管理员复核后索引的 PDF/DOCX/Markdown/TXT 导入
- 结构化证据需求、父文档路由和有界两跳补充检索

项目是个人演示项目，不代表真实企业上线、团队协作、客户数量或生产 SLA。`E:\chongqing-wenlv-assistant` 和 `E:\qiuzhaoxiangmu\retail-analytics-agent` 不属于本项目，本次交接不应修改它们。

## 2. 当前目录

| 目录 | 作用 |
| --- | --- |
| `src/enterprise_knowledge_rag` | Python 后端、检索、工作流、评测实现 |
| `frontend` | React + Vite 企业知识工作台 |
| `knowledge` | 版本化合成语料和 manifest |
| `evaluation/development-v2.json` | 60 条当前开发集，可用于调试和迭代 |
| `evaluation/frozen-holdout-v2.json` | 20 条已一次性消费的冻结集，不得覆盖或据此调参 |
| `db/migrations` | 带 SHA-256 校验的增量迁移 |
| `scripts/migrate.py` | 应用迁移 |
| `scripts/index_knowledge.py` | 解析、切分、写入向量索引 |
| `scripts/retrieval_smoke.py` | pgvector 检索链路冒烟测试 |
| `scripts/run_development.py` | 三方案真实 development 评测入口 |
| `docs/OPERATIONS.md` | Docker、配置、健康检查和交付操作 |
| `docs/EVALUATION_PROTOCOL.md` | 评测口径和冻结规则 |

## 3. 已实现能力

### 运行链路

`ChatRequest -> domain -> rewrite -> retrieval_plan -> document_route -> section_retrieve -> evidence_coverage -> supplemental_retrieve? -> evidence -> generate -> finalize`

工作流会在每一跳生成候选前完成权限预过滤和版本决议；第二跳只能查询第一跳已经授权并路由的文档集合。无法覆盖必需证据需求时在生成前拒答，不让模型用常识补写制度。生成结果必须通过引用和需求完整性校验，失败时允许有限重生成，仍失败则降级或拒答。

### 三种检索方案

`EvaluationStrategy` 与 `RetrievalStrategy` 一一对应：

1. `vector_baseline`：向量召回基线
2. `hybrid_rrf`：BM25 + 向量的 RRF 融合
3. `hybrid_rrf_reranker`：RRF 后使用重排模型

三种方案共享同一套工作流、权限、版本、提示词、评分器和运行环境，评测时只替换检索策略。报告会记录代码提交、Embedding、Reranker、LLM、提示词版本、温度、重复次数和环境。

### 交付能力

- psycopg 连接池和 FastAPI 生命周期管理
- Docker Compose 启动顺序：PostgreSQL -> migrate -> index -> API
- `/health` 仅表示进程存活；`/ready` 还检查数据库、文档和当前 Embedding 索引
- GitHub Actions 覆盖 Python 3.11/3.12、Ruff、前端测试/构建、响应式检查和空卷 pgvector smoke

## 4. 当前验证状态

当前 production 容器已通过 Docker 运行 PostgreSQL/pgvector，并完成远程模型（`text-embedding-v3` / `qwen3-rerank` / `qwen-plus`）的 v2 三方案 development 评测（27 个文档版本、24 个生效文档、103 个切片，语料快照 `sha256:24af1c83…`）：

- `evaluation/reports/development-*-r1..r3.json` 保存百炼 `qwen-plus` 三策略各 3 次对比，`development-summary.json` 保存均值、范围和总体标准差；`latest-development.json` 指向生产默认 `hybrid_rrf_reranker` 的第 3 次报告。容器内无 git 元数据，`code_commit` 记为 `unknown0`。
- 60 条 development 对三策略各重复 3 次，共 540 次真实执行。纯向量、Hybrid RRF、Hybrid + Reranker 核心通过率均值分别为 55.56%、60.56%、56.11%；Hybrid RRF 相对纯向量提升 5.00 个百分点。
- Reranker 的 Recall@5 均值为 95.62%，高于纯向量 93.97%，但 P50/P95 增至 7.98s/15.25s；这是一项召回与延迟权衡，不代表全面更准。
- 9 份重复报告的权限泄漏率均为 0。
- 20 条 v2 frozen holdout 已在部署版本 `10993fa` 上一次性运行：执行成功率 95.00%、核心通过率 90.00%、Recall@5 100.00%、引用准确率 97.06%、引用召回 100.00%、正确拒答率 100.00%、权限泄漏率 0%、P50/P95 6.79s/12.58s。
- frozen 中 1 条远程 `ModelProviderError` 和 1 条多余引用均保留在分母；报告归档为 `evaluation/reports/final-holdout-v2.json`，禁止调参后重跑，数字只代表当时快照。
- README、简历和验收材料只能引用 `evaluation/reports/` 可追溯的指标，不能填写用户数或生产指标。

## 5. 下一次运行顺序

### 本地或 CI 交付检查

```powershell
python -m pytest
ruff check src tests scripts
npm --prefix frontend run test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build
```

Windows 本地若无法创建临时文件，应设置可写的 `TEMP`/`TMP` 后重试；Docker 和 PostgreSQL 相关检查优先以 GitHub Actions 的 `delivery-smoke` 为准。

### 复现 development 评测

1. 准备 PostgreSQL + pgvector，并执行迁移和索引。
2. 配置固定的 `EMBEDDING_MODEL`、`RERANKER_MODEL`、`MODEL_NAME`、提示词版本和温度。
3. 确认 `/ready` 通过，先运行少量 development smoke。
4. 设置 `EVAL_REPETITIONS`，运行 `python scripts/run_development.py`。
5. 对三种策略分别保存报告，比较核心结果、拒答正确率、引用准确率、延迟和模型调用次数。
6. frozen holdout 已经消费并归档；后续只读最终报告，不再运行。

## 6. 运行安全边界

- development 入口只加载 `evaluation/development-v2.json`；不要为了方便修改为自动读取冻结集。
- 不要把合成语料写成真实企业数据，不要把本地演示身份写成正式认证。
- 不要在未生成真实报告前写“准确率 100%”。
- 不要用 `docker compose down --volumes` 清理包含重要数据的环境。
- 不要改写已提交迁移；新增数据库变化必须增加迁移文件。

## 7. 建议的后续拆分

按优先级依次完成：正式认证与多租户隔离、备份恢复演练、限流和连接池压测、监控告警、自动发布回滚。受控 development 与冻结集最终验收已经完成；后续内容应标为边界或迭代计划。
