# 企业知识库 RAG 服务

这是“知枢 Nexus”企业智能 Agent 平台的独立可信证据后端。它只负责文档进入知识库、权限过滤、混合检索、重排、证据覆盖、引用和拒答，不负责通用聊天、经营数据库查询或 Agent 编排。

## 服务边界

```text
文档导入 -> 解析/清洗/切分 -> BM25 + 向量 -> RRF -> Reranker
                                                   |
                         权限/版本/生效时间 -> Evidence -> 引用回答
```

项目一“知枢 Nexus”通过带 `X-Internal-Token` 的 `/internal/evidence` 调用本服务。项目二不会反向调用项目一，因此不存在循环依赖。直接访问本项目只提供知识库管理员控制台，不提供普通用户聊天入口。

## 核心能力

- PDF、DOCX、Markdown、TXT 解析、清洗、标题感知切分和管理员复核导入
- 文档版本、生效时间、部门和角色权限过滤
- BM25、向量检索、RRF 融合和可选 Reranker
- 父文档路由、结构化证据需求、有限二跳补全
- 引用校验、证据覆盖率、证据不足拒答和降级
- `/internal/evidence` 受认证证据 API
- 单管理员认证、导入审核、文档停用/恢复/重建索引/永久删除、审计墓碑
- 检索实验室：权限过滤、BM25、向量、RRF、Rerank、证据链路诊断
- PostgreSQL/pgvector、FastAPI、React/Vite
- development 与 frozen holdout 评测报告，所有指标均可追溯到报告文件

## 快速启动

```powershell
docker compose up -d --build --wait
```

默认打开 `http://127.0.0.1:8010/`，使用 `knowledge-admin-demo / KnowledgeAdmin2026!` 进入演示控制台。迁移、索引、模型和安全运维说明见 [`docs/OPERATIONS.md`](docs/OPERATIONS.md)。

## 可复现评测

开发集入口是 `scripts/run_development.py`，评测报告位于 `evaluation/reports/`。当前已保存的报告只代表对应语料、模型和代码快照，不外推为通用准确率，也不冒充生产 SLA。指标定义见 [`docs/EVALUATION_PROTOCOL.md`](docs/EVALUATION_PROTOCOL.md)，面试讲解见 [`docs/INTERVIEW_GUIDE_RAG.md`](docs/INTERVIEW_GUIDE_RAG.md)。

当前 v2 评测使用 60 条 development 用例，对三种策略各重复 3 次，共 540 次真实执行。Hybrid RRF 的核心通过率均值为 60.56%，相对纯向量 55.56% 提升 5.00 个百分点；加入 Reranker 后 Recall@5 均值从 93.97% 提升至 95.62%，但 P50 从 7.64s 增至 7.98s，说明重排存在可观测的效果/延迟权衡。20 条一次性 frozen holdout 的核心通过率为 90.00%、Recall@5 与引用召回均为 100%、引用准确率 97.06%、正确拒答率 100%、权限泄漏率 0%。

## 诚实边界

这是个人独立项目，使用脱敏/合成企业制度语料，不代表真实企业客户、用户规模、多租户生产系统或团队协作成果。项目一的 Text-to-SQL、MCP、通用 Agent 和跨域协作能力不在本仓库重复实现。
