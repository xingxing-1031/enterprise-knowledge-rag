# 企业知识 RAG 受控评测协议

## 1. 目的与边界

本协议用于比较检索方案并定位工作流问题，不把单个总分当作 Agent 的真实准确率。语料均为项目构造的合成企业制度，评测结果不能表述为真实企业用户效果。

当前已完成三策略各 3 次的真实 development 实验，原始报告与聚合结果保存在 `evaluation/reports/`。README 和简历只能引用报告中可追溯的均值、波动、延迟或提升比例，并明确这是合成 development 集结果。

## 2. 数据隔离

- `evaluation/development.json` / `evaluation/frozen_holdout.json`：历史 v1 题集与报告，只作对照。
- `evaluation/development-v2.json`：60 条当前开发集，可用于调试、错误分析和策略优化。
- `evaluation/frozen-holdout-v2.json`：20 条当前冻结集，已在代码和配置固定后消费一次，默认运行器仍拒绝执行。
- 冻结集只允许在代码、配置和 development 结论固定后，由最终验收入口显式解锁一次。
- 只要根据 frozen 结果修改过代码、Prompt、阈值或数据，该题集立即降级为 development，不能继续称为未见集。
- 题集文件不被聊天 API 或工作流导入，避免标准答案进入运行上下文。

校验 frozen 文件结构不等于消费冻结集；把问题提交给 Agent 并获得结果才算消费。

## 3. 人工标准答案

每条题目人工指定：

- 查询时间、可信用户角色和部门；
- 预期是否属于企业知识范围；
- 预期回答或拒答类型；
- 正确文档、版本和章节；
- 不能进入候选集的受限文档；
- 必须由原文支持的关键事实。

证据键格式为 `document_id@version#末级章节名`。契约测试会从 Markdown 重新解析并切分语料，确认 gold 证据、版本和关键事实确实存在。Agent 输出不会参与标准答案生成。

## 4. 固定变量

每份真实报告必须记录：

- 代码提交和语料快照哈希；
- 题集 ID、版本和 split；
- Embedding、Reranker、LLM 与 Prompt 版本；
- 查询改写、权限、版本、证据预算、超时和重试配置；
- 检索池大小、最终 Top K 和随机参数；
- 运行时间、机器环境和重复次数。

比较实验只允许改变 `vector_baseline`、`hybrid_rrf`、`hybrid_rrf_reranker` 这一项。先跑少量 development smoke，确认数据和评分方向正确，再运行完整 development；不能看到全量结果后为某一方案单独修改共享策略。

## 5. 分阶段评分

- `domain_accuracy`：范围判断是否与人工标签一致。
- `recall_at_k`：Top K 覆盖了多少正确证据。
- `reciprocal_rank`：第一个正确证据出现得有多早。
- `ndcg_at_k`：多个正确证据的整体排序质量。
- `access_leakage_rate`：受限文档是否进入候选；目标必须为 0。
- `version_accuracy`：是否只选择查询时间对应的正确版本。
- `citation_accuracy`：引用是否指向人工 gold 证据。
- `correct_refusal_rate`：应拒答题是否按正确原因拒答。
- `false_refusal_rate`：可回答题是否被错误拒绝。
- `automated_answer_score`：关键事实的确定性覆盖率，仅作初筛。
- `document_route_recall`：父文档路由覆盖 gold 文档的比例。
- `evidence_need_coverage`：必需证据需求被最终证据覆盖的比例。
- `second_hop_trigger_accuracy`：应触发/不应触发第二跳是否与标注一致。
- `second_hop_success`：标注为两跳的问题是否在第二跳后覆盖全部必需需求。
- `irrelevant_evidence_ratio`：最终候选中不属于 gold 文档的比例。
- `core_pass_rate`：范围、召回、安全、版本、引用或拒答核心链路是否整体通过。
- `execution_success_rate`：执行异常也进入分母，不能从报告中丢弃。
- P50/P95 延迟与模型调用次数：衡量效果之外的成本。

