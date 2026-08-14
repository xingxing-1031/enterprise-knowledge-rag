# 企业知识库 RAG 服务

这是“企析”项目的独立企业知识库 RAG 子项目。它只负责文档进入知识库、权限过滤、混合检索、重排、证据覆盖、引用和拒答，不负责通用聊天、经营数据库查询或 Agent 编排。

## 服务边界

```text
文档导入 -> 解析/清洗/切分 -> BM25 + 向量 -> RRF -> Reranker
                                                   |
                         权限/版本/生效时间 -> Evidence -> 引用回答
```

项目一“企析”通过带 `X-Internal-Token` 的 `/internal/evidence` 调用本服务。项目二不会反向调用项目一，因此不存在循环依赖。直接访问本项目仍可使用 RAG 对话工作台、文档管理和评测页面。

## 核心能力

- PDF、DOCX、Markdown、TXT 解析、清洗、标题感知切分和管理员复核导入
- 文档版本、生效时间、部门和角色权限过滤
- BM25、向量检索、RRF 融合和可选 Reranker
- 父文档路由、结构化证据需求、有限二跳补全
- 引用校验、证据覆盖率、证据不足拒答和降级
- `/internal/evidence` 受认证证据 API
- PostgreSQL/pgvector、FastAPI、LangGraph、SSE、React/Vite
- development 与 frozen holdout 评测报告，所有指标均可追溯到报告文件

## 快速启动

```powershell
docker compose up -d --build --wait
```

默认打开 `http://127.0.0.1:8010/`。迁移、索引、模型和安全运维说明见 [`docs/OPERATIONS.md`](docs/OPERATIONS.md)。

## 可复现评测

开发集入口是 `scripts/run_development.py`，评测报告位于 `evaluation/reports/`。当前已保存的报告只代表对应语料、模型和代码快照，不外推为通用准确率，也不冒充生产 SLA。指标定义见 [`docs/EVALUATION_PROTOCOL.md`](docs/EVALUATION_PROTOCOL.md)，面试讲解见 [`docs/INTERVIEW_GUIDE_RAG.md`](docs/INTERVIEW_GUIDE_RAG.md)。

## 诚实边界

这是个人独立项目，使用脱敏/合成企业制度语料，不代表真实企业客户、用户规模、多租户生产系统或团队协作成果。项目一的 Text-to-SQL、MCP、通用 Agent 和跨域协作能力不在本仓库重复实现。
