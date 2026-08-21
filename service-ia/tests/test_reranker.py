import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from app.retrieval.reranker import rerank


class _ConcurrentUnsafeModel:
    def __init__(self):
        self._in_use = False

    def predict(self, pairs, **_kwargs):
        if self._in_use:
            raise RuntimeError("Already borrowed")
        self._in_use = True
        try:
            time.sleep(0.02)
            return [0.5 for _ in pairs]
        finally:
            self._in_use = False


def test_rerank_serializes_shared_fast_tokenizer_access():
    model = _ConcurrentUnsafeModel()
    barrier = threading.Barrier(2)

    def score() -> list[float]:
        barrier.wait()
        return rerank("question", ["passage"])

    with patch("app.retrieval.reranker._get_model", return_value=model):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: score(), range(2)))

    assert results == [[0.5], [0.5]]
