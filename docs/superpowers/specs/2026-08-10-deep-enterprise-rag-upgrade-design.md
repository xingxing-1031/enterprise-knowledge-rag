# 企业文档深度 RAG 升级设计

> 日期：2026-08-10
> 状态：已确认，待实施
> 适用项目：`enterprise-knowledge-rag`

## 1. 背景与目标

当前项目已经具备版本化 Markdown 语料、标题感知切分、PostgreSQL/pgvector、权限与版本预过滤、BM25/向量/RRF/Reranker、最小证据、引用校验、拒答、LangGraph、FastAPI/SSE 和受控评测。

现有不足是：文档只能由开发者预先整理成 Markdown；查询改写仍为原样返回；检索是一次性平面 chunk 检索；跨文档或跨章节问题没有明确的证据需求、补召回和覆盖判定。因此，仅用“向量、混合检索、重排”描述时，会与项目一的评测方案产生表面重复，也不足以证明企业 RAG 深度。

本轮升级目标是建立一条可解释、可测试的企业文档闭环：

```text
企业文件
-> 解析与清洗
-> 人工元数据确认
-> 分层索引
-> 结构化检索计划
-> 文档级路由
-> 章节级召回
-> 最多两跳的证据补全
-> 多文档证据合并
-> 逐主张引用校验
-> 回答、降级或拒答
```

项目仍使用明确标记的合成企业语料，不冒充真实企业数据、客户或生产上线效果。

## 2. 设计原则

1. **召回的是候选证据，不是答案。** 每个候选必须携带文档、章节、版本、权限和命中通道。
2. **模型不决定安全边界。** 身份、部门、权限、查询时间、版本有效性和发布状态由服务端规则处理。
3. **检索计划受结构约束。** 模型只能生成有限枚举和查询文本，失败时走确定性回退，不能自由扩展工具或循环。
4. **最多两跳。** 第二跳只由未覆盖的证据需求触发，避免无限 Agentic Search。
5. **证据必须完整。** 可回答问题的每项必要事实都必须有证据支持；缺少关键证据时拒答。
6. **文档先预览再发布。** 文件解析成功不等于可以进入知识库，管理员必须确认业务元数据和清洗结果。
7. **评测分阶段。** 文档解析、路由、召回、补召回、证据覆盖、引用和最终回答分别评测。

## 3. 范围

### 3.1 本轮包含

- 文本型 PDF、Word `.docx`、Markdown 和 TXT 导入。
- 文件类型、大小、页数和基础结构校验。
- 页眉页脚、页码、空白、重复段落和不可见控制字符清理。
- Word 标题、段落、列表和普通表格保留。
- PDF 页面文本和段落提取；复杂表格无法稳定恢复时产生人工复核告警。
- 扫描版 PDF 识别并进入待人工处理状态，不写入向量索引。
- 管理员填写或确认标题、部门、密级、角色、版本、生效时间和状态。
- 原始文件哈希去重、规范化文本、解析报告和索引状态记录。
- 父文档与子章节的分层检索。
- 结构化检索计划、证据需求拆解和最多两跳的定向补召回。
- 多文档证据合并、需求覆盖判定、引用完整性校验和安全 Trace。
- 管理端文档导入、预览、确认和状态展示。
- development 数据集增加跨章节、跨文档和解析质量场景。

### 3.2 本轮不包含

- OCR 和扫描件文字识别。
- 复杂 PDF 表格、公式、图片和多模态理解。
- Neo4j、GraphRAG 或自动构建知识图谱。
- HyDE、无限查询扩展、自我反思循环或多 Agent 检索。
- 模型微调、GRPO 或使用无法复现的训练效果数字。
- 多租户对象存储、杀毒引擎和正式 DLP/PII 系统。
- frozen holdout 执行。

这些能力只能在后续评测证明存在对应问题时再引入。

## 4. 文档入库设计

### 4.1 文件安全边界

- 允许扩展名：`.pdf`、`.docx`、`.md`、`.txt`。
- 单文件最大 15 MiB。
- PDF 最大 200 页。
- 同时校验扩展名、MIME 和文件签名；不执行宏、脚本、嵌入对象或外部链接。
- 上传文件名只作展示，服务端使用随机稳定 ID 保存，禁止路径穿越。
- 原始文件保存在 `UPLOAD_STORAGE_DIR`，目录不进入 Git。
- 相同 SHA-256 原始文件默认拒绝重复导入；新版本必须显式提供新的版本号或替换关系。

### 4.2 解析适配器

统一接口：

```python
class SourceExtractor(Protocol):
    def supports(self, media_type: str, suffix: str) -> bool: ...
    def extract(self, source: SourceFile) -> ExtractedDocument: ...
```

