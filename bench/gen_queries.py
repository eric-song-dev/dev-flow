"""Generate a labeled retrieval query set from synced issues/PRs with DeepSeek.

Each sampled item gets two queries: a paraphrased natural-language question and a short
keyword-style search. The gold label is the item's own record id.
"""
import asyncio, json, random, re, sys
import httpx
import common  # noqa: F401
from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import Issue, PullRequest

OUT = sys.argv[1]
N_PER_TYPE = int(sys.argv[2]) if len(sys.argv) > 2 else 40
BOTS = ("dependabot", "pre-commit-ci", "renovate", "github-actions")

PROMPT = """You build a retrieval benchmark for an engineering assistant indexed on a GitHub repository's issues and pull requests.
Given ONE {kind}, write two search queries a developer would use when trying to find exactly this {kind} later.
Rules:
- "semantic": one natural-language question (12-30 words) describing the problem/change in your own words. Do NOT copy any 3+ word phrase from the title, do NOT mention the {kind} number.
- "keyword": a short search-box query of 3-6 terms (identifiers, error names, type names are fine).
- Both must be specific enough that this {kind} is the best answer among hundreds of others in the same repository.
Return JSON: {{"semantic": "...", "keyword": "..."}}"""

def sample():
    db = SessionLocal()
    rng = random.Random(7)
    issues = [i for i in db.query(Issue).filter(Issue.repo_id == common.REPO_ID).all()
              if len((i.body or "").strip()) >= 100 and not any(b in (i.author or "").lower() for b in BOTS)]
    prs = [p for p in db.query(PullRequest).filter(PullRequest.repo_id == common.REPO_ID).all()
           if len((p.body or "").strip()) >= 100 and not any(b in (p.author or "").lower() for b in BOTS)]
    issues.sort(key=lambda x: x.number); prs.sort(key=lambda x: x.number)
    picked = [("issue", i) for i in rng.sample(issues, min(N_PER_TYPE, len(issues)))]
    picked += [("pull_request", p) for p in rng.sample(prs, min(N_PER_TYPE, len(prs)))]
    print("eligible issues", len(issues), "eligible prs", len(prs), "picked", len(picked), flush=True)
    return [(kind, str(item.id), item.number, item.title, (item.body or "")[:3000]) for kind, item in picked]

async def gen(client, sem, kind, item_id, number, title, body):
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": PROMPT.format(kind="issue" if kind == "issue" else "pull request")},
            {"role": "user", "content": f"Title: {title}\n\nBody:\n{body}"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    }
    async with sem:
        for attempt in range(3):
            try:
                r = await client.post(f"{settings.llm_base_url}/chat/completions", json=payload,
                                      headers={"Authorization": f"Bearer {settings.llm_api_key}"})
                r.raise_for_status()
                data = json.loads(r.json()["choices"][0]["message"]["content"])
                return [
                    {"id": f"{kind}-{number}-{style}", "style": style, "query": data[style].strip(),
                     "source_type": kind, "gold_source_id": item_id, "number": number, "title": title}
                    for style in ("semantic", "keyword") if str(data.get(style) or "").strip()
                ]
            except Exception as exc:  # retry transient failures
                err = exc
        print("failed", kind, number, err, flush=True)
        return []

async def main():
    items = sample()
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=120) as client:
        rows = await asyncio.gather(*(gen(client, sem, *item) for item in items))
    cases = [case for group in rows for case in group]
    json.dump(cases, open(OUT, "w"), ensure_ascii=False, indent=1)
    print("wrote", len(cases), "queries", flush=True)

asyncio.run(main())
