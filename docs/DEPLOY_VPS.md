# VPS deployment

The VPS deployment uses remote Qwen generation and remote embeddings. The
default `hybrid_rrf` strategy does not load the local reranker, so the server
only runs PostgreSQL, FastAPI, React, and Caddy.

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
migration, starts the API and Caddy, then verifies `/ready` on port `8010`.

## First smoke test

Open `http://<server-ip>:8010/` and verify:

1. A normal policy question returns a cited answer.
2. A restricted question is refused without revealing document content.
3. An evidence-insufficient question is refused.
4. The API is ready only after migrations and remote embedding indexing finish.
