# Supervised Enterprise Multi-Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the port-8010 application into an on-demand enterprise operations multi-agent assistant while preserving governed RAG and reusing the existing retail analytics runtime.

**Architecture:** Add a structured Supervisor and a bounded orchestration service in project two. Knowledge work stays in the existing RAG graph, data work crosses an authenticated internal HTTP boundary into project one, and general chat uses the configured OpenAI-compatible model. Deterministic review gates all enterprise results.

**Tech Stack:** Python 3.11, FastAPI, LangGraph, Pydantic, OpenAI-compatible API, PostgreSQL/pgvector, React, TypeScript, pytest, Docker Compose, GitHub Actions.

## Global Constraints

- Keep `8010` as the unified public entry point.
- Do not expose secrets, chain-of-thought, raw unauthorized evidence, or database credentials.
- Do not weaken existing RAG refusal, permission, version, citation, SQL safety, approval, or audit behavior.
- Keep public response additions backward compatible.
- Only report metrics produced by saved sample-level evaluation artifacts.

### Task 1: Define orchestration contracts and Supervisor

**Files:** `src/enterprise_knowledge_rag/agent_models.py`, `src/enterprise_knowledge_rag/supervisor.py`, `tests/test_supervisor.py`.

- [ ] Write routing and strict-model tests for general, knowledge, data and collaboration cases.
- [ ] Implement structured plans, deterministic fallback routing and bounded subtask contracts.
- [ ] Run focused tests and commit.

### Task 2: Add general and retail data adapters

**Files:** `src/enterprise_knowledge_rag/general_chat.py`, `src/enterprise_knowledge_rag/retail_agent.py`, `tests/test_agent_adapters.py`, project-one internal endpoint and tests.

- [ ] Test general answer boundaries, internal authentication, payload validation, timeout and degradation.
- [ ] Implement the general model adapter and authenticated project-one client/server contract.
- [ ] Run focused tests in both repositories and commit each repository independently.

### Task 3: Implement bounded multi-agent orchestration

**Files:** `src/enterprise_knowledge_rag/multi_agent.py`, `runtime.py`, `bootstrap.py`, `app.py`, `workflow.py`, corresponding tests.

- [ ] Test single-Agent routing, collaborative execution, partial failure and deterministic review.
- [ ] Implement Supervisor dispatch, parallel knowledge/data execution, synthesis and review.
- [ ] Expose backward-compatible result fields and public progress events.
- [ ] Run backend suites and commit.

### Task 4: Upgrade the unified frontend

**Files:** `frontend/src/types.ts`, `api.ts`, `App.tsx`, `components/ChatView.tsx`, `styles.css`, tests.

- [ ] Add tests for route badges, Agent task steps, tool results, data evidence and review status.
- [ ] Implement the enterprise operations assistant workspace with compact conditional details.
- [ ] Run frontend tests and production build, then commit.

### Task 5: Add reproducible multi-agent evaluation

**Files:** `evaluation/multi_agent_development.jsonl`, evaluation runner/script/tests, report documentation.

- [ ] Add versioned cases across six task classes with explicit expected routes and evidence.
- [ ] Implement sample-level and aggregate scoring with latency percentiles.
- [ ] Run deterministic and live development evaluations and save raw reports.
- [ ] Commit only measured claims.

### Task 6: Verify, document and deploy

**Files:** README, architecture, resume evidence, interview guide, environment and deployment files.

- [ ] Run all project-one and project-two tests, linters and frontend build.
- [ ] Update deployment configuration and secret names without committing values.
- [ ] Push both repositories, verify GitHub Actions, deploy, and test public health plus representative routes.
- [ ] Record deployed revisions, measured metrics, limitations and interview answers.
