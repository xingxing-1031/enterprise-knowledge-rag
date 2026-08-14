# 运行与交付手册

## 1. 交付边界

本项目是使用合成制度语料的个人演示系统。Docker、连接池、迁移、索引、健康检查和 CI 用于证明可重复交付，不代表已经具备多租户、SSO、高可用、备份恢复和生产监控。

## 2. 配置

复制 `.env.example` 为 `.env`，再填写实际模型地址和密钥。密钥只放在本地或部署平台的环境变量中，不提交到 Git。

关键配置：

- `DATABASE_URL`：PostgreSQL 连接串。
- `DATABASE_POOL_MIN_SIZE` / `DATABASE_POOL_MAX_SIZE`：API 连接池上下限。
- `EMBEDDING_MODEL`：写入和读取向量时共同使用的模型标识。
- `MODEL_BASE_URL` / `MODEL_NAME` / `MODEL_API_KEY`：OpenAI 兼容的 Qwen 服务。
- `AUTH_KNOWLEDGE_ADMIN_USERNAME` / `AUTH_KNOWLEDGE_ADMIN_PASSWORD_HASH`：唯一网页登录管理员身份。
- `AUTH_SESSION_SECRET`：签名 HttpOnly 会话密钥。
- `ADMIN_AUDIT_SECRET`：文档引用 HMAC 密钥，不能与会话密钥复用。
- `UPLOAD_STORAGE_DIR` / `UPLOAD_MAX_BYTES` / `PDF_MAX_PAGES`：上传目录、15 MiB 文件上限和 200 页 PDF 上限。
- `DOCUMENT_ROUTE_LIMIT`：单次父文档路由上限，默认 4。
- `EVIDENCE_MAX_ITEMS` / `EVIDENCE_MAX_TOKENS`：最终证据条数和近似 token 预算，默认 6 / 1200。

### 安全导入流程

只有服务端解析出的 `knowledge_admin` 身份可以上传和确认。上传后依次执行格式签名校验、解析、确定性清洗和预览；管理员确认部门、可见性、角色、版本及生效时间后才允许索引。原文件保存在独立 `enterprise_rag_uploads` 数据卷，API 以非 root 用户写入。隔离状态不能被确认，也不会产生父文档或章节向量。

## 3. Docker Compose 启动

```powershell
docker compose up -d --build --wait
```

启动顺序固定为：

```text
PostgreSQL 健康 -> migrate 完成 -> index 完成 -> API /ready 通过
```

打开 `http://127.0.0.1:8010/`。前端与 API 同源，不需要额外启动 Vite。网页只接受知识库管理员登录；项目一通过 `/internal/evidence` 获取普通员工可见证据。

镜像显式安装 CPU 版 Torch，避免把 GPU 运行库带入演示镜像。首次索引会下载 bge-m3，首次问答会加载 bge-reranker-v2-m3；耗时取决于网络和机器配置，模型缓存保存在 `model_cache` 数据卷中。建议为双模型本地运行准备至少 8 GB 内存，资源不足时应改用远程模型服务，而不是忽略内存边界。后续内容和向量模型均未变化的文档会跳过；更换 `EMBEDDING_MODEL` 会触发重建。

如果构建时访问 `deb.debian.org` 返回 502，可在本地 `.env` 覆盖 Debian 镜像，不要修改并提交全局默认值。例如：

```dotenv
DEBIAN_MIRROR=https://mirrors.aliyun.com/debian
DEBIAN_SECURITY_MIRROR=https://mirrors.aliyun.com/debian-security
```

## 4. 单独执行迁移和索引

本机虚拟环境：

```powershell
python scripts/migrate.py
python scripts/index_knowledge.py
```

容器环境：

```powershell
docker compose run --rm migrate
docker compose run --rm index
```

迁移记录在 `schema_migrations`。已执行文件的 SHA-256 校验和发生变化时命令会失败，应该新增迁移文件，不能篡改历史迁移。

## 5. 健康检查

- `/health`：进程可以响应。
- `/ready`：数据库表存在、知识文档非空，并且每份文档都有当前 `EMBEDDING_MODEL` 的父文档向量和章节向量。

因此 PostgreSQL 只完成端口监听时，API 仍不会被标记为业务就绪。

## 6. 管理控制台操作

- **文档库**：按标题、编号和状态筛选，查看来源文件、权限和切片数量。
- **生命周期**：停用版本立即从生效版本解析中排除；恢复后重新可检索；重建索引只允许受控目录中的源文件。
- **永久删除**：必须输入完整标题确认，级联删除源文件、文档、切片和向量；审计只保留 HMAC 文档引用，不保存正文或路径。
- **检索实验室**：管理员可模拟普通员工、部门管理员或管理员，结果只返回安全元数据和分数，不返回隐藏切片正文。
- **导入审核**：上传文件先解析、清洗和预览，确认元数据后才建立索引。

## 7. CI 中的确定性测试向量

GitHub Actions 在空数据卷验证 004 迁移、全量合成语料索引、父文档路由、受路由文档约束的章节检索和 `/ready`。为了不在每次基础设施测试中下载大型模型，只有 `APP_ENV=ci` 且 `DETERMINISTIC_TEST_EMBEDDINGS=true` 时才允许使用确定性测试向量。

该模式只能证明数据库和索引链路可运行，不能用于 RAG 效果评测，也不能写成 bge-m3 的准确率。真实检索质量必须使用 bge-m3、Reranker 和受控数据集另行评测。

## 8. 验证命令

```powershell
python -m pytest
ruff check src tests scripts
npm --prefix frontend run test
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

浏览器检查覆盖 360、390 和 1440 像素宽度，并断言页面没有横向溢出。

`/ready` 同时要求每份文档存在当前 Embedding 模型的父文档向量和章节向量。CI 的空卷 smoke 还会执行一次父文档路由，再将路由键显式转发给章节检索。

## 9. 清理与数据保护

普通停止不会删除数据：

```powershell
docker compose down
```

下面的命令会永久删除本项目 PostgreSQL 数据和模型缓存，只允许在明确需要空卷重验时执行：

```powershell
docker compose down --volumes
```

不要在包含需要保留数据的环境中运行该命令。
