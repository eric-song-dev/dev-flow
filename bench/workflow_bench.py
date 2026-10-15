"""Multi-agent engineering-review workflow: wall-clock with max_parallel_tasks = 1 vs 3 (default) vs 4.

Uses the production planner, specialist agents (real DeepSeek calls), observer and synthesizer.
Replanning is disabled so every run executes the identical task graph.
"""
import asyncio, json, statistics, sys, time
import common
from app.api.routes.chat import _build_engineering_workflow_runtime, _skill_runtime_context
from app.db.models import Repository
from app.db.session import SessionLocal
from app.services.agents.workflow_orchestrator import WorkflowOrchestrator
from app.services.agents.planner_agent import PlannerAgent
from app.services.rag.retrieval import search_similar_documents

MESSAGE = "评估当前仓库整体工程状态：结合 Issue、PR、CI 失败和历史知识，有哪些阻塞和风险？下一步优先处理什么？"
RUNS = int(sys.argv[2]) if len(sys.argv) > 2 else 4
PARALLEL = [int(x) for x in (sys.argv[3] if len(sys.argv) > 3 else "1,3,4").split(",")]

async def one(db, repo, parallel):
    context = {**_skill_runtime_context(), "repo_id": str(repo.id), "team_members": [], "disable_replan": True}
    wf_context, runners = _build_engineering_workflow_runtime(repo, db, MESSAGE, context)
    spec = await PlannerAgent().run({"message": MESSAGE}, wf_context)
    spec["max_parallel_tasks"] = parallel
    t = time.perf_counter()
    report = await WorkflowOrchestrator(runners).run_spec(spec, wf_context, allow_replan=False)
    wall = time.perf_counter() - t
    tasks = []
    for r in report["task_results"]:
        from datetime import datetime
        s, e = r.get("started_at"), r.get("completed_at")
        dur = (datetime.fromisoformat(e) - datetime.fromisoformat(s)).total_seconds() if s and e else None
        tasks.append({"task": r["task_id"], "status": r["status"], "seconds": round(dur, 2) if dur is not None else None,
                      "confidence": r.get("confidence")})
    return {"parallel": parallel, "wall_s": round(wall, 2), "tasks": tasks,
            "plan": [(t["id"], t["dependencies"]) for t in report["spec"]["tasks"]],
            "observer": report["observation"]["summary"], "metrics": report["metrics"]}

async def main():
    db = SessionLocal()
    repo = db.get(Repository, common.REPO_ID)
    search_similar_documents(db, common.REPO_ID, "warm up embedding model", limit=3)  # load embedding model once
    results = []
    for i in range(RUNS):
        order = PARALLEL if i % 2 == 0 else list(reversed(PARALLEL))
        for p in order:
            r = await one(db, repo, p)
            results.append(r)
            print(json.dumps({k: r[k] for k in ("parallel", "wall_s", "tasks")}, ensure_ascii=False), flush=True)
    summary = {}
    for p in PARALLEL:
        walls = [r["wall_s"] for r in results if r["parallel"] == p]
        summary[p] = {"runs": len(walls), "median_s": round(statistics.median(walls), 2), "mean_s": round(statistics.mean(walls), 2),
                      "min_s": min(walls), "max_s": max(walls)}
    print("SUMMARY", json.dumps(summary), flush=True)
    print("PLAN", results[0]["plan"], flush=True)
    json.dump({"summary": summary, "results": results}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)

asyncio.run(main())
