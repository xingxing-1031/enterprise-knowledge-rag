FROM node:22-alpine AS frontend-builder

WORKDIR /workspace/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
RUN npm run build


FROM python:3.12-slim AS python-builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /workspace

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch>=2,<3" \
    && /opt/venv/bin/pip install --no-cache-dir ".[retrieval,models]"


FROM python:3.12-slim

ARG DEBIAN_MIRROR=http://deb.debian.org/debian
ARG DEBIAN_SECURITY_MIRROR=http://deb.debian.org/debian-security

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY --from=python-builder /opt/venv /opt/venv
RUN sed -i \
        "s|http://deb.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g; s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g" \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install --yes --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

COPY --chown=appuser:appuser src ./src
COPY --chown=appuser:appuser db ./db
COPY --chown=appuser:appuser knowledge ./knowledge
COPY --chown=appuser:appuser evaluation ./evaluation
COPY --chown=appuser:appuser scripts ./scripts
COPY --chown=appuser:appuser --from=frontend-builder /workspace/frontend/dist ./frontend/dist
RUN install -d -o appuser -g appuser \
    /app/data/uploads \
    /home/appuser/.cache/huggingface

USER appuser

EXPOSE 8010

CMD ["uvicorn", "enterprise_knowledge_rag.main:app", "--host", "0.0.0.0", "--port", "8010"]
