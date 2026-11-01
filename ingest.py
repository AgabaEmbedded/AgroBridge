"""Ingest documents into the two isolated knowledge bases.

Usage:
    python ingest.py                 # sync KB1 and KB2
    python ingest.py --kb KB1        # only agriculture
    python ingest.py --kb KB2        # only policy
    python ingest.py --drop-legacy   # also delete the old single-collection index

Chunks are content-addressed, so re-running only embeds new/changed chunks and removes
chunks whose source document was edited or deleted.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from services.config import settings
from services.document_processor import SUPPORTED_SUFFIXES, build_kb_records, sync_collection
from services.retrieval_service import get_client, get_collection

LEGACY_COLLECTION = "agrobridge_knowledge"


def ingest(kb: str) -> dict[str, int | str]:
    kb = kb.upper()
    folder = settings.documents_dir / kb
    if not folder.exists():
        print(f"{kb}: folder missing at {folder}")
        return {"kb": kb, "added": 0, "removed": 0, "metadata_updated": 0, "total": 0}

    records = build_kb_records(kb, folder)
    collection = get_collection(kb)
    if not records:
        print(f"{kb}: no extractable text found in {folder}")
        return {"kb": kb, "added": 0, "removed": 0, "metadata_updated": 0, "total": collection.count()}

    stats = sync_collection(collection, records)
    print(
        f"{kb}: +{stats['added']} new, -{stats['removed']} stale, "
        f"~{stats['metadata_updated']} metadata updated, {stats['total']} chunks total"
    )
    return {"kb": kb, **stats}


def _warn_flat_files() -> None:
    flat = [
        path
        for path in settings.documents_dir.glob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    ]
    if flat:
        print(
            "Note: files directly in documents/ are ignored. "
            "Move them into documents/KB1 or documents/KB2."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest AgroBridge KB1/KB2 documents.")
    parser.add_argument("--kb", choices=["all", "KB1", "KB2"], default="all")
    parser.add_argument(
        "--drop-legacy",
        action="store_true",
        help=f"Delete the pre-multi-agent '{LEGACY_COLLECTION}' collection",
    )
    args = parser.parse_args()

    _warn_flat_files()
    targets = ["KB1", "KB2"] if args.kb == "all" else [args.kb]
    for kb in targets:
        ingest(kb)

    if args.drop_legacy:
        client = get_client()
        names = {collection.name for collection in client.list_collections()}
        if LEGACY_COLLECTION in names:
            client.delete_collection(LEGACY_COLLECTION)
            print(f"Deleted legacy collection {LEGACY_COLLECTION}")


if __name__ == "__main__":
    main()
