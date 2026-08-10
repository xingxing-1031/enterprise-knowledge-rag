# Enterprise Knowledge RAG 求职版收尾设计

日期：2026-08-11  
状态：待用户复核  
范围：仅 `enterprise-knowledge-rag`；项目一、简历和面试准备在本阶段完成后分别处理

## 1. 目标

把项目二从“功能链路已接通”收敛为可用于实习与秋招答辩的受控 RAG 项目。重点不是继续增加功能，而是解决当前报告已经暴露的两类核心问题：

1. 模型自由生成 `need_id`，导致运行时 `certificate_req`、`package` 等标识与 development gold 的 `material`、`registration` 无法比较。
2. 多跳 development 用例没有稳定获得两跳预算，当前三种策略的 `second_hop_success` 均为 `0`。

同时处理 Reranker 冷启动长尾、重复实验和最终冻结验收，使简历数字能够追溯到提交后的原始报告。

## 2. 当前基线

固定语料快照和 17 条 development 用例已分别使用本地 `qwen3:4b` 与百炼 `qwen-plus` 完成单次三策略评测。

`qwen-plus` 当前结果：

| 策略 | 执行成功率 | 核心通过率 | Recall@5 | P50 / P95 |
| --- | ---: | ---: | ---: | ---: |
| 纯向量 | 88.24% | 52.94% | 83.33% | 6.42s / 35.93s |
| Hybrid RRF | 94.12% | 52.94% | 83.33% | 6.45s / 10.48s |
| Hybrid + Reranker | 100% | 58.82% | 83.33% | 7.89s / 617.34s |

三种策略权限泄漏率均为 `0`，但第二跳成功率均为 `0`。Reranker 的首个请求出现约 617 秒冷启动长尾，因此当前结果不足以支持把它作为默认演示策略。

## 3. 非目标

- 不新增第三跳、开放式 Agent 自主循环或多个 Sub-agent。
- 不扩展新的文档格式、认证系统、多租户或公网部署。
- 不读取或修改 `evaluation/frozen_holdout.json` 来指导本轮开发。
- 不为了让指标变好而逐题硬编码查询、文档 ID、版本或答案。
- 不把 development 指标表述为生产准确率或泛化能力。

## 4. 稳定证据需求契约

### 4.1 服务端拥有 `need_id`

LLM 继续负责输出受约束的 `EvidenceKind`、检索 query 和是否必需，不再拥有最终 ID 的语义命名权。服务端在计划校验后按证据类型和出现顺序规范化：

```text
material
exception
rule
rule_2
deadline
```

单一类型使用类型名；同类型重复出现时追加从 2 开始的序号。原始用户问题和模型 query 仍承载具体语义，ID 只用于运行时关联、引用校验和评测。

这样可以消除 `certificate_req` / `material`、`package` / `registration` 一类字符串漂移，同时不使用模糊字符串映射猜测模型意图。

### 4.2 Development gold 同步规范化

`evaluation/development.json` 中 `required_need_ids` 改为同一套规范化 ID。只修改 development：

- 病假材料与紧急流程：`material`、`exception`
- 新供应商门槛与登记材料：`rule`、`material`
- 报销期限：`deadline`
- 缺失例外：`exception`
- 受限付款例外：`exception`

Gold 描述的是证据类型契约，不复制模型的自由文本命名。冻结集保持字节级不变。

## 5. 有界第二跳

### 5.1 预算由服务端校正

模型仍可表达 `requires_multi_hop`，但服务端不完全信任该布尔值。满足以下任一条件时允许最多两跳：

- 存在两个或以上必需证据需求；
- 模型明确标记需要多跳。

安全 fallback 仍保持单一 `rule` 需求和一跳，避免模型完全失败时扩大检索。

### 5.2 检索流程

```text
父文档权限、版本过滤
-> primary_query 路由父文档
-> primary_query 完成第一跳章节召回
-> 确定性 coverage 标注已覆盖需求
-> 仅对缺失的 required need 使用 need.query 做一次补充召回
-> 第二跳仍限制在第一跳已授权并路由的文档键内
-> 合并、去重、预算分配、最终 coverage
```

