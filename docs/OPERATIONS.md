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
- `DEMO_ROLE` / `DEMO_DEPARTMENTS`：服务器注入的演示身份，客户端不能覆盖。

## 3. Docker Compose 启动

```powershell
docker compose up -d --build --wait
```

启动顺序固定为：

```text
PostgreSQL 健康 -> migrate 完成 -> index 完成 -> API /ready 通过
```

打开 `http://127.0.0.1:8010/`。前端与 API 同源，不需要额外启动 Vite。

镜像显式安装 CPU 版 Torch，避免把 GPU 运行库带入演示镜像。首次索引会下载 bge-m3，首次问答会加载 bge-reranker-v2-m3；耗时取决于网络和机器配置，模型缓存保存在 `model_cache` 数据卷中。建议为双模型本地运行准备至少 8 GB 内存，资源不足时应改用远程模型服务，而不是忽略内存边界。后续内容和向量模型均未变化的文档会跳过；更换 `EMBEDDING_MODEL` 会触发重建。

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
- `/ready`：数据库表存在、知识文档非空，并且每份文档都有当前 `EMBEDDING_MODEL` 的向量片段。

因此 PostgreSQL 只完成端口监听时，API 仍不会被标记为业务就绪。

## 6. CI 中的确定性测试向量

GitHub Actions 在空数据卷验证迁移、全量语料索引、pgvector 检索和 `/ready`。为了不在每次基础设施测试中下载大型模型，只有 `APP_ENV=ci` 且 `DETERMINISTIC_TEST_EMBEDDINGS=true` 时才允许使用确定性测试向量。

该模式只能证明数据库和索引链路可运行，不能用于 RAG 效果评测，也不能写成 bge-m3 的准确率。真实检索质量必须使用 bge-m3、Reranker 和受控数据集另行评测。

## 7. 验证命令

```powershell
python -m pytest
ruff check src tests scripts
npm --prefix frontend run test
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

浏览器检查覆盖 360、390 和 1440 像素宽度，并断言页面没有横向溢出。

## 8. 清理与数据保护

普通停止不会删除数据：

```powershell
docker compose down
```

下面的命令会永久删除本项目 PostgreSQL 数据和模型缓存，只允许在明确需要空卷重验时执行：

```powershell
docker compose down --volumes
```

不要在包含需要保留数据的环境中运行该命令。
