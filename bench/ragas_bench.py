"""RAGAS evaluation of the production ChatAgent path on a labeled subset of the retrieval queries.

Reference answers are written by DeepSeek from the gold issue/PR text only.
"""
import asyncio, json, random, sys
import httpx
import common
from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import Issue, PullRequest
from app.services.evals.ragas_runner import RagEvalCase, run_rag_quality_eval

queries = json.load(open(sys.argv[1]))
out = sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 20
db = SessionLocal()
rng = random.Random(11)
semantic = [q for q in queries if q["style"] == "semantic"]
picked = rng.sample(semantic, min(N, len(semantic)))

REF_PROMPT = ("Write a concise reference answer (2-4 sentences) to the developer's question using ONLY the given "
              "GitHub {kind}. Mention the {kind} number and the key facts. Return JSON {{\"reference\": \"...\"}}")

async def reference(client, q):
    model = Issue if q["source_type"] == "issue" else PullRequest
    item = db.get(model, q["gold_source_id"])
    kind = "issue" if q["source_type"] == "issue" else "pull request"
    payload = {"model": settings.llm_model, "response_format": {"type": "json_object"}, "temperature": 0,
               "messages": [{"role": "system", "content": REF_PROMPT.format(kind=kind)},
                            {"role": "user", "content": f"Question: {q['query']}\n\n{kind} #{item.number}: {item.title}\n\n{(item.body or '')[:4000]}"}]}
    r = await client.post(f"{settings.llm_base_url}/chat/completions", json=payload,
                          headers={"Authorization": f"Bearer {settings.llm_api_key}"})
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])["reference"]

async def main():
    async with httpx.AsyncClient(timeout=120) as client:
        refs = await asyncio.gather(*(reference(client, q) for q in picked))
    cases = [RagEvalCase(id=q["id"], question=q["query"], reference=ref, expected_source_ids=[q["gold_source_id"]],
                         source_type=q["source_type"]) for q, ref in zip(picked, refs)]
    json.dump([c.__dict__ for c in cases], open(out.replace(".json", "_cases.json"), "w"), ensure_ascii=False, indent=1)

    async def progress(p):
        print("progress", p.get("stage"), p.get("completed_cases"), "/", p.get("total_cases"), flush=True)

    result = await run_rag_quality_eval(db, common.REPO_ID, cases=cases, run_judge=True, progress_callback=progress)
    json.dump(result, open(out, "w"), ensure_ascii=False, indent=1, default=str)
    for key in ("status", "quality_status", "metrics", "retrieval_metrics", "summary", "thresholds"):
        if key in result:
            print(key, json.dumps(result[key], ensure_ascii=False, default=str)[:1500], flush=True)

asyncio.run(main())
