"""SSE streaming: time to first event / first tool_use / first answer delta / final, over /api/chat/stream."""
import json, statistics, sys, time
import httpx

API = "http://127.0.0.1:8000"
REPO = "738918ba-f7bc-45cf-bfc2-807f2849a974"
PROMPTS = [
    "Color 类型是怎么解析 hex 颜色字符串的？给出对应源码位置。",
    "Where is the phone number validator implemented and which third-party library does it depend on?",
    "历史上有没有讨论过 ISBN 校验相关的 Issue 或 PR？",
    "Which past issues discussed problems with timezone or tzdata dependencies?",
    "coordinate.py 里 Latitude 的取值范围校验是怎么写的？",
    "Have there been past pull requests that added new currency or language code types?",
]
rows = []
with httpx.Client(timeout=900) as client:
    for prompt in PROMPTS:
        conv = client.post(f"{API}/api/repos/{REPO}/conversations", json={"title": "bench sse"}).json()
        t0 = time.perf_counter(); marks = {}; events = 0
        with client.stream("POST", f"{API}/api/chat/stream", json={"repo_id": REPO, "conversation_id": conv["id"], "message": prompt}) as resp:
            buf = ""
            for chunk in resp.iter_text():
                buf += chunk
                while "\n\n" in buf:
                    raw, buf = buf.split("\n\n", 1)
                    name = next((l[7:] for l in raw.split("\n") if l.startswith("event: ")), "message")
                    events += 1
                    now = time.perf_counter() - t0
                    marks.setdefault("first_event", now)
                    marks.setdefault(f"first_{name}", now)
        marks["total"] = time.perf_counter() - t0
        row = {"prompt": prompt[:40], "events": events, **{k: round(v, 2) for k, v in marks.items()}}
        rows.append(row); print(json.dumps(row, ensure_ascii=False), flush=True)
        client.delete(f"{API}/api/repos/{REPO}/conversations/{conv['id']}")
fe = [r["first_tool_use"] for r in rows if "first_tool_use" in r]; tot = [r["total"] for r in rows]
print("SUMMARY", json.dumps({"n": len(rows), "first_tool_use_median_s": statistics.median(fe), "total_median_s": statistics.median(tot),
                             "events_median": statistics.median(r["events"] for r in rows)}), flush=True)
json.dump(rows, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
