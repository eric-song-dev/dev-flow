import sys, time
sys.path.insert(0, "/Users/ericsong/test/project/dev-flow/backend")
import os
os.chdir("/Users/ericsong/test/project/dev-flow/backend")
from sentence_transformers import SentenceTransformer
from app.db.session import SessionLocal
from app.db.models import PullRequest
db = SessionLocal()
texts = [f"{p.title}\n{p.body or ''}" for p in db.query(PullRequest).limit(32).all()]
for device in sys.argv[1:]:
    m = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B", device=device)
    m.max_seq_length = 2048
    t = time.time(); v = m.encode(texts, batch_size=8, normalize_embeddings=True); print(device, len(texts), "docs", round(time.time() - t, 2), "s", v.shape, flush=True)
