# VPS deployment

The VPS deployment uses remote Qwen generation, remote embeddings
(`text-embedding-v3`), and a remote reranker (`qwen3-rerank`) over the
DashScope OpenAI-compatible endpoints, so every feature behaves as in local
development. The default retrieval strategy is `hybrid_rrf_reranker`. The
server only runs PostgreSQL, FastAPI, React, and Caddy — no local models are
loaded.

The deployment is isolated from the retail project:

- Compose project: `enterprise-knowledge-rag-vps`
- Database and upload volumes: `enterprise_rag_vps_*`
- Public demo port: `8010` by default
- Public data: synthetic knowledge only

## Server preparation

Clone the repository to `/home/ubuntu/enterprise-knowledge-rag`, copy
`.env.vps.example` to `.env.vps`, and fill in the database password, Qwen
endpoint, embedding endpoint, model names, and server-side API keys. Do not
commit `.env.vps`.

The embedding model must return vectors matching `EMBEDDING_DIMENSION`. If the
provider uses a different dimension, update the setting and rebuild the empty
database index before serving traffic.

## GitHub Actions

Create a `production` environment in the repository and add these secrets:

- `VPS_HOST`
- `VPS_USER`
- `VPS_SSH_PRIVATE_KEY`
- `VPS_KNOWN_HOSTS`

The workflow is manual and deploys the selected branch or commit. It runs the
migration, rebuilds the vector index with the remote embedding model, then
starts the API and Caddy and verifies `/ready` on port `8010`. The first
index on a fresh volume calls the remote embedding API for every chunk.

## First smoke test

Open `http://<server-ip>:8010/` and verify:

1. A normal policy question returns a cited answer.
2. A restricted question is refused without revealing document content.
3. An evidence-insufficient question is refused.
4. The API is ready only after migrations and remote embedding indexing finish.
