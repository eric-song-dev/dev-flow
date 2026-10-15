"""End-to-end ChatAgent benchmark over the HTTP API: tool selection, completion, latency, tokens, prompt-cache hits.

Each case runs in its own new conversation, which is deleted afterwards.
"""
import json, statistics, sys, time
import httpx

API = "http://127.0.0.1:8000"
REPO = "738918ba-f7bc-45cf-bfc2-807f2849a974"
cases = json.load(open(sys.argv[1]))
out = sys.argv[2]
results = []
with httpx.Client(timeout=600) as client:
    for case in cases:
        conv = client.post(f"{API}/api/repos/{REPO}/conversations", json={"title": f"bench {case['id']}"}).json()
        t = time.perf_counter()
        r = client.post(f"{API}/api/chat", json={"repo_id": REPO, "conversation_id": conv["id"], "message": case["message"]})
        wall = time.perf_counter() - t
        if r.status_code != 200:
            results.append({"id": case["id"], "error": r.status_code, "body": r.text[:500], "wall_s": wall})
            print(case["id"], "HTTP", r.status_code, r.text[:200], flush=True)
            continue
        data = r.json()
        called = [c["tool_name"] for c in data.get("tool_calls") or []]
        usage = data.get("model_usage") or []
        row = {
            "id": case["id"], "wall_s": round(wall, 2), "route": data.get("route"),
            "called": called, "expect": case["expect"],
            "tool_hit": any(t in called for t in case["expect"]),
            "first_tool_hit": bool(called) and called[0] in case["expect"],
            "completion": data.get("completion"),
            "tool_errors": [c for c in data.get("tool_calls") or [] if c.get("status") == "error"],
            "llm_calls": len(usage),
            "input_tokens": sum(int(u.get("input_tokens") or 0) for u in usage),
            "output_tokens": sum(int(u.get("output_tokens") or 0) for u in usage),
            "cache_read_tokens": sum(int(u.get("cache_read_input_tokens") or 0) for u in usage),
            "usage_sources": sorted({u.get("source") for u in usage}),
            "runtime_tool_context": (data.get("context_diagnostics") or {}).get("runtime_tool_context"),
            "prompt_calls": [(p.get("phase"), p.get("estimated_prompt_tokens")) for p in (data.get("context_diagnostics") or {}).get("prompt_calls") or []],
            "answer_head": (data.get("answer") or "")[:300],
            "conversation_id": conv["id"],
        }
        results.append(row)
        print(json.dumps({k: row[k] for k in ("id", "wall_s", "called", "tool_hit", "llm_calls", "input_tokens", "cache_read_tokens")}, ensure_ascii=False), flush=True)
        client.delete(f"{API}/api/repos/{REPO}/conversations/{conv['id']}")

ok = [r for r in results if "error" not in r]
walls = sorted(r["wall_s"] for r in ok)
inp = sum(r["input_tokens"] for r in ok); cached = sum(r["cache_read_tokens"] for r in ok)
summary = {
    "cases": len(results), "http_ok": len(ok),
    "tool_selection_accuracy": round(sum(r["tool_hit"] for r in ok) / len(ok), 4),
    "first_tool_accuracy": round(sum(r["first_tool_hit"] for r in ok) / len(ok), 4),
    "completed": sum(1 for r in ok if (r["completion"] or {}).get("status", "").startswith("completed")),
    "runs_with_tool_errors": sum(1 for r in ok if r["tool_errors"]),
    "latency_p50_s": statistics.median(walls), "latency_p95_s": walls[int(0.95 * (len(walls) - 1))],
    "llm_calls_total": sum(r["llm_calls"] for r in ok),
    "input_tokens_total": inp, "output_tokens_total": sum(r["output_tokens"] for r in ok),
    "cache_read_tokens_total": cached, "cache_hit_ratio": round(cached / inp, 4) if inp else None,
}
print("SUMMARY", json.dumps(summary), flush=True)
json.dump({"summary": summary, "results": results}, open(out, "w"), ensure_ascii=False, indent=1)
