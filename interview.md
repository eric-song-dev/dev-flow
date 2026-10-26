AI Engineering Copilot | Python, FastAPI, LangGraph, LangChain, RAG, Milvus, PostgreSQL, MCP, TypeScript, Next.js, React

1. To ground merge and release decisions in Issue, PR, and CI evidence, architected a multi-agent review workflow (Planner → Issue/PR/CI/RAG agents → Observer → Synthesis) with dependency-aware DAG scheduling, bounded concurrency, per-task timeouts, and observer-triggered replanning; cut median latency 39% (87 s → 53 s) vs. sequential execution over 16 live runs, with 100/100 agent tasks succeeding.
2. To answer questions over a repository's engineering history, built a hybrid RAG pipeline over 470+ issues, PRs, CI logs, and docs that fuses field-weighted BM25 with Milvus vector search on Qwen3 embeddings, plus near-duplicate and per-parent dedup; raised Recall@5 from 0.89 to 0.97 and MRR from 0.82 to 0.91 over BM25 on 160 labeled queries, while query-aware compression cut context tokens 67%.
3. To let one assistant handle code, history, and repo-ops questions, built a LangGraph tool-calling agent over 14 tools (workspace code search, RAG, an MCP memory server, issue/PR/CI agents) with loop guards, retryable-error classification, and token-budgeted context assembly; it routed 90% of 20 benchmark scenarios to the right tool, and a cache-stable prompt prefix served 83% of 2.67M input tokens from the provider's prompt cache.
4. To sync live GitHub data safely, engineered a FastAPI + PostgreSQL backend (100 REST endpoints, 32 tables) with idempotent paginated sync, HMAC-verified webhooks, RBAC, Fernet-encrypted tokens, and audit-logged human approval before any GitHub write; a full sync ingested 415 issues and PRs over 579 API calls with zero errors, backed by 237 pytest tests.
5. To make long-running agent work observable, shipped a Next.js 15 / React 19 + TypeScript console that streams tool_use/tool_result events over SSE and requires users to approve a multi-agent workflow's plan before it executes; the first live tool event arrives at a median 2.8 s vs. 53 s for full completion.



AI Engineering Copilot | Python, FastAPI, LangGraph, LangChain, RAG, Milvus, PostgreSQL, MCP, TypeScript, Next.js, React

1. Architected a multi-agent review workflow orchestrating Planner, Issue/PR/CI/RAG agents, Observer, and Synthesis as a dependency-aware DAG; cut median latency by 39% versus sequential execution.
2. Built a hybrid RAG pipeline over 400+ GitHub issues, PRs, and CI logs, fusing field-weighted BM25 with Milvus vector search; lifted Recall@5 from 0.89 to 0.97 and cut context tokens by 67%.
3. Built a LangGraph tool-calling agent over 14 tools, including code search, RAG, and an MCP memory server; achieved 90% tool-routing accuracy and an 83% prompt-cache hit rate.
4. Engineered a FastAPI and PostgreSQL backend with 100 REST endpoints, idempotent GitHub sync, HMAC webhooks, and RBAC-gated write approval; synced 415 issues and PRs with zero errors.
5. Shipped a Next.js 15 and React 19 console streaming agent tool events over SSE with plan-then-execute approval, surfacing live progress in a median 2.8 s versus 53 s for full completion.

- Backend：4、1、2
- AI Applied：1、2、3
- Full Stack：5、4、1