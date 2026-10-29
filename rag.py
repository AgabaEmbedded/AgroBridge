from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from win_runtime import preload_vc_runtime

# Must run before torch/chromadb import their native extensions (see win_runtime.py).
preload_vc_runtime()

import chromadb
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "farmvoice_knowledge"

# Multilingual embedding model is a reasonable starting point, not a guarantee of
# strong Hausa retrieval. Evaluate it with real Hausa farmer questions.
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"

_model: SentenceTransformer | None = None
_collection = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(DB_DIR))
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def embed_passages(texts: list[str]) -> list[list[float]]:
    # E5 models expect these prefixes for retrieval tasks.
    vectors = get_model().encode(
        [f"passage: {text}" for text in texts],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vectors.tolist()


def retrieve(query: str, top_k: int = 4) -> list[dict[str, Any]]:
    collection = get_collection()
    if collection.count() == 0:
        return []

    query_vector = get_model().encode(
        [f"query: {query}"], normalize_embeddings=True, show_progress_bar=False
    )[0].tolist()
    result = collection.query(
        query_embeddings=[query_vector],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    hits: list[dict[str, Any]] = []
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    for text, metadata, distance in zip(documents, metadatas, distances):
        hits.append({"text": text, "metadata": metadata or {}, "distance": float(distance)})
    return hits