不无条件执行第二跳。如果第一跳已完整覆盖必需证据，直接生成回答更正确，也更节省延迟。

### 5.3 真实验收场景

至少以下两个 development answer 用例应在固定配置下真实触发第二跳，并在第二跳后覆盖全部规范化需求：

- `dev-hr-leave-emergency-two-hop`
- `dev-procurement-supplier-two-hop`

权限用例 `dev-finance-restricted-supplement-no-leak` 必须保持受限文档不进入路由、候选、证据和报告。无论是否触发补充召回，`access_leakage_rate` 必须为 `0`。

如果第一跳因检索改进已经稳定完整覆盖某个 answer 用例，不应人为删除正确证据来强迫两跳；此时应新增或重写 development 场景，使其自然表达隐含的补充证据需求，并记录该变更原因。

## 6. 默认检索策略与冷启动

当前不把 Reranker 预热作为首选方案。预热只会把约 617 秒成本从首个请求移动到启动阶段，还会延迟 readiness。

求职演示默认使用 `Hybrid RRF`：

- 当前执行成功率 `94.12%`；
- P50/P95 为 `6.45s / 10.48s`，尾延迟最稳定；
- 与 Reranker 相比，当前核心通过率只低 5.88 个百分点；
- 不依赖 CrossEncoder 首次推理完成后才能正常演示。

`Hybrid + Reranker` 继续作为可选评测策略保留。最终默认值必须由修复后的三次 development 均值重新确认；如果 Reranker 在长驻同进程的重复实验中同时取得稳定质量收益和可接受延迟，可以重新选择。

## 7. 实验与冻结规则

### 7.1 Development

完成代码、Prompt、development gold 和配置修复后：

1. 先运行相关确定性测试和少量 development smoke。
2. 固定代码提交、语料快照、`qwen-plus`、`bge-m3`、Reranker、Prompt、温度和数据库快照。
3. 同一进程运行三种策略，每种策略重复 3 次。
4. 保存每次原始 JSON，不只保留最好一次。
5. 汇总均值、最小值、最大值或标准差，并单独报告冷启动与热运行延迟。

选择默认策略时按以下顺序判断：

1. 权限泄漏率必须为 0。
2. 执行成功率和核心通过率。
3. 两跳成功、引用准确率和错误拒答。
4. P50/P95、模型调用次数和冷启动成本。

### 7.2 Frozen holdout

只有在代码、Prompt、语料、development 结论和默认策略全部提交后，才运行一次 frozen holdout。运行后：

- 原始报告立即提交；
- 不根据具体 frozen 失败题继续调参并保留“未见集”称号；
- 简历必须同时说明题数、重复次数、指标名称和合成数据边界。

## 8. 测试与验证

新增或更新测试覆盖：

- 任意模型自由 ID 都被规范化成稳定服务端 ID。
- 相同 kind 的多个需求得到稳定序号且不冲突。
- 两个必需需求自动获得两跳预算。
- fallback 仍为单需求一跳。
- 只有 coverage 缺失时才执行第二跳。
- 第二跳只接收第一跳授权路由键。
- development gold 只使用规范化 ID。
- frozen 文件哈希与当前提交一致。
- 评测报告记录真实 commit、模型、策略、重复次数和语料快照。

最终验证命令包括全量 pytest、Ruff、前端测试、前端 lint、前端构建和 Docker development smoke。

## 9. 完成标准

项目二求职版只有同时满足以下条件才算完成：

- 稳定 need ID 契约有测试保护。
- 至少两个真实 development answer 场景证明补充检索有效，或有书面证据说明第一跳已自然完整覆盖并替换为合理场景。
- 三种策略完成 3 次固定条件 development 对比。
- 默认策略由聚合数据决定，不凭单次最好结果选择。
- 权限泄漏率保持 0，第二跳受限键测试通过。
- frozen holdout 只在定版后消费一次并提交原始报告。
- README、交接文档和面试指南与最终报告一致。
- `.env` 与百炼 API Key 未进入 Git。

完成本阶段后停止增加项目二功能，转入项目一文档、HTTPS 和评测口径优化。
