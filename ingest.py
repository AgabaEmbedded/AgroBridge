from __future__ import annotations

import hashlib
import re
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from rag import BASE_DIR, embed_passages, get_collection

DOCUMENTS_DIR = BASE_DIR / "documents"
SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}
CHUNK_SIZE = 1_000
CHUNK_OVERLAP = 150


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        document = Document(str(path))
        parts = [p.text for p in document.paragraphs if p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))
        return "\n".join(parts)
    return path.read_text(encoding="utf-8", errors="ignore")


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    # Character-based chunks are intentionally simple. Split near paragraph/sentence
    # boundaries where possible, while keeping overlap to preserve context.
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


def main() -> None:
    if not DOCUMENTS_DIR.exists():
        DOCUMENTS_DIR.mkdir(parents=True)

    files = [p for p in DOCUMENTS_DIR.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES]
    if not files:
        print(f"No supported documents found in {DOCUMENTS_DIR}")
        print("Add PDF, DOCX, TXT, or Markdown files, then run this script again.")
        return

    ids: list[str] = []
    texts: list[str] = []
    metadatas: list[dict[str, str | int]] = []
    source_count = 0

    for path in files:
        text = clean_text(extract_text(path))
        if not text:
            print(f"Skipping empty/unextractable file: {path.name}")
            continue
        source_count += 1

        relative_path = str(path.relative_to(DOCUMENTS_DIR))
        chunks = chunk_text(text)
        for index, chunk in enumerate(chunks):
            stable_id = hashlib.sha256(f"{relative_path}:{index}:{chunk}".encode("utf-8")).hexdigest()
            ids.append(stable_id)
            texts.append(chunk)
            metadatas.append({"source": relative_path, "chunk": index + 1})

    if not texts:
        print("No extractable text found.")
        return

    collection = get_collection()
    existing_ids = set(collection.get(include=[])["ids"])
    desired_ids = set(ids)
    stale_ids = sorted(existing_ids - desired_ids)
    missing = [index for index, chunk_id in enumerate(ids) if chunk_id not in existing_ids]

    if not missing and not stale_ids:
        print(
            f"Index already up to date: {len(desired_ids)} chunks from "
            f"{source_count} document(s). Nothing to embed."
        )
        return

    if stale_ids:
        collection.delete(ids=stale_ids)
        print(f"Removed {len(stale_ids)} stale chunk(s) from changed or deleted documents")

    batch_size = 64
    for start in range(0, len(missing), batch_size):
        batch_indexes = missing[start : start + batch_size]
        collection.upsert(
            ids=[ids[index] for index in batch_indexes],
            documents=[texts[index] for index in batch_indexes],
            metadatas=[metadatas[index] for index in batch_indexes],
            embeddings=embed_passages([texts[index] for index in batch_indexes]),
        )
        print(f"Embedded {min(start + batch_size, len(missing))}/{len(missing)} new chunk(s)")

    print(
        f"Done: {len(missing)} new chunk(s) embedded, {len(stale_ids)} stale removed, "
        f"{len(desired_ids)} total from {source_count} document(s)."
    )
    print("Note: scanned/image-only PDFs need OCR before ingestion.")


if __name__ == "__main__":
    main()
