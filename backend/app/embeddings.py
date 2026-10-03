"""
Local embedding + reranker models (sentence-transformers on CPU).

Models are loaded lazily the first time they're needed, so the worker only pays the memory
cost when it actually runs an import. Downloads are cached in HF_HOME (a docker volume).
"""

import logging
import threading
import time

from app import metrics
from app.config import settings

log = logging.getLogger(__name__)

_lock = threading.Lock()
_embedder = None
_reranker = None

def get_embedder():
    global _embedder
    with _lock:
        if _embedder is None:
            import torch
            from sentence_transformers import SentenceTransformer

            torch.set_num_threads(settings.torch_threads)
            start = time.perf_counter()
            _embedder = SentenceTransformer(settings.embedding_model, device="cpu")
            #complaints and kb sections are short, no need for the 32k default
            _embedder.max_seq_length = 512
            log.info(
                "embedding model loaded",
                extra={"model": settings.embedding_model, "seconds": round(time.perf_counter() - start, 1)},
            )
    return _embedder


def get_reranker():
    global _reranker
    with _lock:
        if _reranker is None:
            from sentence_transformers import CrossEncoder

            _reranker = CrossEncoder(settings.reranker_model, device="cpu", max_length=512)
            log.info("reranker loaded", extra={"model": settings.reranker_model})
    return _reranker


def embed_documents(texts: list[str], log_every: int = 64) -> list[list[float]]:
    if not texts:
        return []
    model = get_embedder()
    out: list[list[float]] = []
    start = time.perf_counter()
    #encode in slices so long imports show progress in the logs instead of looking stuck
    for i in range(0, len(texts), log_every):
        batch = texts[i : i + log_every]
        vectors = model.encode_document(batch, batch_size=16, normalize_embeddings=True)
        out.extend(v.tolist() for v in vectors)
        if len(texts) > log_every:
            log.info(
                "embedding progress",
                extra={"done": len(out), "total": len(texts), "seconds": round(time.perf_counter() - start, 1)},
            )
    return out


def embed_query(text: str) -> list[float]:
    model = get_embedder()
    with metrics.STAGE_LATENCY.labels("embed_query").time():
        vector = model.encode_query([text], normalize_embeddings=True)[0]
    return vector.tolist()


def rerank_scores(query: str, documents: list[str]) -> list[float]:
    """relevance score per document (higher is better), cross-encoder reads query and doc together"""
    if not documents:
        return []
    model = get_reranker()
    with metrics.STAGE_LATENCY.labels("rerank").time():
        #single-label cross encoders already return a 0-1 score (sigmoid applied)
        scores = model.predict([(query, doc) for doc in documents])
    return [float(s) for s in scores]
