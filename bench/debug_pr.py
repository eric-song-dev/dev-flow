import asyncio, traceback
import common
from app.api.routes.chat import _build_engineering_workflow_runtime, _skill_runtime_context
from app.db.models import Repository
from app.db.session import SessionLocal
from app.services.agents.planner_agent import PlannerAgent
from app.schemas.workflow import WorkflowSpec

MESSAGE = "评估当前仓库整体工程状态：结合 Issue、PR、CI 失败和历史知识，有哪些阻塞和风险？下一步优先处理什么？"
async def main():
    db = SessionLocal(); repo = db.get(Repository, common.REPO_ID)
    ctx = {**_skill_runtime_context(), "repo_id": str(repo.id), "team_members": []}
    wf, runners = _build_engineering_workflow_runtime(repo, db, MESSAGE, ctx)
    print({k: wf[k] for k in ("pr_number", "issue_number", "workflow_run_number")})
    spec = WorkflowSpec.model_validate(await PlannerAgent().run({"message": MESSAGE}, wf))
    task = next(t for t in spec.tasks if t.task_type == "pr_review")
    from unittest.mock import patch
    async def fake_json(self, *a, **k): return {}
    with patch("app.services.llm.client.LLMClient.chat_json", fake_json):
        try:
            r = await runners["pr_review"](task, spec, wf)
            print("ok", r.status, r.summary)
        except Exception:
            traceback.print_exc()
asyncio.run(main())
