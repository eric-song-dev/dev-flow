"""Retrieval ablation over the labeled query set: BM25 vs vector vs weighted hybrid vs hybrid + rerank."""
import json, math, statistics, sys, time
import common
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.rag.embeddings import embed_knowledge_query, embed_text
from app.services.rag.retrieval import search_similar_documents
from app.services.context_compression import compress_retrieval_results, estimate_tokens

cases = json.load(open(sys.argv[1]))
out_path = sys.argv[2]
K = 10
db = SessionLocal()

def embed_q(q, instructed=True):
    if instructed:
        return embed_knowledge_query(q, provider=settings.embedding_provider, model=settings.embedding_model,
                                     dimensions=settings.embedding_dimensions)
    return embed_text(q)

CONFIGS = {
    "bm25": dict(retrieval_method="fulltext", apply_rerank=False),
    "vector": dict(retrieval_method="vector", apply_rerank=False),
    "hybrid_weighted": dict(retrieval_method="hybrid", apply_rerank=False),
    "hybrid_weighted+rerank": dict(retrieval_method="hybrid", apply_rerank=True),
    "vector_no_query_instruction": dict(retrieval_method="vector", apply_rerank=False, instructed=False),
}

def ranks(results, gold):
    for idx, r in enumerate(results, 1):
        if str(r.get("source_id")) == gold or str(r.get("id")) == gold:
            return idx
    return None

embed_times = []
q_cache = {}
for case in cases:
    t = time.perf_counter(); q_cache[(case["id"], True)] = embed_q(case["query"]); embed_times.append(time.perf_counter() - t)
    q_cache[(case["id"], False)] = embed_q(case["query"], instructed=False)

rows = {name: [] for name in CONFIGS}
latency = {name: [] for name in CONFIGS}
compression = []
for case in cases:
    for name, cfg in CONFIGS.items():
        cfg = dict(cfg); instructed = cfg.pop("instructed", True)
        t = time.perf_counter()
        res = search_similar_documents(db, common.REPO_ID, case["query"], limit=K,
                                       query_embedding=q_cache[(case["id"], instructed)],
                                       apply_compression=False, **cfg)
        latency[name].append(time.perf_counter() - t)
        rows[name].append({"id": case["id"], "style": case["style"], "rank": ranks(res, case["gold_source_id"]),
                           "top": [(r.get("source_type"), r.get("title")) for r in res[:3]]})
        if name == "hybrid_weighted+rerank":
            top5 = res[:5]
            before = sum(estimate_tokens(str(r.get("_raw_content") or r.get("snippet") or "")) for r in top5)
            comp = compress_retrieval_results(case["query"], top5, max_tokens_per_item=260)
            after = sum(estimate_tokens(str(r.get("snippet") or "")) for r in comp)
            compression.append((before, after))

def metrics(rs):
    n = len(rs)
    out = {"n": n}
    for k in (1, 3, 5, 10):
        out[f"recall@{k}"] = round(sum(1 for r in rs if r["rank"] and r["rank"] <= k) / n, 4)
    out["mrr@10"] = round(sum(1 / r["rank"] for r in rs if r["rank"]) / n, 4)
    out["ndcg@10"] = round(sum(1 / math.log2(r["rank"] + 1) for r in rs if r["rank"]) / n, 4)
    return out

summary = {}
for name, rs in rows.items():
    summary[name] = {"all": metrics(rs)}
    for style in ("semantic", "keyword"):
        summary[name][style] = metrics([r for r in rs if r["style"] == style])
    lat = sorted(latency[name])
    summary[name]["latency_ms"] = {"p50": round(statistics.median(lat) * 1000, 1), "p95": round(lat[int(0.95 * (len(lat) - 1))] * 1000, 1)}
emb = sorted(embed_times)
summary["_query_embedding_ms"] = {"p50": round(statistics.median(emb) * 1000, 1), "p95": round(emb[int(0.95 * (len(emb) - 1))] * 1000, 1)}
b = sum(x for x, _ in compression); a = sum(y for _, y in compression)
summary["_context_compression_top5"] = {"tokens_before": b, "tokens_after": a, "reduction": round(1 - a / b, 4) if b else 0}
json.dump({"summary": summary, "rows": rows}, open(out_path, "w"), ensure_ascii=False, indent=1)
for name, s in summary.items():
    print(name, json.dumps(s))