适配器职责：

- `MarkdownExtractor`：保留现有 front matter 与 Markdown 结构。
- `TextExtractor`：UTF-8/常见中文编码检测，输出普通段落。
- `DocxExtractor`：使用 `python-docx` 提取标题、段落、列表和表格，表格规范化为 Markdown。
- `PdfExtractor`：使用 `pypdf` 提取页面文本，记录页码和文本密度；文本密度过低时判断为扫描件或不可解析文件。

解析器不自动决定部门、权限、版本和生效时间。

### 4.3 规范化与清洗

清洗步骤固定且可审计：

1. Unicode 和换行规范化。
2. 删除不可见控制字符，保留正常中文、英文和业务符号。
3. 合并无意义连续空白，不合并表格和列表内部结构。
4. 检测在多页重复出现的短页眉、页脚和纯页码。
5. 对完全相同的连续段落去重；跨章节重复只告警，不自动删除。
6. 恢复标题栈并生成规范化 Markdown。
7. 生成清洗前后字符数、段落数、表格数、告警和内容哈希。

清洗报告必须区分：

- `info`：正常清洗记录。
- `warning`：需要管理员核对但允许预览。
- `blocking`：扫描件、空文档、损坏文件、超限文件或无法识别格式，禁止发布。

文档中的“忽略系统指令”“泄露其他文档”等提示词样式文本只标记为内容注入告警。生成模型始终把知识文本视为数据，不能执行文档中的指令；该启发式告警不宣称是完整安全边界。

### 4.4 人工确认与状态机

入库任务状态：

```text
uploaded
-> parsed
-> needs_review
-> approved
-> indexed
```

失败分支：

```text
uploaded/parsed -> quarantined
approved/indexed -> failed
```

管理员在 `needs_review` 阶段确认：

- 标题和文档类型。
- 部门与可见性。
- 允许角色。
- 版本、替代关系、生效和失效时间。
- 清洗后的章节预览与所有告警。

客户端不能自行伪造管理员角色；仍使用服务端可信身份。只有 `approved` 文档可以建立索引，只有 `active` 且在查询时间生效的版本可以被检索。

## 5. 分层索引与检索

### 5.1 父文档索引

每个文档版本生成确定性的 `document_search_text`：

```text
标题 + 文档类型 + 部门 + 顶级章节标题 + 管理员确认的主题标签
```

为父文档保存独立 Embedding。父文档索引只用于路由，不直接作为回答证据。

### 5.2 子章节索引

沿用现有标题感知切分；每个子 chunk 继续保存：

- `chunk_id`
- `document_id` / `document_version`
- `section_path`
- 正文、内容哈希和 token 数
- Embedding 模型版本

子章节召回只在已经通过权限、版本和父文档路由的文档集合中进行。

### 5.3 分层查询流程

```text
授权且生效的文档集合
-> 父文档 BM25 + 向量路由
-> RRF 选出最多 4 个文档版本
-> 在这些文档内执行章节 BM25 + 向量召回
-> RRF + Cross-Encoder Reranker
-> 证据候选
```

原有三方案继续保留为评测对照，但线上默认方案升级为分层混合检索。父文档路由结果、子章节召回结果和最终证据必须分开记录，不能把它们压成一个无法诊断的总分。

## 6. 结构化检索计划

新增严格 Pydantic 模型：

```python
class EvidenceKind(StrEnum):
    RULE = "rule"
    PROCEDURE = "procedure"
    MATERIAL = "material"
    EXCEPTION = "exception"
    APPROVER = "approver"
    DEADLINE = "deadline"
    SCOPE = "scope"

class EvidenceNeed(StrictModel):
    need_id: str
    kind: EvidenceKind
    query: str
    required: bool = True

class RetrievalPlan(StrictModel):
    primary_query: str
    topic: str
    departments: set[str]
    evidence_needs: list[EvidenceNeed]
    requires_multi_hop: bool
    max_hops: Literal[1, 2]
```

约束：

- 最多 4 个 `evidence_needs`。
- `max_hops` 只能是 1 或 2。
- 部门只用于缩小候选，不能扩大用户已有权限。
- 请求中的可信 `as_of` 和显式版本条件不允许被模型覆盖。
- 结构化计划生成失败时，回退为一个 `RULE` 需求和单跳原问题检索；记录 `plan_degraded`。

示例：

