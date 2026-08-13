# 多 Agent 简历证据与表述

## 可直接使用的项目描述

独立设计并实现面向企业运营的按需多 Agent 助手，由 Supervisor 将请求路由至通用对话、企业知识、经营数据或协作模式；知识 Agent 负责权限、版本、混合检索、Reranker 与引用校验，数据 Agent 通过受认证内部接口复用 Text-to-SQL、SQLGlot AST、业务一致性、审批与审计能力，复杂任务由综合 Agent 汇总并经审核 Agent 校验证据完整性。

建立包含通用反例、制度查询、经营指标和跨域复盘的 26 条合成 development 路由集，当前路由与期望角色选择均为 26/26；该数字仅代表当前 development 契约，不表述为通用 Agent 准确率。

## 简历关键词

Python、FastAPI、LangGraph、Supervisor、Multi-Agent、RAG、BM25、向量检索、RRF、Reranker、Context Management、Text-to-SQL、SQLGlot、MCP、SSE、React、TypeScript、PostgreSQL、pgvector。

## 可以证明的工程边界

- `8010` 是统一入口，普通聊天不会启动知识和数据工具。
- 单一企业制度问题只走知识 Agent；单一经营问题只走数据 Agent。
- 复杂问题并行执行知识与数据任务，最终结果必须同时具有企业引用和数据 evidence ID 才通过审核。
- 项目一和项目二通过 64 位共享内部令牌通信，浏览器和公开 OpenAPI 不暴露内部接口。
- 项目一内部调用设置 `include_knowledge=false`，避免它再次调用项目二造成递归，并保持知识/数据职责隔离。

## 不应写入简历的表述

- 不写“生产级多租户平台”或“真实企业上线”。
- 不写“多 Agent 准确率 100%”；只能写 26 条 development 路由样本 26/26。
- 不声称 Agent 自由自主循环；当前是 Supervisor 生成结构化计划并进行有界调度。
- 不声称所有角色都是独立大模型实例；角色按职责、上下文和工具权限隔离，可复用同一个模型 API。
