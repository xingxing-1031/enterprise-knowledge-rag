# 企业运营多 Agent 助手

面向企业员工的按需多 Agent 演示项目。Supervisor 根据问题选择通用对话、企业知识、经营数据或多 Agent 协作路径；企业知识沿用可审计 RAG，经营数据通过受认证内部接口调用零售分析 Agent。

## 当前状态

项目已完成 Supervisor、通用对话 Agent、知识 Agent、数据 Agent、综合 Agent 与审核 Agent。简单问题只调用一个必要角色；同时需要企业制度与经营数据的任务才并行执行知识和数据子任务，再进行受证据约束的综合与审核。

知识 Agent 具备版本化合成语料、受控文档导入、标题感知切分、父文档/子章节双层索引、权限与版本过滤、BM25 + 向量 + RRF + Reranker、最多两跳的证据补全、引用校验和拒答。数据 Agent 复用项目一的业务 Skill、Text-to-SQL、SQLGlot AST、业务一致性、审批、审计、图表和 MCP 报告导出能力，不在本项目复制数据库逻辑。

真实运行适配器、连接池、增量迁移与索引命令、启动入口和 React 企业知识工作台已经接通。Docker Compose 按 PostgreSQL、迁移、索引、API 的顺序启动，并由 FastAPI 同源提供前端。公网演示已部署 PostgreSQL/pgvector，Embedding、Reranker 与生成均走百炼远程模型（`text-embedding-v3` / `qwen3-rerank` / `qwen-plus`），演示默认使用 `hybrid_rrf_reranker`。

## 快速启动

```powershell
docker compose up -d --build --wait
```

启动完成后打开 `http://127.0.0.1:8010/`。首次运行需要下载本地检索模型，具体配置、迁移、索引、验证和安全清理方式见 [`docs/OPERATIONS.md`](docs/OPERATIONS.md)。

## 固定演示场景

1. 通用对话：解释 RAG、润色文字或进行普通聊天，不伪造企业事实。
2. 知识任务：返回当前生效制度、章节、版本和引用。
3. 数据任务：调用经营分析 Agent 返回数据结论、图表、工具轨迹和数据证据。
4. 协作任务：例如“分析退款率变化并判断是否触发售后制度”，知识与数据 Agent 并行执行，综合 Agent 汇总，审核 Agent 检查证据完整性。
5. 权限或证据不足：不泄露受限文档，也不使用通用模型常识补全企业制度和经营数字。

## 多 Agent Development 评测

`evaluation/multi_agent_development.jsonl` 包含 26 条合成 development 样本，覆盖通用、知识、数据和协作四类路由，并包含“分析文字”“Python 数据结构”“公司销售额”等容易被误路由的反例。确定性回退 Supervisor 的当前结果为：路由准确率 `26/26`，期望角色选择 `26/26`。原始样本级报告见 `evaluation/reports/multi-agent-development-20260813T231151Z.json`。

这组结果只证明当前规则对该 development 契约的覆盖，不是通用意图识别准确率，也不代表公网端到端任务成功率。端到端数据、知识和协作任务仍分别受模型、数据库、检索和网络延迟影响。

## 管理员导入

知识管理员可导入 `.pdf`、`.docx`、`.md` 和 `.txt`。服务端限制单文件 15 MiB、PDF 200 页，并在索引前展示清洗报告与规范化预览。扫描件、空文件、损坏文件、格式/签名不一致和超限文件会进入隔离状态，未经管理员确认的元数据和正文不会进入索引。

## Development 评测

在 18 条合成 development 用例上，固定 25 份文档语料快照（`sha256:d5148700…`）、百炼远程模型（Embedding `text-embedding-v3` / Reranker `qwen3-rerank` / 生成 `qwen-plus`）、Prompt 和运行环境，对三种检索策略各重复 3 次。报告由生产容器重跑，容器内无 git 元数据，`code_commit` 记为 `unknown0`，可复现条件以语料快照与模型标识为准：

| 策略 | 执行成功率均值 | 核心通过率均值（范围） | Recall@5 均值 | 引用准确率均值 | 证据覆盖 / 二跳成功 | P50 / P95 均值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 纯向量 | 100.00% | 57.41%（55.56%–61.11%） | 75.46% | 70.83% | 30.00% / 0.00% | 4.78s / 7.65s |
| Hybrid RRF | 98.15% | 53.70%（50.00%–55.56%） | 75.46% | 66.20% | 30.00% / 0.00% | 4.73s / 8.44s |
| Hybrid + Reranker | 98.15% | 61.11%（61.11%–61.11%） | 74.54% | 83.33% | 40.00% / 0.00% | 5.46s / 7.66s |

全部 9 次策略运行的权限泄漏率均为 0。本轮 25 份文档语料上，Reranker 的核心通过率（61.11%）与引用准确率（83.33%）均为三策略最高，证据覆盖也最高（40.00%），P95 均值（7.66s）与纯向量（7.65s）持平。Hybrid RRF 本轮核心通过率（53.70%）仍低于纯向量（57.41%），三策略二跳成功率均为 0（多跳用例的 gold 口径限制）。这组数据说明检索策略优劣对语料与用例敏感，单轮对比不能外推；演示默认使用 `hybrid_rrf_reranker` 是为了展示完整检索链路（BM25 + 向量 RRF + 重排），是否采用仍要看冻结集与成本。完整均值、范围与总体标准差见 [`evaluation/reports/development-summary.json`](evaluation/reports/development-summary.json)，指标定义与限制见 [`docs/EVALUATION_PROTOCOL.md`](docs/EVALUATION_PROTOCOL.md)。

固定配置后一次性消费了 8 条合成 frozen holdout（提交 `f31a2e2`、默认 Hybrid RRF、本地 `bge-m3`、`qwen-plus`、12 份文档语料快照 `sha256:810fac…`）：执行成功率 75.00%、核心通过率 62.50%、Recall@5 100.00%、引用准确率 85.00%、权限泄漏率 0%、P50/P95 6.93s/41.45s。两条远程 `ModelProviderError` 保留在分母中，验收后未根据结果调参或重跑。该冻结集的语料与模型配置早于当前生产部署，且已一次性消费，数字只代表当时快照，不代表当前生产策略。原始证据见 [`evaluation/reports/final-holdout.json`](evaluation/reports/final-holdout.json)。

## 诚实边界

这是个人独立项目和受限演示，不代表真实企业上线、团队协作、客户使用或多租户生产系统。简历数字只使用 `evaluation/reports/` 中的实际报告。