```json
{
  "primary_query": "病假超过两天需要什么材料，紧急就医怎么办",
  "topic": "病假",
  "departments": ["hr"],
  "evidence_needs": [
    {"need_id": "materials", "kind": "material", "query": "病假超过两天材料要求"},
    {"need_id": "emergency", "kind": "exception", "query": "紧急就医补交材料例外"}
  ],
  "requires_multi_hop": true,
  "max_hops": 2
}
```

## 7. 两跳证据补全

### 7.1 第一跳

第一跳使用 `primary_query` 完成父文档路由，再对每个 `EvidenceNeed.query` 执行子章节检索。候选通过 Reranker 后，按 `need_id` 建立证据覆盖关系。

### 7.2 证据缺口判定

`EvidenceCoverageService` 只判断证据需求是否被候选覆盖，不生成答案。覆盖判定依据：

- 候选来自授权且生效的文档版本。
- Reranker 分数达到配置阈值。
- 章节标题和正文与 `EvidenceKind`、需求查询存在足够匹配。
- 同一候选可支持多个需求，但每个必需需求必须至少有一个支持候选。

### 7.3 第二跳

仅当存在未覆盖的必需需求且 `max_hops == 2` 时执行。第二跳查询由以下确定性内容组成：

```text
原主题 + 未覆盖需求类型 + 未覆盖需求查询 + 第一跳已确认的文档标题
```

第二跳仍重复权限、版本和发布状态过滤，不能继承未经验证的隐藏候选。第二跳结束后仍缺少必需证据则返回 `insufficient_evidence`，不能让生成模型补全。

### 7.4 合并与预算

- 按稳定 `chunk_id` 和内容哈希去重。
- 不允许同一文档的冲突版本同时进入证据集。
- 先保证必需需求各有一条证据，再分配剩余 token 预算。
- 证据记录新增 `supports_need_ids` 与 `retrieval_hop`。
- 默认最多 6 条证据、总预算 1200 近似 token。

## 8. 回答与引用完整性

生成提示中包含检索计划、证据需求和对应证据。模型输出继续使用结构化 claims/citations。

除现有引用存在性和关键数字校验外，新增：

- 每个必需 `need_id` 必须被至少一条 claim 覆盖。
- 每条 claim 只能引用本次证据集合。
- 多文档回答需要分别引用支持对应结论的文档，不能用一条引用覆盖全部结论。
- 引用完整性失败时允许一次重生成。
- 再次失败但证据完整时，降级返回按证据需求分组的事实摘要。
- 证据本身不完整时拒答，不能降级为自由回答。

## 9. API 与前端

### 9.1 管理接口

- `POST /knowledge/imports`：管理员上传文件和基础元数据，返回导入任务 ID。
- `GET /knowledge/imports/{import_id}`：查看解析状态、清洗报告和规范化预览。
- `POST /knowledge/imports/{import_id}/approve`：管理员确认完整元数据并触发索引。
- `GET /knowledge/imports`：查看任务列表和状态。

文件上传和元数据校验失败返回稳定中文错误；管理员 Trace 保留英文错误类型，不返回供应商原始异常或文件系统路径。

### 9.2 知识库管理页面

在现有知识库页面增加：

- 文件上传入口。
- 元数据表单。
- 规范化文档预览。
- 清洗统计和告警。
- 批准入库、隔离和失败状态。

### 9.3 问答过程展示

普通用户只看到中文安全阶段：

```text
理解问题
-> 定位相关制度
-> 检索具体章节
-> 补充缺失依据（仅在触发时）
-> 核对引用
-> 生成回答
```

管理员可以查看：检索计划、父文档 ID、证据需求、hop、命中通道、候选数量和耗时。不能显示被权限过滤文档的标题、正文或相似度。

## 10. Trace 与审计

Trace 新增组件：

- `ingest_detect`
- `ingest_extract`
- `ingest_clean`
- `ingest_review`
- `retrieval_plan`
- `document_route`
- `section_retrieve`
- `evidence_coverage`
- `supplemental_retrieve`
- `citation_validate`

Trace 记录系统运行位置、状态、耗时、数量和稳定错误类型。审计日志记录管理员上传、确认、拒绝和重新索引行为。两者职责保持分离。

## 11. 数据库变化

新增迁移，不修改历史迁移：

### `knowledge_imports`

- 导入任务 ID、原始文件哈希、原始文件名、安全存储路径。
- MIME、文件类型、大小、页数。
- 状态、清洗报告、规范化预览路径。
- 上传人、确认人和时间。
- 失败类型，不保存敏感原始异常。

### `knowledge_documents`

新增：

- `document_search_text`
- `document_embedding`
- `document_embedding_model`
- 可选主题标签

### `knowledge_chunks`

无需把 `supports_need_ids` 和 `retrieval_hop` 持久化；它们属于单次请求证据状态。