数字、空格差异可标准化；完整答案的语义正确性仍需独立人工盲审。核心结果错误时，不因语言流畅而判整题成功。

## 6. 失败与报告

单题超时或服务异常记录异常类型，保留该题并计入失败，不写入密钥、供应商原始错误或受限正文。报告保留逐题观察值和阶段分数，汇总值只用于概览。

不能只报告最好一次。真实对比需要同样的重复次数，报告均值、波动、延迟和模型调用成本；某方案是否更好必须结合核心通过率、安全、泛化和成本判断。

## 7. 当前状态

- 题集结构、gold 证据契约、评分器、冻结锁定与并发结果顺序均有自动化测试。
- 生产服务器当前索引 27 个文档版本、24 个生效文档、103 个切片；语料快照为 `sha256:24af1c83…`。
- v2 development 在腾讯云生产容器使用 `text-embedding-v3`、`qwen3-rerank`、`qwen-plus`，三策略各 3 次，共 540 次真实执行。部署版本经发布记录核验为 `10993fa`；镜像未复制 `.git`，因此原始报告内 `code_commit` 字段保留为 `unknown0`，未手工篡改。
- 纯向量、Hybrid RRF、Hybrid + Reranker 的核心通过率均值分别为 55.56%、60.56%、56.11%；Hybrid RRF 相对纯向量提升 5.00 个百分点。
- 三策略 Recall@5 均值分别为 93.97%、92.28%、95.62%，引用召回分别为 92.61%、91.61%、94.27%。Reranker 提升召回，但 P50/P95 为 7.98s/15.25s，高于纯向量 7.64s/13.73s，不能表述为全面更优。
- 9 份 development 报告的权限泄漏率均为 0，执行成功率均值为 98.89%–99.44%。
- 20 条 v2 frozen holdout 已一次性消费并归档为 `evaluation/reports/final-holdout-v2.json`：执行成功率 95.00%、核心通过率 90.00%、Recall@5 100%、引用准确率 97.06%、引用召回 100%、正确拒答率 100%、权限泄漏率 0%、P50/P95 6.79s/12.58s。1 条远程模型异常和 1 条多余引用均保留在分母中。

## 8. 分层与多跳指标

Development 题集额外记录父文档路由召回、必需证据需求覆盖、第二跳触发准确性、第二跳成功率和无关证据比例。异常题保留在执行成功率和核心通过率分母中；这些指标只描述当前报告，不代表生产效果。

## 8.1 Agentic RAG v2

- `evaluation/development-v2.json` 包含 60 条当前语料用例，覆盖 24 个逻辑文档、三种角色和六个部门。
- `evaluation/frozen-holdout-v2.json` 包含 20 条冻结用例，已一次性消费。
- v2 使用 Query Decomposition 将复合问题拆成 evidence needs，并按缺口执行最多一次 Iterative Retrieval；“两阶段”是成本边界，不是对外算法名称。
- 新报告增加 Citation Recall、need coverage precision、阶段耗时、P99 和安全错误码。
- v2 原始报告与聚合结果已归档，README 与简历只引用其中可复核的真实数字。

## 9. 一次性冻结验收入口

v1 冻结集曾在提交 `f31a2e2` 上执行一次，历史报告保留为 `final-holdout.json`。v2 冻结集在部署版本 `10993fa` 上执行一次，命令如下，仅作审计记录，不得覆盖现有输出：

```powershell
$env:FROZEN_HOLDOUT_CONFIRM = "CONSUME_ONCE"
.\.venv\Scripts\python.exe scripts\run_final_holdout.py
```

入口会拒绝错误确认串，也不会覆盖已有的 `evaluation/reports/final-holdout-v2.json`。v2 结果为：20 条、执行成功率 95.00%、核心通过率 90.00%、Recall@5 100.00%、引用准确率 97.06%、引用召回 100.00%、正确拒答率 100.00%、权限泄漏率 0%、P50/P95 6.79s/12.58s。验收后没有根据单题结果修改代码、Prompt、阈值或数据。
