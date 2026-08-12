# 企业制度与流程知识库助手

面向企业员工的可审计 RAG 演示项目。项目使用构造的脱敏制度语料，重点验证文档版本、生效时间、部门权限、混合检索、引用和拒答。

## 当前状态

项目已完成版本化合成语料、受控文档导入、标题感知切分、父文档/子章节双层索引、权限与版本过滤、BM25 + 向量 + RRF + Reranker、最多两跳的证据补全、引用校验、拒答、LangGraph、FastAPI/SSE 和受控评测框架。

真实运行适配器、连接池、增量迁移与索引命令、启动入口和 React 企业知识工作台已经接通。Docker Compose 按 PostgreSQL、迁移、索引、API 的顺序启动，并由 FastAPI 同源提供前端。公网演示已部署 PostgreSQL/pgvector，Embedding、Reranker 与生成均走百炼远程模型（`text-embedding-v3` / `qwen3-rerank` / `qwen-plus`），演示默认使用 `hybrid_rrf_reranker`。

## 快速启动

```powershell
docker compose up -d --build --wait
```

启动完成后打开 `http://127.0.0.1:8010/`。首次运行需要下载本地检索模型，具体配置、迁移、索引、验证和安全清理方式见 [`docs/OPERATIONS.md`](docs/OPERATIONS.md)。

## 固定演示场景

1. 正常查询：返回当前生效制度、章节和版本引用。
2. 历史查询：按明确时间选择旧版本。
3. 权限拒绝：不泄露受限文档的标题和内容。
4. 证据不足：明确拒答，不使用模型常识补全企业规则。
5. 多文档问题：先路由父文档，再按证据需求召回章节；仅在必需需求未覆盖时执行一次补充检索。

## 管理员导入

知识管理员可导入 `.pdf`、`.docx`、`.md` 和 `.txt`。服务端限制单文件 15 MiB、PDF 200 页，并在索引前展示清洗报告与规范化预览。扫描件、空文件、损坏文件、格式/签名不一致和超限文件会进入隔离状态，未经管理员确认的元数据和正文不会进入索引。

## Development 评测

在 18 条合成 development 用例上，固定 25 份文档语料快照（`sha256:d5148700…`）、百炼远程模型（Embedding `text-embedding-v3` / Reranker `qwen3-rerank` / 生成 `qwen-plus`）、Prompt 和运行环境，对三种检索策略各重复 3 次。报告由生产容器重跑，容器内无 git 元数据，`code_commit` 记为 `unknown0`，可复现条件以语料快照与模型标识为准：

| 策略 | 执行成功率均值 | 核心通过率均值（范围） | Recall@5 均值 | 引用准确率均值 | 证据覆盖 / 二跳成功 | P50 / P95 均值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 纯向量 | 100.00% | 51.85%（50.00%–55.56%） | 75.46% | 63.89% | 30.00% / 0.00% | 4.98s / 8.91s |
| Hybrid RRF | 100.00% | 46.30%（44.44%–50.00%） | 76.39% | 62.04% | 30.00% / 0.00% | 5.03s / 13.80s |
| Hybrid + Reranker | 100.00% | 57.41%（55.56%–61.11%） | 75.46% | 80.56% | 40.00% / 0.00% | 5.69s / 28.26s |

全部 9 次策略运行的权限泄漏率均为 0。本轮 25 份文档语料上，Reranker 的核心通过率（57.41%）与引用准确率（80.56%）均为三策略最高，证据覆盖也最高（40.00%）；但它的 P95 均值（28.26s）明显高于纯向量（8.91s）与 Hybrid RRF（13.80s）。Hybrid RRF 本轮核心通过率（46.30%）反而低于纯向量（51.85%），三策略二跳成功率均为 0（多跳用例的 gold 口径限制）。这组数据说明检索策略优劣对语料与用例敏感，单轮对比不能外推；演示默认使用 `hybrid_rrf_reranker` 是为了展示完整检索链路（BM25 + 向量 RRF + 重排），是否采用仍要看冻结集与成本。完整均值、范围与总体标准差见 [`evaluation/reports/development-summary.json`](evaluation/reports/development-summary.json)，指标定义与限制见 [`docs/EVALUATION_PROTOCOL.md`](docs/EVALUATION_PROTOCOL.md)。

固定配置后一次性消费了 8 条合成 frozen holdout（提交 `f31a2e2`、默认 Hybrid RRF、本地 `bge-m3`、`qwen-plus`、12 份文档语料快照 `sha256:810fac…`）：执行成功率 75.00%、核心通过率 62.50%、Recall@5 100.00%、引用准确率 85.00%、权限泄漏率 0%、P50/P95 6.93s/41.45s。两条远程 `ModelProviderError` 保留在分母中，验收后未根据结果调参或重跑。该冻结集的语料与模型配置早于当前生产部署，且已一次性消费，数字只代表当时快照，不代表当前生产策略。原始证据见 [`evaluation/reports/final-holdout.json`](evaluation/reports/final-holdout.json)。

## 诚实边界

这是个人独立项目和受限演示，不代表真实企业上线、团队协作、客户使用或多租户生产系统。简历数字只使用 `evaluation/reports/` 中的实际报告。
