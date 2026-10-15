"""RAGAS evaluation on the first N pre-generated cases (references already written), with stage timestamps."""
import asyncio, json, sys, time
import common
from app.db.session import SessionLocal
from app.services.evals.ragas_runner import RagEvalCase, run_rag_quality_eval

cases_path, out, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
cases = [RagEvalCase(**c) for c in json.load(open(cases_path))[:n]]
db = SessionLocal()
t0 = time.time()

async def progress(p):
    print(f"[{time.time() - t0:7.1f}s] {p.get('stage')} {p.get('completed_cases')}/{p.get('total_cases')} {p.get('case_id') or ''}", flush=True)

async def main():
    result = await run_rag_quality_eval(db, common.REPO_ID, cases=cases, run_judge=True, progress_callback=progress)
    json.dump(result, open(out, "w"), ensure_ascii=False, indent=1, default=str)
    print("KEYS", list(result.keys()), flush=True)
    for key in ("status", "quality_status", "execution_status", "metrics", "retrieval_metrics", "summary", "thresholds"):
        if key in result:
            print(key, json.dumps(result[key], ensure_ascii=False, default=str)[:2000], flush=True)

asyncio.run(main())
