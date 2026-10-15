"""Shared setup for benchmark scripts: import the backend app, run embeddings on MPS with a 2048-token cap."""
import os
import sys

BACKEND = "/Users/ericsong/test/project/dev-flow/backend"
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)
os.environ.setdefault("AUTO_SYNC_ENABLED", "false")
os.environ.setdefault("LOCAL_EMBEDDING_DEVICE", "mps")

from app.services.rag import embeddings as _emb  # noqa: E402

_orig_loader = _emb._local_sentence_transformer.__wrapped__
MAX_SEQ = int(os.environ.get("BENCH_MAX_SEQ", "2048"))


@_emb.lru_cache(maxsize=4)
def _capped_loader(model_name, device):
    model = _orig_loader(model_name, device or "mps")
    model.max_seq_length = MAX_SEQ
    return model


_emb._local_sentence_transformer = _capped_loader
REPO_ID = "738918ba-f7bc-45cf-bfc2-807f2849a974"