## 12. 评测设计

### 12.1 文档处理指标

- 文件解析成功率。
- 阻断文件识别准确率。
- 标题、段落和 Word 表格保留率。
- 重复页眉页脚移除准确率。
- 不应删除正文的误清洗率。
- 增量导入跳过率和重复文件识别率。

### 12.2 检索指标

- 文档路由 Recall@K。
- 章节 Recall@K、MRR 和 nDCG。
- 证据需求识别准确率。
- 必需需求覆盖率。
- 第二跳触发准确率。
- 第二跳补证据成功率。
- 无关证据比例。
- 权限泄漏率，必须为 0。
- 版本选择准确率。

### 12.3 回答指标

- 引用准确率。
- 引用完整性。
- 正确拒答率和错误拒答率。
- 必需事实覆盖率。
- P50/P95 延迟、检索跳数和模型调用次数。

评测仍保留确定性 gold 评分器作为主依据；可选 LLM Judge 只能评价语言完整性，必须记录模型、提示词和重复次数，不能替代 gold 证据、权限和版本评分。

development 至少新增：

1. 同一制度跨章节的材料 + 例外问题。
2. 跨制度的规则 + 办理流程问题。
3. 第一跳足够、不应触发第二跳的问题。
4. 第二跳后仍缺证据、必须拒答的问题。
5. 第二跳可能命中受限文档但必须保持零泄漏的问题。

frozen holdout 保持锁定，不在本轮开发过程中运行。

## 13. 错误与降级

| 场景 | 处理 |
| --- | --- |
| 不支持的文件、文件超限、损坏文件 | 拒绝导入，记录稳定错误类型 |
| 扫描版 PDF 或文本密度过低 | 隔离为 `quarantined`，提示需要 OCR/人工处理 |
| 文档清洗存在非阻断告警 | 进入 `needs_review`，禁止自动发布 |
| 结构化检索计划失败 | 单需求、单跳原问题检索，记录 `plan_degraded` |
| 父文档路由为空 | `insufficient_evidence` |
| 第二跳后必需需求仍未覆盖 | `insufficient_evidence` |
| 命中但无权访问 | `permission_denied`，不泄露文档信息 |
| 引用校验失败但证据完整 | 一次重生成，之后返回证据分组降级摘要 |
| 数据库或模型服务失败 | `service_failed`，不伪装成业务拒答 |

## 14. 测试边界

主要公共测试接口：

- `SourceExtractor.extract()`：格式解析和阻断判定。
- `DocumentCleaningService.clean()`：规范化文本与清洗报告。
- `IngestionService.preview()/approve()`：状态机、权限和幂等。
- `RetrievalPlanner.plan()`：结构化证据需求和回退。
- `HierarchicalRetrievalService.retrieve()`：父文档路由和章节召回。
- `EvidenceCoverageService.cover()`：需求覆盖和第二跳触发。
- `run_chat()`：成功、多跳、拒答、权限和降级端到端行为。

测试必须验证：

- 第二跳不会绕过第一跳相同的权限和版本过滤。
- Reranker 不会引入未召回 chunk。
- 扫描件、空文档和损坏文件不会写入索引。
- 上传重试和批准重试不会重复建立索引。
- 多跳 Trace 不包含隐藏文档内容和模型推理过程。
- 旧的单跳问题与 111 项 Python 基线测试不回归。

## 15. 验收标准

1. 文本型 PDF、DOCX、Markdown 和 TXT 均能进入预览；扫描件被可靠隔离。
2. 管理员未确认的文档不能被索引或检索。
3. 父文档路由与章节召回可以独立观测和评分。
4. 至少两个 development 场景真实触发第二跳并返回多个正确引用。
5. 单跳可回答问题不发生无意义第二跳。
6. 证据不完整、版本冲突和权限不足时按正确原因拒答。
7. 权限泄漏自动化测试为 0。
8. 全量 Python、前端、类型检查、构建和 CI 交付检查通过。
9. 真实模型和数据库评测完成前，不填写准确率和提升比例。
10. frozen holdout 只在系统配置最终冻结后运行一次。

## 16. 面试叙述边界

可以陈述：

- 亲自实现了文档适配、清洗报告、人工确认、分层索引、结构化检索计划和两跳证据补全。
- 能解释召回对象、父子检索、证据需求、第二跳触发和引用完整性。
- 使用合成企业制度和受控评测验证工程行为。

不能陈述：

- 使用了真实企业内部数据或服务真实客户。
- 已达到生产级 OCR、GraphRAG、多租户或高并发 SLA。
- 未经报告验证的准确率、提升比例、语料规模或用户数量。

