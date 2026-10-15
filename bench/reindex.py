import time
import common
from app.db.session import SessionLocal
from app.services.rag.qa import reindex_documents, rag_status

db = SessionLocal()
t = time.time()
n = reindex_documents(db, common.REPO_ID)
print("reindexed", n, "docs in", round(time.time() - t, 1), "s", flush=True)
print(rag_status(db, common.REPO_ID))
