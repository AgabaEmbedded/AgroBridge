"""Retrieval tools shared by all agents.

KB1 (agriculture) and KB2 (policy) live in separate Chroma collections. Every hit carries
the metadata and a citation string agents can quote without inventing references.
"""

from __future__ import annotations

from typing import Any

from win_runtime import preload_vc_runtime

preload_vc_runtime()

import chromadb
from chromadb.config import Settings as ChromaSettings

from services.config import settings
from services.embedding_service import embed_query

_client = None
_collections: dict[str, Any] = {}

KB_NAMES = ("KB1", "KB2")


def _client_instance():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=str(settings.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def collection_name(kb: str) -> str:
    if kb == "KB1":
        return settings.kb1_collection
    if kb == "KB2":
        return settings.kb2_collection
    raise ValueError(f"Unknown knowledge base: {kb!r}")


def get_collection(kb: str):
    kb = kb.upper()
    if kb not in _collections:
        _collections[kb] = _client_instance().get_or_create_collection(
            name=collection_name(kb),
            metadata={"hnsw:space": "cosine", "knowledge_base": kb},
        )
    return _collections[kb]


def get_client():
    return _client_instance()


def reset_collection(kb: str):
    """Drop and recreate a KB collection after an embedding-model change."""
    kb = kb.upper()
    name = collection_name(kb)
    _collections.pop(kb, None)
    try:
        _client_instance().delete_collection(name)
    except Exception:
        pass
    return get_collection(kb)


def _where(filters: dict[str, Any] | None):
    if not filters:
        return None
    clauses = []
    for key, value in filters.items():
        if isinstance(value, (list, tuple, set)):
            clauses.append({key: {"$in": list(value)}})
        else:
            clauses.append({key: {"$eq": value}})
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _citation(metadata: dict[str, Any]) -> str:
    kb = metadata.get("knowledge_base", "")
    name = metadata.get("document_name") or metadata.get("source_path") or "unknown document"
    page = metadata.get("page_number")
    chunk = metadata.get("chunk_index")
    label = f"{kb}/{name}"
    if page is not None:
        label += f" p.{page}"
    if chunk is not None:
        label += f" c.{chunk}"
    return label


def search(
    kb: str,
    query: str,
    top_k: int | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Search one knowledge base and return traceable passages."""
    kb = kb.upper()
    collection = get_collection(kb)
    total = collection.count()
    if total == 0 or not query.strip():
        return []

    limit = max(1, min(top_k or settings.top_k, total))
    result = collection.query(
        query_embeddings=[embed_query(query)],
        n_results=limit,
        where=_where(filters),
        include=["documents", "metadatas", "distances"],
    )

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    hits: list[dict[str, Any]] = []
    for text, metadata, distance in zip(documents, metadatas, distances):
        metadata = metadata or {}
        hits.append(
            {
                "text": text,
                "distance": float(distance),
                "document_id": metadata.get("document_id"),
                "document_name": metadata.get("document_name"),
                "knowledge_base": metadata.get("knowledge_base", kb),
                "document_type": metadata.get("document_type"),
                "source": metadata.get("source"),
                "source_path": metadata.get("source_path"),
                "publication_year": metadata.get("publication_year"),
                "page_number": metadata.get("page_number"),
                "chunk_index": metadata.get("chunk_index"),
                "category": metadata.get("category"),
                "metadata": metadata,
                "citation": _citation(metadata),
            }
        )
    return hits


def search_kb1(query: str, filters: dict[str, Any] | None = None, top_k: int | None = None):
    return search("KB1", query, top_k=top_k, filters=filters)


def search_kb2(query: str, filters: dict[str, Any] | None = None, top_k: int | None = None):
    return search("KB2", query, top_k=top_k, filters=filters)


def get_document(
    document_id: str, page_number: int | None = None, max_chars: int = 20000
) -> dict[str, Any]:
    """Fetch more content from an ingested source document, optionally one page."""
    where = {"document_id": {"$eq": document_id}}
    if page_number is not None:
        where = {
            "$and": [
                {"document_id": {"$eq": document_id}},
                {"page_number": {"$eq": page_number}},
            ]
        }

    found: list[dict[str, Any]] = []
    for kb in KB_NAMES:
        collection = get_collection(kb)
        if collection.count() == 0:
            continue
        result = collection.get(where=where, include=["documents", "metadatas"])
        for text, metadata in zip(result.get("documents", []), result.get("metadatas", [])):
            metadata = metadata or {}
            found.append(
                {
                    "text": text,
                    "metadata": metadata,
                    "page_number": metadata.get("page_number"),
                    "chunk_index": metadata.get("chunk_index", 0),
                }
            )

    if not found:
        return {"document_id": document_id, "found": False, "text": "", "chunks": []}

    found.sort(key=lambda item: (item["page_number"] or 0, item["chunk_index"] or 0))
    text = "\n\n".join(
        (f"[page {item['page_number']}]\n" if item["page_number"] is not None else "")
        + item["text"]
        for item in found
    )
    truncated = len(text) > max_chars
    return {
        "document_id": document_id,
        "found": True,
        "document_name": found[0]["metadata"].get("document_name"),
        "knowledge_base": found[0]["metadata"].get("knowledge_base"),
        "page_numbers": sorted({item["page_number"] for item in found if item["page_number"]}),
        "text": text[:max_chars],
        "truncated": truncated,
        "chunks": len(found),
    }


def collection_count(kb: str) -> int | None:
    try:
        return get_collection(kb).count()
    except Exception:
        return None
