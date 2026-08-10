# W7-2：干净环境交付

## 本阶段目标

让企业知识助手能够从空 PostgreSQL 数据卷按固定顺序完成迁移、索引和 API 启动，并通过本地测试与 GitHub Actions 重复验证。

## 业务问题

“代码在开发机能跑”不能证明别人拉取后也能运行。数据库端口可连接也不代表制度表、语料快照和当前向量模型已经准备完成；直接依赖 PostgreSQL 的一次性初始化目录，也无法安全处理后续版本升级。

## 我的实现

FastAPI 使用 psycopg 连接池，并由应用生命周期统一打开和关闭。迁移命令按文件名顺序执行，把版本和 SHA-256 校验和写入 `schema_migrations`；历史迁移被修改时拒绝继续。索引命令复用已有标题切分、内容哈希和增量写入逻辑。

Docker Compose 把启动顺序定义为 PostgreSQL、迁移、索引、API。React 先构建为静态产物，再由 FastAPI 同源托管。`/ready` 不只检查连接，还要求每份知识文档都存在当前 Embedding 模型的片段。

CI 分开验证 Python 3.11/3.12、Ruff、前端单元测试、类型检查、构建、依赖审计、三种视口和空卷 pgvector。基础设施 smoke 使用明确受限于 `APP_ENV=ci` 的确定性测试向量，不冒充真实 bge-m3 效果。

## 验证结果

- Python 全量回归：`107 passed, 1 skipped`；跳过项是当前机器没有 Docker 时不能执行的真实 pgvector 往返测试。
- Ruff：`src`、`tests`、`scripts` 全部通过。
- 前端：`3 passed`，TypeScript 检查和 Vite 生产构建通过，依赖审计为 `0 vulnerabilities`。
- 360、390、1440 三种视口的页面断言均通过且无横向溢出；当前 Windows 环境的 Playwright 在断言完成后的进程清理阶段超时，仍需由 Linux CI 给出最终任务退出状态。
- Docker/pgvector 空卷：当前 Codex 环境未安装 Docker，配置已进入 CI，不能在本地宣称容器验收通过。

## 遇到的问题与取舍

真实 bge 模型体积较大，若每次 CI 都下载，基础设施反馈会很慢。我没有把测试向量当作检索质量结果，而是把它限制为 CI 专用，只验证迁移、索引持久化、向量查询和就绪门槛。模型质量仍由后续固定 bge/Reranker/LLM 的 development 与 frozen holdout 评测负责。

## 我能口述的标准答案

镜像负责打包代码和依赖，容器是运行实例，数据卷保存数据库与模型缓存，Compose 定义它们的依赖顺序。我的 `/health` 只表示进程活着，`/ready` 还会检查表、文档和当前模型的完整索引。迁移是可追踪的增量升级，知识索引依据内容哈希跳过未变化文档，两者职责不同。

## 面试追问

- 为什么不能继续依赖 `/docker-entrypoint-initdb.d` 做所有升级？
- 为什么连接池必须由 FastAPI 生命周期管理？
- `/health` 和 `/ready` 的语义为什么要分开？
- CI 测试向量能证明什么，不能证明什么？
- 为什么迁移文件执行后不能直接修改？

## 下一步

在可运行 Docker 的 GitHub Actions 或服务器完成空卷验收，再接入真实 bge-m3、Reranker 和 Qwen 跑 development 对比；代码和配置冻结后，最后一次运行 frozen holdout。
