"""Embedding model loader and encoder for BAAI/bge-m3."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import torch

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# Module-level singleton — populated by load_model()
_model = None
_model_name: str | None = None
SentenceTransformer = None


def load_model(model_path: str) -> None:
    """Load the SentenceTransformer model into the module singleton.

    Should be called once at application startup (FastAPI lifespan).
    """
    global _model, _model_name  # noqa: PLW0603
    if _model is not None and _model_name == model_path:
        logger.info("Model '%s' already loaded, skipping.", model_path)
        return

    global SentenceTransformer  # noqa: PLW0603
    if SentenceTransformer is None:
        from sentence_transformers import SentenceTransformer as sentence_transformer_class

        SentenceTransformer = sentence_transformer_class

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is required for the BGE-M3 embedding runtime; refusing CPU fallback."
        )

    device = "cuda"
    logger.info("Loading BGE-M3 embedding model '%s' on CUDA with float16 weights.", model_path)
    _model = SentenceTransformer(
        model_path,
        device=device,
        model_kwargs={"torch_dtype": torch.float16},
    )
    _model_name = model_path
    logger.info(
        "Model loaded: device=%s, dimension=%d, max_seq_length=%d",
        device,
        _model.get_sentence_embedding_dimension(),
        _model.max_seq_length,
    )


def encode(texts: list[str]) -> NDArray[np.float32]:
    """Encode raw BGE-M3 retrieval texts into embedding vectors.

    Returns:
        numpy array of shape (len(texts), dimension), dtype float32.
    """
    if _model is None:
        raise RuntimeError("Embedding model not loaded. Call load_model() first.")
    if not texts:
        return np.empty((0, get_dimension()), dtype=np.float32)

    vectors = _model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return vectors.astype(np.float32)


def get_dimension() -> int:
    """Return the loaded embedding vector dimension."""
    if _model is None:
        raise RuntimeError("Embedding model not loaded. Call load_model() first.")
    return _model.get_sentence_embedding_dimension()


def is_loaded() -> bool:
    """Check whether the embedding model has been loaded."""
    return _model is not None
