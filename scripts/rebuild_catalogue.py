"""Rebuild metadata/document_catalogue.xlsx from metadata/sources.json.

Cheap path for routine catalogue refreshes: only PDFs whose recorded text count is low are
re-opened to refresh extraction stats. Also sets text/OCR status from sidecars.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "metadata"
DOCS = ROOT / "documents"


def quality(record: dict) -> str:
    if record.get("quality"):
        return record["quality"]
    text = f"{record.get('institution','')} {record.get('title','')}".lower()
    if any(w in text for w in ["ministry", "council", "federal", "nafdac", "afdb", "african union", "fao", "nasc", "arcn", "naerls", "budget office"]):
        return "official"
    if any(w in text for w in ["iita", "cimmyt", "ifdc", "university", "research", "cgiar", "aeson", "fara", "harvestplus"]):
        return "research"
    if any(w in text for w in ["actionaid", "commonwealth"]):
        return "secondary"
    return "unknown"


def geography(record: dict) -> str:
    if record.get("geography"):
        return record["geography"]
    text = f"{record.get('title','')} {record.get('institution','')}".lower()
    if "nigeria" in text or any(w in text for w in ["nasc", "naerls", "fmafs", "fmard", "arcn", "nigerian"]):
        return "Nigeria"
    if any(w in text for w in ["african union", "ecowas", "caadp", "malabo"]):
        return "Africa"
    return "Global"


def main() -> int:
    records = json.loads((META / "sources.json").read_text(encoding="utf-8"))
    for record in records:
        record["quality"] = quality(record)
        record["geography"] = geography(record)
        record["crop_relevance"] = record.get("topic", "")
        filename = record.get("filename")
        if not filename:
            continue
        path = ROOT / filename
        if not path.exists():
            continue
        sidecar = path.with_name(path.name + ".ocr.txt")
        if sidecar.exists():
            text = sidecar.read_text(encoding="utf-8", errors="ignore")
            record["text_chars"] = len(text)
            record["text_status"] = "ocr_text_sidecar"
            record["ocr_status"] = "completed" if len(text) > 200 else "failed"
            continue
        if (record.get("text_chars") or 0) < 100:
            try:
                reader = PdfReader(str(path))
                record["pages"] = len(reader.pages)
                record["text_chars"] = len(
                    "".join((page.extract_text() or "") for page in reader.pages)
                )
            except Exception:
                record["text_chars"] = 0
        record["text_status"] = (
            "extractable_text" if (record.get("text_chars") or 0) >= 100 else "none"
        )
        record["ocr_status"] = (
            "not_needed" if (record.get("text_chars") or 0) >= 100 else "required"
        )

    (META / "sources.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Catalogue"
    columns = [
        "Document ID", "Document Title", "Knowledge Base", "Category",
        "Issuing Institution", "Publication Year", "Effective Period", "Document Type",
        "Original Source URL", "Date Retrieved", "Source Quality", "Text Extraction",
        "OCR Status", "Policy/Document Status", "Crop Relevance",
        "Geographical Relevance", "Local Filename", "Short Description",
        "Verification Status", "SHA-256", "Pages", "Notes",
    ]
    sheet.append(columns)
    for record in sorted(records, key=lambda item: item["id"]):
        sheet.append([
            record.get("id"), record.get("title"), record.get("kb"), record.get("category"),
            record.get("institution"), record.get("year"), record.get("period"),
            record.get("doc_type"), record.get("url"), record.get("retrieved_at"),
            record.get("quality"), record.get("text_status"), record.get("ocr_status"),
            record.get("status"), record.get("crop_relevance"), record.get("geography"),
            record.get("filename", ""), record.get("description", ""),
            record.get("verification_status", ""), record.get("sha256", ""),
            record.get("pages"), record.get("notes", ""),
        ])
    header_fill = PatternFill("solid", fgColor="1F4E3D")
    header_font = Font(color="FFFFFF", bold=True)
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(wrap_text=True)
        cell.border = border
    widths = [14, 55, 10, 24, 38, 12, 16, 22, 55, 14, 18, 20, 14, 22, 30, 24, 62, 55, 22, 66, 8, 55]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = border
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    manual = workbook.create_sheet("Manual retrieval")
    manual.append(["Document ID", "Title", "KB", "Category", "Institution", "Source URL", "Reason"])
    for record in sorted(records, key=lambda item: item["id"]):
        if record.get("verification_status") == "manual_required":
            manual.append([
                record.get("id"), record.get("title"), record.get("kb"),
                record.get("category"), record.get("institution"), record.get("url"),
                record.get("notes", ""),
            ])

    summary = workbook.create_sheet("Summary")
    summary.append(["Metric", "Value"])
    summary.append(["Catalogue records", len(records)])
    summary.append(["Active PDFs", len(list(DOCS.rglob("*.pdf")))])
    summary.append(["Manual retrieval", sum(1 for r in records if r.get("verification_status") == "manual_required")])
    summary.append(["OCR sidecars", len(list(DOCS.rglob("*.ocr.txt")))])
    summary.append([])
    summary.append(["KB", "Category", "Records"])
    for (kb, category), count in sorted(Counter((r["kb"], r["category"]) for r in records).items()):
        summary.append([kb, category, count])
    for cell in summary[1]:
        cell.fill = header_fill
        cell.font = header_font
    for column, width in (("A", 34), ("B", 30), ("C", 14)):
        summary.column_dimensions[column].width = width

    workbook.save(META / "document_catalogue.xlsx")
    print(f"records={len(records)} active={len(list(DOCS.rglob('*.pdf')))}")
    print("low/no OCR:", [r["id"] for r in records if r.get("ocr_status") == "required"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
