"""Embedding service backed by Google Gemini's embedding API.

The configured model is ``gemini-embedding-001``. Retrieval uses the asymmetric task
types recommended by Gemini: ``RETRIEVAL_DOCUMENT`` for indexed passages and
``RETRIEVAL_QUERY`` for caller questions. Vectors are L2-normalised before storage and
query so the cosine Chroma collections remain comparable.
"""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable

from services.config import settings

# Gemini batchEmbedContents accepts at most 100 requests; keep a safety margin.
_MAX_BATCH = 64


class EmbeddingServiceError(RuntimeError):
    """Raised when the embedding provider is not configured or returns invalid data."""


def _api_key() -> str:
    key = (settings.gemini_api_key or "").strip()
    if not key:
        raise EmbeddingServiceError(
            "GEMINI_API_KEY (or GOOGLE_API_KEY) is not configured. "
            "Set it in .env before querying or reindexing."
        )
    return key


def _endpoint(method: str) -> str:
    base = settings.gemini_api_base_url.rstrip("/")
    model = urllib.parse.quote(settings.embedding_model, safe="")
    return f"{base}/models/{model}:{method}"


def _request_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": _api_key(),
        },
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(settings.gemini_embedding_retries):
        try:
            with urllib.request.urlopen(request, timeout=settings.gemini_embedding_timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt + 1 >= settings.gemini_embedding_retries:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise EmbeddingServiceError(
                    f"Gemini embedding request failed with HTTP {exc.code}: {detail}"
                ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 >= settings.gemini_embedding_retries:
                raise EmbeddingServiceError(f"Gemini embedding request failed: {exc}") from exc
        time.sleep(min(8.0, 1.5 * (2**attempt)))
    raise EmbeddingServiceError(f"Gemini embedding request failed: {last_error}")


def _normalise(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        raise EmbeddingServiceError("Gemini returned a zero-length embedding vector.")
    return [value / norm for value in values]


def _embed_batch(texts: list[str], task_type: str) -> list[list[float]]:
    _api_key()
    requests = [
        {
            "model": f"models/{settings.embedding_model}",
            "content": {"parts": [{"text": text}]},
            "taskType": task_type,
            "outputDimensionality": settings.embedding_dimension,
        }
        for text in texts
    ]
    result = _request_json(_endpoint("batchEmbedContents"), {"requests": requests})
    embeddings = result.get("embeddings") or []
    if len(embeddings) != len(texts):
        raise EmbeddingServiceError(
            f"Gemini returned {len(embeddings)} embeddings for {len(texts)} inputs."
        )
    vectors: list[list[float]] = []
    for item in embeddings:
        values = item.get("values") or []
        if len(values) != settings.embedding_dimension:
            raise EmbeddingServiceError(
                f"Gemini returned dimension {len(values)}; expected {settings.embedding_dimension}."
            )
        vectors.append(_normalise([float(value) for value in values]))
    return vectors


def dimension() -> int:
    return settings.embedding_dimension


def embed_passages(texts: Iterable[str]) -> list[list[float]]:
    items = [str(text) for text in texts]
    if not items:
        return []
    vectors: list[list[float]] = []
    for start in range(0, len(items), _MAX_BATCH):
        vectors.extend(_embed_batch(items[start : start + _MAX_BATCH], "RETRIEVAL_DOCUMENT"))
    return vectors


def embed_query(text: str) -> list[float]:
    result = _request_json(
        _endpoint("embedContent"),
        {
            "model": f"models/{settings.embedding_model}",
            "content": {"parts": [{"text": str(text)}]},
            "taskType": "RETRIEVAL_QUERY",
            "outputDimensionality": settings.embedding_dimension,
        },
    )
    values = (result.get("embedding") or {}).get("values") or []
    if len(values) != settings.embedding_dimension:
        raise EmbeddingServiceError(
            f"Gemini returned query dimension {len(values)}; expected {settings.embedding_dimension}."
        )
    return _normalise([float(value) for value in values])


def warmup() -> int:
    """Validate configuration without making a network call."""
    _api_key()
    return dimension()
