"""Singleton cross-encoder reranker with a CPU-safe fallback."""

from __future__ import annotations

import logging
import threading
from typing import Sequence

import torch
from sentence_transformers import CrossEncoder

_MODEL_NAME = "BAAI/bge-reranker-v2-m3"
_MODEL_LOCK = threading.Lock()
_MODEL: CrossEncoder | None = None

logger = logging.getLogger(__name__)


def _get_model() -> CrossEncoder:
    """Load the reranker once, preferring CUDA FP16 and safely falling back to CPU."""
    global _MODEL  # noqa: PLW0603
    if _MODEL is not None:
        return _MODEL

    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Loading reranker model=%s device=%s", _MODEL_NAME, device)
        _MODEL = CrossEncoder(_MODEL_NAME, device=device)
        if device == "cuda":
            _MODEL.model.half()
        _MODEL.model.eval()
        return _MODEL


def rerank(query: str, passages: Sequence[str]) -> list[float]:
    """Score query/passage pairs with the singleton CUDA-or-CPU cross encoder."""
    if not passages:
        return []
    model = _get_model()
    # Hugging Face's fast tokenizer mutates its padding/truncation state during
    # `predict`; concurrent calls on this shared cross-encoder raise
    # `RuntimeError: Already borrowed`. Retrieval may fan out per RFP need, so
    # serialize the inference section while retaining parallel database search.
    with _MODEL_LOCK:
        scores = model.predict(
            [(query, passage) for passage in passages],
            batch_size=16,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
    return [float(score) for score in scores]
