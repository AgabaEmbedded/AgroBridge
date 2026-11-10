"""Document processing and incremental KB synchronisation.

Extraction preserves page numbers for PDFs, attaches KB/type/source metadata to every
chunk, and only embeds chunks that do not already exist. Chunk IDs are content hashes, so
edited or removed documents automatically drop their old chunks.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from docx import Document
from pypdf import PdfReader

from services.embedding_service import embed_passages

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}
CHUNK_SIZE = 1600
CHUNK_OVERLAP = 240

_TYPE_KEYWORDS = (
    ("budget", "budget"),
    ("expenditure", "budget"),
    ("report", "report"),
    ("review", "report"),
    ("assessment", "report"),
    ("evaluation", "report"),
    ("policy", "policy"),
    ("strategy", "policy"),
    ("plan", "policy"),
    ("regulation", "regulation"),
    ("standard", "regulation"),
    ("guideline", "guideline"),
    ("manual", "manual"),
    ("handbook", "guideline"),
    ("guide", "guideline"),
    ("research", "research"),
    ("study", "research"),
)


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start, end), text.rfind(". ", start, end))
            if boundary > start + size // 2:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def extract_pages(path: Path) -> list[tuple[int | None, str]]:
    """Return (page_number, text) pairs. Non-paginated formats use None."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        # PDFium is far faster and more robust than pypdf on large/malformed policy PDFs.
        try:
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(str(path))
            pages: list[tuple[int | None, str]] = []
            for index in range(len(document)):
                page = document[index]
                textpage = page.get_textpage()
                pages.append((index + 1, textpage.get_text_range()))
                textpage.close()
                page.close()
            return pages
        except Exception:
            reader = PdfReader(str(path))
            pages = []
            for number, page in enumerate(reader.pages, start=1):
                try:
                    pages.append((number, page.extract_text() or ""))
                except Exception:
                    pages.append((number, ""))
            return pages
    if suffix == ".docx":
        document = Document(str(path))
        parts = [p.text for p in document.paragraphs if p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))
        return [(None, "\n".join(parts))]
    return [(None, path.read_text(encoding="utf-8", errors="ignore"))]


def _sidecar_metadata(path: Path) -> dict[str, Any]:
    sidecar = path.with_name(path.name + ".meta.json")
    if not sidecar.exists():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _document_type(name: str, sidecar: dict[str, Any]) -> str:
    if sidecar.get("document_type"):
        return str(sidecar["document_type"])
    lowered = name.lower()
    for keyword, value in _TYPE_KEYWORDS:
        if keyword in lowered:
            return value
    return "document"


def _publication_year(name: str, sidecar: dict[str, Any]) -> int | None:
    value = sidecar.get("publication_year")
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    match = re.search(r"(19|20)\d{2}", name)
    return int(match.group(0)) if match else None


def build_kb_records(kb: str, kb_dir: Path) -> list[dict[str, Any]]:
    """Read every supported document under ``kb_dir`` into chunk records."""
    records: list[dict[str, Any]] = []
    if not kb_dir.exists():
        return records

    for path in sorted(kb_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        if path.name.endswith(".meta.json"):
            continue

        sidecar = _sidecar_metadata(path)
        relative = path.relative_to(kb_dir).as_posix()
        document_id = hashlib.sha256(f"{kb}:{relative}".encode("utf-8")).hexdigest()[:32]
        document_name = str(sidecar.get("title") or path.stem)
        document_type = _document_type(path.stem, sidecar)
        publication_year = _publication_year(path.stem, sidecar)
        category = str(sidecar.get("category") or ("policy" if kb == "KB2" else "agriculture"))
        source = str(sidecar.get("source") or "")

        try:
            pages = extract_pages(path)
        except Exception:
            print(f"Skipping unreadable file: {path}")
            continue
        print(f"{kb}: read {relative} ({len(pages)} page(s))", flush=True)

        for page_number, page_text in pages:
            text = clean_text(page_text)
            if not text:
                continue
            for chunk_index, chunk in enumerate(chunk_text(text), start=1):
                chunk_id = hashlib.sha256(
                    f"{document_id}:{page_number}:{chunk_index}:{chunk}".encode("utf-8")
                ).hexdigest()
                metadata: dict[str, Any] = {
                    "document_id": document_id,
                    "document_name": document_name,
                    "knowledge_base": kb,
                    "document_type": document_type,
                    "source": source,
                    "publication_year": publication_year,
                    "page_number": page_number,
                    "category": category,
                    "source_path": f"{kb}/{relative}",
                    "chunk_index": chunk_index,
                }
                # Chroma metadata cannot store None values.
                metadata = {key: value for key, value in metadata.items() if value is not None}
                records.append({"id": chunk_id, "text": chunk, "metadata": metadata})
    return records


def sync_collection(collection, records: list[dict[str, Any]], batch_size: int = 64) -> dict[str, int]:
    """Add new chunks, update changed metadata, delete stale chunks."""
    existing = collection.get(include=["metadatas"])
    existing_ids = set(existing.get("ids", []))
    existing_metadata = {
        chunk_id: metadata or {}
        for chunk_id, metadata in zip(
            existing.get("ids", []), existing.get("metadatas", []) or []
        )
    }

    desired_ids = {record["id"] for record in records}
    stale_ids = sorted(existing_ids - desired_ids)
    missing = [record for record in records if record["id"] not in existing_ids]
    metadata_updates = [
        record
        for record in records
        if record["id"] in existing_ids
        and existing_metadata.get(record["id"], {}) != record["metadata"]
    ]

    if stale_ids:
        collection.delete(ids=stale_ids)

    if metadata_updates:
        collection.update(
            ids=[record["id"] for record in metadata_updates],
            metadatas=[record["metadata"] for record in metadata_updates],
        )

    for start in range(0, len(missing), batch_size):
        batch = missing[start : start + batch_size]
        collection.upsert(
            ids=[record["id"] for record in batch],
            documents=[record["text"] for record in batch],
            metadatas=[record["metadata"] for record in batch],
            embeddings=embed_passages([record["text"] for record in batch]),
        )
        print(f"  embedded {min(start + batch_size, len(missing))}/{len(missing)} new chunks", flush=True)

    return {
        "added": len(missing),
        "removed": len(stale_ids),
        "metadata_updated": len(metadata_updates),
        "total": len(desired_ids),
    }


def iter_supported_files(folder: Path) -> Iterable[Path]:
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            yield path
