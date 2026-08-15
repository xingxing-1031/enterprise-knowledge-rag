# 简历证据：企业知识库 RAG

## 项目描述（可直接改写进简历）

独立设计并实现企业知识库 RAG 服务，围绕企业制度问答构建“解析清洗、权限治理、混合检索、证据覆盖、引用回答、拒答降级”闭环。文档按版本和生效时间管理，检索层融合 BM25 与向量召回，使用 RRF 和 Reranker 提升候选排序质量；通过结构化证据需求与引用校验，避免模型在证据不足时编造制度结论，并以受认证 `/internal/evidence` API 为项目一提供可审计证据。

## 技术关键词

Python、FastAPI、LangGraph、PostgreSQL、pgvector、BM25、向量检索、RRF、Reranker、权限过滤、版本治理、Evidence API、SSE、Docker Compose、React、TypeScript。

## 数据写法

只引用 `evaluation/reports/` 中已保存的实际报告，并同时说明语料快照、模型、评测集和限制。不要把 development 结果写成通用准确率，也不要声称真实客户或生产 SLA。

Agentic RAG v2 可描述为：基于 Query Decomposition 将复合问题拆分为结构化证据需求，并按证据缺口触发有界 Iterative Retrieval，在权限、版本与证据预算约束下完成跨文档证据聚合。

当前可核验数据：

- 27 个文档版本、24 个当前生效文档、103 个切片；线上使用远程 `text-embedding-v3`、`qwen3-rerank` 与 `qwen-plus`。
- 60 条 development × 3 策略 × 3 次，共 540 次真实执行。Hybrid RRF 核心通过率均值 60.56%，相对纯向量 55.56% 提升 5.00 个百分点。
- Reranker 将 Recall@5 均值从 93.97% 提升到 95.62%、引用召回从 92.61% 提升到 94.27%，但 P50 从 7.64s 增至 7.98s；只能写成效果/延迟权衡，不能写成全面提升。
- 20 条 frozen holdout 一次性验收：执行成功率 95.00%、核心通过率 90.00%、Recall@5 100%、引用准确率 97.06%、引用召回 100%、正确拒答率 100%、权限泄漏率 0%、P50/P95 6.79s/12.58s。

推荐简历写法：在 60 条 development 上完成三策略各 3 次、共 540 次真实对照，Hybrid RRF 核心通过率较纯向量提升 5.00 个百分点；20 条一次性 frozen holdout 达到核心通过率 90%、Recall@5/引用召回 100%、引用准确率 97.06%、权限泄漏率 0%，并将 1 条远程模型异常保留在分母中。
