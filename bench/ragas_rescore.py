"""Retry timed-out/missing Judge metrics with the project's rescore_rag_result (no ChatAgent rerun)."""
import asyncio, json, os, sys, time
import common
from app.services.evals.ragas_runner import rescore_rag_result

src, out = sys.argv[1], sys.argv[2]
result = json.load(open(src))
t0 = time.time()

async def progress(p):
    print(f"[{time.time() - t0:7.1f}s] {p.get('stage')} {p.get('completed_cases')}/{p.get('total_cases')} {p.get('message') or ''}"[:200], flush=True)

async def main():
    rescored = await rescore_rag_result(result, eval_id="bench-rescore", progress_callback=progress)
    json.dump(rescored, open(out, "w"), ensure_ascii=False, indent=1, default=str)
    for key in ("status", "quality_status", "execution_status", "metrics", "summary"):
        if key in rescored:
            print(key, json.dumps(rescored[key], ensure_ascii=False, default=str)[:2000], flush=True)

asyncio.run(main())
