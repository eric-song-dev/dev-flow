# AI Engineering Copilot

**An AI engineering copilot for GitHub repositories.** It syncs a repository's issues, pull requests, CI runs, and source code, then answers engineering questions with a tool-calling agent, hybrid RAG, and a multi-agent review workflow. Any action that would write to GitHub is returned as a draft that a human must approve.

```text
$ curl -N localhost:8000/api/chat/stream -H 'Content-Type: application/json' \
    -d '{"repo_id": "<uuid>", "message": "Can the latest PR be merged?"}'
event: tool_use      workflow.run_engineering_review
event: tool_result   success · multi-agent decision memo
event: thought       CI gate is failing; checking whether the PR touches the failing job ...
event: tool_use      workspace.read_file {"path": ".github/workflows/ci.yml"}
event: delta         "Hold the merge: the latest CI run is failing on ..."
event: final         {completion: completed, tool_calls: [...], citations: [...]}
                     (abridged, illustrative)
```

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [Benchmarks](#benchmarks)
- [Roadmap](#roadmap)
- [Contributing](#contributing)

## Overview

Engineering questions rarely live in one place. "Can we merge this?" depends on the diff, open review comments, the latest CI failure, related issues, and decisions recorded months ago. AI Engineering Copilot brings those sources together:

- **Ask**: a LangGraph tool-calling agent chooses among 14 tools, including workspace code search, hybrid RAG, MCP memory, issue/PR/CI agents, reports, safety review, and the multi-agent workflow.
- **Decide**: cross-domain questions go to a Planner → specialist agents → Observer → Synthesis workflow that runs independent agents in parallel and flags conflicts before answering.
- **Act safely**: comments, labels, and issue closures become `ActionDraft`s that require explicit, RBAC-gated human approval, and every approval is audit-logged.
- **Measure**: a RAGAS harness replays the production agent, and a retrieval benchmark tracks Recall@K and MRR.

Results on a real repository (`pydantic/pydantic-extra-types`, 415 issues and PRs); see [Benchmarks](#benchmarks) for methodology.

| Metric | Result |
| --- | --- |
| Multi-agent workflow latency, parallel vs. sequential | **−39%** (87 s → 53 s median) |
| Hybrid retrieval vs. BM25, 160 labeled queries | Recall@5 **0.89 → 0.97**, MRR **0.82 → 0.91** |
| Query-aware context compression | **−67%** retrieved-context tokens |
| Agent tool routing, 20 scenarios | **90%** correct tool |
| Prompt-cache hit rate | **83%** of 2.67M input tokens |
| First live SSE tool event | **2.8 s** median (vs. 53 s full completion) |

## Features

### Agents

- **Tool-calling ChatAgent** built on a LangGraph `StateGraph`, using native tool calls within a 12-step budget.
  - A loop guard stops the run when the same tool call is repeated with the same arguments.
  - Tool errors are classified, and retryable ones (timeouts, rate limits, transient network failures) are retried once.
  - A context-overflow error triggers one retry with a more aggressively compacted context.
- **Multi-agent engineering review.** A `PlannerAgent` builds a `WorkflowSpec` of scoped tasks and their dependencies; the orchestrator runs ready tasks in parallel (up to 3 at a time by default) with per-task timeouts.
  - An `ObserverAgent` flags merge gates, cross-agent conflicts, evidence gaps, and low confidence, and can trigger a bounded replan.
  - A `SynthesisAgent` writes a decision memo covering What / Why / Tradeoff / Open Questions / Next Action.
- **Specialist agents** for issue triage, PR review (P1/P2/P3 findings), CI failure debugging, weekly reports, and safety review. The issue, PR, and CI agents merge the LLM's JSON output with a deterministic fallback and validate the result against Pydantic schemas.
- **Skill runtime** with six `SKILL.md` skills. Full instructions load on demand, an explicitly requested skill limits which tools may run, and every activation is traced.
- **MCP memory server** (stdio JSON-RPC) that exposes thread transcripts, sealed sessions, and evidence search.

### Retrieval & context

- **Hybrid RAG** combines field-weighted BM25 with Milvus vector search on Qwen3 embeddings, then applies these stages:
  1. Weighted score fusion.
  2. Near-duplicate removal (SHA-256 fingerprint, plus Jaccard ≥ 0.9).
  3. A cap of 2 chunks per parent document.
  4. Reranking.
  5. Parent-context expansion or query-aware extractive compression.
- **Source policy.** Only reusable unstructured knowledge is embedded: issue and PR text, failed CI logs, docs, uploads, and approved memory. Current code is searched live (ripgrep), and structured facts are queried from the database.
- **Knowledge base studio.** Upload TXT, Markdown, PDF, DOCX, JSON, CSV, or log files. Files are chunked along their structure, duplicate uploads are skipped, and a retrieval test bench lets you check results per query.
- **Context engineering.**
  - Token budgets per section (system, memory, evidence, recent turns, tool output).
  - Microcompaction of old tool output.
  - LLM compaction summaries with a key-fact preservation check and a circuit breaker.
  - Session sealing into long-term memory.
  - A stable prompt prefix and a prompt-cache key for provider-side caching.
- **Secret redaction** of CI logs (tokens, keys, JWTs, private keys) before indexing.

### GitHub & platform

- Connect a GitHub (or GitHub-compatible) repository, or a local checkout.
- Sync issues, PRs (with files and review comments), and workflow runs (with jobs and failure logs). Sync is paginated and idempotent, and it reports a status for each source: `completed`, `partial`, `empty`, `failed`, or `skipped`.
- HMAC-verified GitHub webhooks and periodic auto-sync.
- RBAC roles (owner / maintainer / developer / viewer), audit logs, and Fernet-encrypted repository tokens.
- PR worktree snapshots, a code graph (symbols and relations), and a cross-entity knowledge graph.
- Answer feedback (👍/👎) with an optional Feishu webhook notification.

### Evaluation

- **RAGAS 0.4 harness** that runs the production ChatAgent in rollback-isolated sessions.
  - Scores Context Precision/Recall, Faithfulness, Answer Relevancy, and Agent Goal Accuracy, alongside hard rule gates.
  - Re-scores only the judge metrics that failed, without rerunning the agent.
  - Compares two runs to catch regressions.
  - Turns failed cases into issue drafts.

### Frontend

- Next.js 15 / React 19 console with 15 pages, including dashboard chat, repos, RAG studio, knowledge, drafts, workflow runs, reports, code graph, and evals.
- Live agent trace over SSE (`tool_use`, `tool_result`, `thought`, `delta`, `final`).
- Plan-then-execute: preview the multi-agent plan before running it.

## Tech Stack

| Layer | Technologies |
| --- | --- |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, httpx |
| Agents | LangGraph, LangChain (`langchain-openai`), any OpenAI-compatible LLM (DeepSeek by default), MCP |
| Retrieval | Milvus 2.5, Qwen3-Embedding-0.6B (`sentence-transformers`) or DashScope `text-embedding-v4`, BM25 |
| Storage | PostgreSQL 16; etcd + MinIO (Milvus dependencies) |
| Evaluation | RAGAS 0.4, pytest (237 tests) |
| Frontend | Next.js 15, React 19, TypeScript, Tailwind CSS, TanStack Query, react-markdown |
| Infra | Docker Compose |

## Getting Started

### Prerequisites

- Python **3.12**
- Node.js **18.18+** (tested with Node 24)
- Docker and Docker Compose
- git, plus ripgrep (optional, for faster code search)
- An OpenAI-compatible LLM API key (DeepSeek by default)
- A GitHub token (recommended; unauthenticated API access is limited to 60 requests per hour)
- Disk space for the Qwen3-Embedding-0.6B model, which downloads on first use

### Installation

```bash
# 1. Configure
cp .env.example .env              # then fill in the keys listed under Configuration

# 2. Start PostgreSQL + Milvus (with etcd and MinIO)
docker compose up -d postgres etcd minio milvus

# 3. Backend
cd backend
python3.12 -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-local-embedding.txt
uvicorn app.main:app --reload     # http://localhost:8000  (docs: /docs)

# 4. Frontend (in a new terminal, from the repo root)
cd frontend
npm install
npm run dev                       # http://localhost:3000
```

Tables are created automatically on first start.

### Configuration

All settings are read from `.env` (see `.env.example` for the full list). These are the ones you will usually change:

| Variable | Purpose |
| --- | --- |
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | Chat and agent model (any OpenAI-compatible endpoint) |
| `GITHUB_TOKEN` | Default token for GitHub API calls |
| `TOKEN_ENCRYPTION_KEY` | Secret used to encrypt per-repository tokens |
| `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` | `qwen_local` (default), `dashscope`, `openai_compatible`, or `deterministic` (tests only) |
| `LOCAL_EMBEDDING_DEVICE` | Set to `mps` on Apple Silicon or `cuda` on NVIDIA; CPU embedding of long documents is very slow |
| `MILVUS_URI`, `MILVUS_COLLECTION` | Vector store connection |
| `DASHSCOPE_API_KEY`, `RERANK_BASE_URL` | Optional DashScope embeddings and `qwen3-rerank` |
| `RAGAS_JUDGE_MODEL`, `RAGAS_TIMEOUT_SECONDS` | Judge model for evals; falls back to `LLM_*` when blank |
| `CONTEXT_*` | Token budget ratios and compaction thresholds |
| `AUTO_SYNC_ENABLED`, `AUTO_SYNC_INTERVAL_SECONDS`, `AUTO_SYNC_LIMIT` | Background sync; leave the limit unset to sync all pages |
| `GITHUB_WEBHOOK_SECRET` | Enables HMAC verification for `/api/webhooks/github` |

> All repositories share one Milvus collection, so they must use the same embedding provider, model, and dimensions. A mismatch raises an error rather than silently mixing vector spaces.

## Usage

### In the browser

The UI labels are currently mostly in Chinese, so each page is listed with its path.

1. **Repos** (`/repos`): connect `owner/repo`. Connecting runs a small initial sync; refresh the repository to fetch all pages.
2. **RAG Studio** (`/rag`): rebuild the index and test retrieval for a query.
3. **Dashboard** (`/`): chat with the agent and watch tool calls stream in. Example prompts:
   - `Where is the phone number validator implemented and which library does it use?`
   - `Have past PRs added new currency or language code types?`
   - `Is the repository ready for the next release, considering issues, PRs and CI?`
   - `Close issue #299 and add the label docs-done.` (returns a draft instead of writing)
4. **Drafts** (`/action-drafts`): confirm or cancel write actions.
5. **Runs** (`/workflow-runs`): inspect multi-agent workflow plans, task results, and Observer findings.
6. **Evals** (`/evals`): run the RAGAS suite and compare runs.

### Through the API

```bash
API=http://localhost:8000

# Connect a repository (token is optional; GITHUB_TOKEN is used otherwise)
curl -X POST $API/api/repos/connect -H 'Content-Type: application/json' \
  -d '{"owner": "pydantic", "repo": "pydantic-extra-types"}'
REPO_ID=<repo_id from the response>

# Full sync (limit: null = all pages)
curl -X POST $API/api/repos/$REPO_ID/sync -H 'Content-Type: application/json' \
  -d '{"sync_issues": true, "sync_pull_requests": true, "sync_workflow_runs": true, "limit": null}'

# Rebuild the RAG index, then search it
curl -X POST $API/api/rag/$REPO_ID/reindex
curl -X POST $API/api/rag/$REPO_ID/search -H 'Content-Type: application/json' \
  -d '{"question": "timezone tzdata dependency problems", "top_k": 5}'

# Chat (JSON response, or SSE stream)
curl -X POST $API/api/chat -H 'Content-Type: application/json' \
  -d "{\"repo_id\": \"$REPO_ID\", \"message\": \"Why did the latest CI run fail?\"}"
curl -N -X POST $API/api/chat/stream -H 'Content-Type: application/json' \
  -d "{\"repo_id\": \"$REPO_ID\", \"message\": \"Why did the latest CI run fail?\"}"

# Run the RAGAS evaluation (asynchronous; poll GET /api/evals/{eval_id})
curl -X POST $API/api/evals/rag/run -H 'Content-Type: application/json' \
  -d "{\"repo_id\": \"$REPO_ID\", \"run_judge\": true, \"top_k\": 5}"
```

Interactive API docs for all 100 endpoints are at `http://localhost:8000/docs`.

## Project Structure

```text
dev-flow/
├── backend/
│   ├── app/
│   │   ├── api/routes/        # 18 FastAPI routers: chat, repos, rag, evals, drafts, ...
│   │   ├── core/              # settings, logging, token encryption
│   │   ├── db/                # SQLAlchemy models (32 tables) and session
│   │   ├── mcp/               # stdio MCP memory server
│   │   ├── schemas/           # Pydantic request/response and agent output contracts
│   │   ├── services/
│   │   │   ├── agents/        # ChatAgent, Planner, Observer, Synthesis, Issue/PR/CI/Report/Safety
│   │   │   ├── rag/           # chunking, embeddings, Milvus store, retrieval, rerank, QA
│   │   │   ├── evals/         # RAGAS runner, eval suites
│   │   │   ├── github/        # GitHub REST client
│   │   │   ├── skills/        # SKILL.md registry
│   │   │   ├── chat_memory.py          # context assembly, memory, session sealing
│   │   │   └── context_compression.py  # budgets, pressure stages, compaction
│   │   ├── skills/            # 6 skills: issue-triage, pr-review, ci-debug, ...
│   │   └── tests/             # pytest suite
│   ├── requirements.txt
│   └── requirements-local-embedding.txt
├── frontend/
│   ├── app/                   # Next.js App Router pages
│   ├── components/            # layout, RAG settings, feedback controls
│   └── lib/                   # API client (incl. SSE parser), RAG helpers
├── bench/                     # benchmark scripts and raw results
├── docs/                      # architecture notes, API notes, sample knowledge doc
├── scripts/                   # pgvector init, demo seed, GitHub smoke test, SQLite demo
└── docker-compose.yml
```

## Architecture

### System overview

```text
┌───────────────────────────────────────────────────────────────────────┐
│ Frontend · Next.js 15 / React 19                                      │
│ chat · repos · RAG studio · knowledge · drafts · runs · evals         │
└───────────────────────────────────┬───────────────────────────────────┘
                                    │  REST  +  SSE stream
┌───────────────────────────────────▼───────────────────────────────────┐
│ Backend · FastAPI                                                     │
│                                                                       │
│  ┌─────────────────┐   ┌──────────────────────┐   ┌─────────────────┐ │
│  │ ChatAgent       │──▶│ Multi-agent workflow │   │ Context         │ │
│  │ LangGraph loop  │   │ Planner → Agents →   │   │ assembler &     │ │
│  │ 14 tools        │   │ Observer → Synthesis │   │ memory sealing  │ │
│  └────────┬────────┘   └──────────────────────┘   └─────────────────┘ │
│           │                                                           │
│  ┌────────▼────────┐   ┌──────────────────────┐   ┌─────────────────┐ │
│  │ Workspace tools │   │ Hybrid RAG           │   │ Safety drafts   │ │
│  │ ripgrep · read  │   │ BM25 + vector        │   │ RBAC · audit    │ │
│  └─────────────────┘   └──────────────────────┘   └─────────────────┘ │
│                                                                       │
│  GitHub sync & webhooks · Skill registry · MCP memory · RAGAS evals   │
└───────┬────────────────┬─────────────────┬─────────────────┬──────────┘
        ▼                ▼                 ▼                 ▼
   PostgreSQL         Milvus          GitHub REST    OpenAI-compatible
   (32 tables)    (1024-d, COSINE)        API          LLM (DeepSeek)
```

### ChatAgent loop

```text
 user message
      │
      ▼
 ┌──────────────────────┐   memory recall / project overview
 │  pre-routing guards  │─────────────────────────────────────▶ fixed tool path ──▶ answer
 └──────────┬───────────┘
            ▼
 ┌──────────────────────┐     tool calls      ┌──────────────────────┐
 │    model_decision    │────────────────────▶│     tool_action      │◀──┐ next pending
 │   LLM + 14 tools     │◀────────────────────│ retry · loop guard   │───┘ tool call
 └──────────┬───────────┘    observations     └──────────┬───────────┘
            │ no tool call                               │ step ≥ 12
            ▼                                            ▼
       final answer                               max_steps_stop
            │
            ▼
 SSE: tool_use · tool_result · thought · delta · final ──▶ persist + seal session memory
```

### Multi-agent engineering review

```text
                        ┌────────────────┐
 "Can we merge?" ──────▶│  PlannerAgent  │  WorkflowSpec: tasks · claims · dependencies
                        └───────┬────────┘
                                ▼
                        ┌────────────────┐
                        │  repo_health   │  baseline snapshot
                        └───────┬────────┘
         ┌───────────────┬──────┴────────┬───────────────┐   ready tasks run in parallel
         ▼               ▼               ▼               ▼   (max 3 at once, 90 s timeout each)
  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
  │ IssueAgent │  │  PRReview  │  │  CIDebug   │  │ RAG search │
  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘
         └───────────────┴───────┬───────┴───────────────┘
                                 ▼
                        ┌────────────────┐  merge gates · cross-agent conflicts
                        │ ObserverAgent  │  evidence gaps · low confidence
                        └───────┬────────┘
             fixable gap? ──yes─┤──▶ Planner.replan: add RAG / CI / safety tasks, rerun
                                │ no
                                ▼
                        ┌────────────────┐
                        │ SynthesisAgent │  What · Why · Tradeoff · Open Questions · Next Action
                        └────────────────┘
```

### Hybrid retrieval pipeline

```text
 query ─┬─▶ BM25 (title·path·symbol·labels·content weighted) ──────┐
        │                                                          │   40–200 candidates each
        └─▶ Qwen3 query embedding ──▶ Milvus COSINE search ────────┤
                                                                   ▼
                     weighted fusion: 0.62·vector + 0.30·bm25 + 0.08 if hit by both
                                                                   ▼
                     dedup: SHA-256 fingerprint + Jaccard ≥ 0.9 · ≤ 2 chunks per parent
                                                                   ▼
                     rerank: qwen3-rerank API when configured, heuristic otherwise
                                                                   ▼
                     parent-chunk expansion  or  query-aware extractive compression
                                                                   ▼
                                       cited evidence ──▶ ChatAgent / RAG Q&A
```

### Context budget

```text
 available prompt tokens = model window − reserved response
 ┌─────────┬───────────────┬────────────────────────┬───────────────┬────────┐
 │ system  │    memory     │        evidence        │ recent turns  │ tools  │
 │   12%   │      22%      │          34%           │      22%      │  10%   │
 └─────────┴───────────────┴────────────────────────┴───────────────┴────────┘
 pressure:  normal ─▶ warning ─▶ auto-compact ─▶ aggressive ─▶ manual
 actions:   microcompact old tool output ─▶ LLM compaction summary
            (key-fact preservation check · circuit breaker after 3 failures)
```

### Safe write path

```text
 "Close issue #299"
        │
        ▼
 ChatAgent ──▶ safety_agent.classify_action_risk ──▶ ActionDraft (pending_confirmation)
                                                             │
                                  human with draft:approve   │  POST /api/action-drafts/{id}/confirm
                                                             ▼
                                                     GitHub API write ──▶ audit_logs
```

## Benchmarks

Measured locally against `pydantic/pydantic-extra-types` (130 issues, 285 PRs, failed CI logs, project docs). Test setup:

- **Hardware:** Apple M5, embeddings on MPS.
- **Models:** `deepseek-flash` as the agent LLM; Qwen3-Embedding-0.6B for embeddings.
- **Embedding cap:** documents were capped at 2,048 tokens for indexing.

Scripts and raw JSON results are in [`bench/`](bench/).

**Retrieval.** The test set has 160 queries over 473 indexed documents: 80 sampled issues and PRs, each with one paraphrased query and one keyword query. Only the source item counts as a hit.

| Retriever | Recall@1 | Recall@5 | MRR@10 |
| --- | --- | --- | --- |
| BM25 only | 0.744 | 0.894 | 0.818 |
| Vector only, no query instruction | 0.731 | 0.906 | 0.809 |
| Vector only, Qwen3 query instruction | 0.863 | 0.975 | 0.914 |
| Hybrid weighted fusion | **0.881** | **0.975** | **0.923** |
| Hybrid + heuristic rerank (agent path) | 0.863 | 0.969 | 0.910 |

Hybrid retrieval p50 latency is 64 ms, plus 23 ms for the query embedding. Query-aware compression cut the top-5 context from 440K to 145K estimated tokens across all queries (−67%).

**Multi-agent workflow.** Every run executes the same 5-task DAG with replanning disabled, 8 runs per mode:

| Mode | Median | Range |
| --- | --- | --- |
| Sequential (`max_parallel_tasks=1`) | 87.3 s | 72.9–101.9 s |
| Parallel (`max_parallel_tasks=3`, default) | **53.3 s** | 34.2–69.1 s |

100 of 100 agent tasks succeeded.

**ChatAgent, end to end over HTTP.** 20 scenarios covering code, issues, PRs, CI, history, safety, and workflow:

- Tool routing: 18 of 20 correct.
- Tool calls: 6 of 246 failed; the agent continued past each failure.
- Prompt cache: 83.5% of 2.67M input tokens were cache hits.
- SSE: the first tool event arrived at a median 2.8 s; the full answer completed at a median 53 s.

**GitHub sync.** A full paginated sync of 130 issues and 285 PRs, including PR files and review comments, took 579 API calls and 259 s with zero errors.

To reproduce (each script takes its input and output paths as arguments):

1. Set `BACKEND` and `REPO_ID` in `bench/common.py`, and `REPO` in `chat_bench.py` and `sse_bench.py`.
2. With the backend's virtualenv, run `reindex.py` and `gen_queries.py`, then `retrieval_bench.py` and `workflow_bench.py`.
3. With the backend running, run `chat_bench.py` and `sse_bench.py`.

## Roadmap

- [ ] Let `issue_agent.analyze_issue` / `pr_review_agent.analyze_pr` accept an issue or PR number. They currently always analyze the most recent one.
- [ ] When the step budget runs out, synthesize an answer from the observations gathered so far instead of returning a fixed stop message.
- [ ] Replace the keyword pre-routing for "project overview" with a classifier. Its false positives send some report and workflow questions down the wrong path.
- [ ] Apply the Qwen3 query instruction on the ChatAgent retrieval path, not only in the knowledge-base API.
- [ ] Count workspace file reads as retrieved context in RAGAS so faithfulness reflects code-grounded answers; raise the RAGAS baseline above the configured thresholds.
- [ ] Use a learned reranker by default. The heuristic rerank does not beat plain fusion on the benchmark.
- [ ] Stream answer tokens directly from the model instead of chunking the finished answer.
- [ ] Add Alembic migrations, FastAPI lifespan handlers, and real user authentication (the current RBAC uses a demo owner).

## Contributing

1. Create a branch from `main`.
2. Keep changes covered by tests:
   ```bash
   (cd backend && .venv/bin/python -m pytest -q)
   (cd frontend && npx tsc --noEmit)
   ```
   Two tests assert default settings, so setting `AUTO_SYNC_LIMIT` or `CONTEXT_MODEL_WINDOW_TOKENS` in your local `.env` can make them fail.
3. For agent changes, rerun the relevant `bench/` script and include before/after numbers in the PR description.
4. Never commit `.env`, tokens, or `.data/`.
