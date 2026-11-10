"""Embedding service: local multilingual model, independent of the generation LLM."""

from __future__ import annotations

import threading
from typing import Iterable

from win_runtime import preload_vc_runtime

# Must run before torch/chromadb import their native extensions (see win_runtime.py).
preload_vc_runtime()

from sentence_transformers import SentenceTransformer

from services.config import settings

_model: SentenceTransformer | None = None
_lock = threading.Lock()


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = SentenceTransformer(settings.embedding_model)
    return _model


def dimension() -> int | None:
    return get_model().get_embedding_dimension()


def embed_passages(texts: Iterable[str]) -> list[list[float]]:
    items = list(texts)
    if not items:
        return []
    vectors = get_model().encode(
        [f"passage: {text}" for text in items],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    vector = get_model().encode(
        [f"query: {text}"], normalize_embeddings=True, show_progress_bar=False
    )[0]
    return vector.tolist()


def warmup() -> int | None:
    return dimension()
