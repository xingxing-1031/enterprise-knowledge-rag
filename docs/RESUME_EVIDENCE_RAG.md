# 简历证据：企业知识库 RAG

## 项目描述（可直接改写进简历）

独立设计并实现企业知识库 RAG 服务，围绕企业制度问答构建“解析清洗、权限治理、混合检索、证据覆盖、引用回答、拒答降级”闭环。文档按版本和生效时间管理，检索层融合 BM25 与向量召回，使用 RRF 和 Reranker 提升候选排序质量；通过结构化证据需求与引用校验，避免模型在证据不足时编造制度结论，并以受认证 `/internal/evidence` API 为项目一提供可审计证据。

## 技术关键词

Python、FastAPI、LangGraph、PostgreSQL、pgvector、BM25、向量检索、RRF、Reranker、权限过滤、版本治理、Evidence API、SSE、Docker Compose、React、TypeScript。

## 数据写法

只引用 `evaluation/reports/` 中已保存的实际报告，并同时说明语料快照、模型、评测集和限制。不要把 development 结果写成通用准确率，也不要声称真实客户或生产 SLA。

Agentic RAG v2 可描述为：基于 Query Decomposition 将复合问题拆分为结构化证据需求，并按证据缺口触发有界 Iterative Retrieval，在权限、版本与证据预算约束下完成跨文档证据聚合。不得把尚未运行的 v2 评测目标写成实际结果。
