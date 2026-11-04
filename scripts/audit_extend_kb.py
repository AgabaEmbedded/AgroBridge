"""Audit and extend the active AgroBridge knowledge base.

- Audits documents/KB1 and documents/KB2 (opens PDFs, checks extractable text, hashes).
- Promotes the already-downloaded candidate PDFs into the active KB without deleting them.
- Adds newly downloaded gap-filling documents from .tmp/new_docs.
- Runs OCR (Windows.Media.Ocr via scripts/windows_ocr.ps1) for scanned PDFs and saves
  sidecar `.ocr.txt` files next to the originals.
- Updates the existing metadata/document_catalogue.xlsx and metadata/sources.json.

No vector-DB ingestion and no application-code changes.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import warnings
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from pypdf import PdfReader

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ROOT / "documents"
CANDIDATES = ROOT / "candidate_documents"
META = ROOT / "metadata"
NEW_DOCS = ROOT / ".tmp" / "new_docs"
OCR_PS = ROOT / "scripts" / "windows_ocr.ps1"

KB1_CATEGORIES = [
    "crop_production",
    "seeds_varieties",
    "soil_fertilizer",
    "pests_diseases",
    "water_management",
    "climate_environment",
    "mechanization",
    "extension",
    "research_statistics",
    "livestock_health",
]
KB2_CATEGORIES = [
    "national_policies",
    "laws_regulations",
    "institutional_mandates",
    "implementation_reports",
    "budgets_statistics",
    "international_frameworks",
]

# Documents acquired for the identified gaps. Only files that validate as PDFs are added.
NEW_SOURCES: list[dict[str, Any]] = [
    {
        "id": "KB1-SV-003",
        "file": "NASC_Varieties_2026.pdf",
        "title": "Crop Varieties Released and Registered in Nigeria (Updated April 2026)",
        "kb": "KB1",
        "category": "seeds_varieties",
        "institution": "National Agricultural Seeds Council (NASC)",
        "year": 2026,
        "period": None,
        "doc_type": "Variety catalogue",
        "url": "https://nacgrab.gov.ng/wp-content/uploads/2026/08/Varieties-Released-Catalogue-updated-April-2026.pdf",
        "status": "current",
        "quality": "official",
        "topic": "Maize; rice; cassava varieties",
        "geography": "Nigeria",
        "description": "Current catalogue of crop varieties released and registered in Nigeria.",
    },
    {
        "id": "KB1-SV-004",
        "file": "NASC_NSRM_2025.pdf",
        "title": "National Seed Roadmap Dashboard 2025",
        "kb": "KB1",
        "category": "seeds_varieties",
        "institution": "National Agricultural Seeds Council (NASC)",
        "year": 2026,
        "period": "2021-2025",
        "doc_type": "Performance dashboard",
        "url": "https://seedcouncil.gov.ng/wp-content/uploads/2026/08/2025-NSRM-Dashboard_Final-Visual_June2026-1.pdf",
        "status": "current",
        "quality": "official",
        "topic": "Seed system performance",
        "geography": "Nigeria",
        "description": "Seed-system performance indicators for the National Seed Roadmap.",
    },
    {
        "id": "KB1-SV-005",
        "file": "CSP_Variety_Release_Baseline.pdf",
        "title": "Crop Variety Release and Registration in Nigeria: Baseline Assessment",
        "kb": "KB1",
        "category": "seeds_varieties",
        "institution": "Crop Science Partnership (CSP) Nigeria",
        "year": None,
        "period": None,
        "doc_type": "Assessment report",
        "url": "https://csp-nigeria.org/wp-content/uploads/2022/03/variety-release-baseline-assessment-1.pdf",
        "status": "historical",
        "quality": "research",
        "topic": "Maize; rice; cassava; tomato varieties",
        "geography": "Nigeria",
        "description": "Assessment of variety release and registration systems for maize, rice, cassava and tomato.",
    },
    {
        "id": "KB1-CP-010",
        "file": "NAERLS_Rice_Bulletin230.pdf",
        "title": "Rice Production, Processing, Utilization and Marketing in Nigeria (Extension Bulletin No. 230)",
        "kb": "KB1",
        "category": "crop_production",
        "institution": "National Agricultural Extension and Research Liaison Services (NAERLS)",
        "year": None,
        "period": None,
        "doc_type": "Extension bulletin",
        "url": "https://naerls.gov.ng/wp-content/uploads/2022/11/Rice-Production-Processing-Utilization-and-Marketing-in-Nigeria.pdf",
        "status": "current",
        "quality": "official",
        "topic": "Rice",
        "geography": "Nigeria",
        "description": "NAERLS extension bulletin on rice production, processing and marketing.",
    },
    {
        "id": "KB1-WM-001",
        "file": "FAO_Growing_Lowland_Rice.pdf",
        "title": "Growing Lowland Rice: A Production Handbook",
        "kb": "KB1",
        "category": "water_management",
        "institution": "Food and Agriculture Organization (FAO)",
        "year": 2008,
        "period": None,
        "doc_type": "Production handbook",
        "url": "https://www.fao.org/fileadmin/user_upload/ivc/docs/Growing%20lowland%20rice_%20production%20handbook_prepress%20final%20version_19-05-08_low%20res.pdf",
        "status": "historical",
        "quality": "official",
        "topic": "Irrigated/lowland rice; water management",
        "geography": "Nigeria",
        "description": "Handbook on lowland rice production, water and irrigation practices.",
    },
    {
        "id": "KB1-SF-002",
        "file": "FARA_NiSIS_Soil.pdf",
        "title": "Climate Smart Agriculture and Soil Fertility Mapping: Nigeria Soil Information Service Pilot",
        "kb": "KB1",
        "category": "soil_fertilizer",
        "institution": "Nigeria Soil Information Service (NiSIS); FARA",
        "year": 2023,
        "period": None,
        "doc_type": "Research article",
        "url": "https://library.faraafrica.org/storage/2023/04/FRR-Vol-754671-676.pdf",
        "status": "current",
        "quality": "research",
        "topic": "Soil fertility; soil information",
        "geography": "Nigeria",
        "description": "Pilot soil fertility mapping and soil information service for Nigeria.",
    },
    {
        "id": "KB1-RS-003",
        "file": "Hybrid_Maize_Adoption.pdf",
        "title": "Hybrid Maize Adoption Determinants in Northern Nigeria: A Gendered Perspective",
        "kb": "KB1",
        "category": "research_statistics",
        "institution": "SciVision Publishers (journal article)",
        "year": 2024,
        "period": None,
        "doc_type": "Research article",
        "url": "https://www.scivisionpub.com/pdfs/hybrid-maize-adoption-determinants-in-northern-nigeria-a-gendered-perspective-3123.pdf",
        "status": "current",
        "quality": "research",
        "topic": "Maize; technology adoption",
        "geography": "Nigeria",
        "description": "Field evidence on determinants of hybrid maize adoption in northern Nigeria.",
    },
    {
        "id": "KB2-IR-005",
        "file": "AfDB_NAGS_PCR_2024.pdf",
        "title": "Support to National Agriculture Growth Scheme - Agro-Pocket: Project Completion Report",
        "kb": "KB2",
        "category": "implementation_reports",
        "institution": "African Development Bank (AfDB); Federal Government of Nigeria",
        "year": 2024,
        "period": None,
        "doc_type": "Project completion report",
        "url": "https://www.afdb.org/sites/default/files/documents/projects-and-operations/nigeria-_support_to_national_agriculture_growth_scheme_-_agro-pocket-_p-ng-aag-016-pcr-decembre_2024.pdf",
        "status": "current",
        "quality": "official",
        "topic": "Programme implementation",
        "geography": "Nigeria",
        "description": "Completion report for the Agro-Pocket agriculture growth programme.",
    },
    {
        "id": "KB2-IR-006",
        "file": "FAO_Inputs_Survey_2024.pdf",
        "title": "Nigeria: Agricultural Inputs Survey, Round 2 (August 2024)",
        "kb": "KB2",
        "category": "implementation_reports",
        "institution": "Food and Agriculture Organization (FAO) DIEM",
        "year": 2024,
        "period": None,
        "doc_type": "Survey report",
        "url": "https://reliefweb.int/attachments/85598b3a-a932-4fd9-af4b-2a0dd78e275a/cd5053en.pdf",
        "status": "current",
        "quality": "official",
        "topic": "Seed and fertilizer access",
        "geography": "Nigeria",
        "description": "Survey evidence on agricultural input access and constraints.",
    },
    {
        "id": "KB2-IR-007",
        "file": "DLEC_Extension_Assessment.pdf",
        "title": "Nigeria In-Depth Assessment of Agricultural Extension",
        "kb": "KB2",
        "category": "implementation_reports",
        "institution": "Digital Green / USAID DLEC",
        "year": 2024,
        "period": None,
        "doc_type": "Assessment report",
        "url": "https://digitalgreen.org/wp-content/uploads/2024/07/Nigeria-In-Depth-Assessment.pdf",
        "status": "current",
        "quality": "research",
        "topic": "Extension delivery",
        "geography": "Nigeria",
        "description": "Assessment of agricultural extension coverage, delivery and digital advisory models.",
    },
    {
        "id": "KB2-BS-004",
        "file": "WB_Nigeria_Irrigation_Audit.pdf",
        "title": "Transforming Irrigation Management in Nigeria: Audited Financial Statement",
        "kb": "KB2",
        "category": "budgets_statistics",
        "institution": "World Bank; Federal Government of Nigeria",
        "year": 2021,
        "period": None,
        "doc_type": "Audited financial statement",
        "url": "https://documents1.worldbank.org/curated/en/394781628549164072/pdf/Nigeria-AFRICA-WEST-P123112-Transforming-Irrigation-Management-in-Nigeria-Audited-Financial-Statement.pdf",
        "status": "historical",
        "quality": "official",
        "topic": "Irrigation expenditure",
        "geography": "Nigeria",
        "description": "Project financial statements showing irrigation programme expenditure.",
    },
    {
        "id": "KB2-BS-005",
        "file": "NAERLS_2024_Performance.pdf",
        "title": "2024 Wet Season Agricultural Performance in Nigeria: National Report",
        "kb": "KB2",
        "category": "budgets_statistics",
        "institution": "NAERLS; Federal Ministry of Agriculture and Food Security",
        "year": 2024,
        "period": "2024 wet season",
        "doc_type": "Agricultural performance report",
        "url": "https://productivity.gov.ng/wp-content/uploads/2025/07/Year-2024-Agricultural-Productivity-Survey-APS-National-Report_.pdf",
        "status": "current",
        "quality": "official",
        "topic": "Crop production statistics",
        "geography": "Nigeria",
        "description": "Official wet-season production, yield and regional performance report.",
    },
    {
        "id": "KB2-IF-006",
        "file": "WB_Uganda_AgPER_2019.pdf",
        "title": "Uganda Agriculture Sector Public Expenditure Review",
        "kb": "KB2",
        "category": "international_frameworks",
        "institution": "World Bank",
        "year": 2019,
        "period": None,
        "doc_type": "Public expenditure review",
        "url": "https://documents1.worldbank.org/curated/en/891951570544230412/pdf/Uganda-Agriculture-Sector-Public-Expenditure-Review.pdf",
        "status": "historical",
        "quality": "research",
        "topic": "Agricultural public expenditure (comparator)",
        "geography": "Uganda (global comparator)",
        "description": "Comparator review of agricultural public spending and budget performance.",
    },
]

EXISTING_SOURCES: dict[str, dict[str, Any]] = {
    "19784_Prevention and control of animal diseases.pdf": {
        "id": "KB1-LH-001",
        "title": "Prevention and Control of Farm Animal Diseases",
        "category": "livestock_health",
        "institution": "Unknown",
        "year": None,
        "doc_type": "Technical note",
        "quality": "unknown",
        "topic": "Livestock disease control (retained for voice assistant)",
        "geography": "Unknown",
        "status": "unknown",
        "description": "Short guide to animal disease control methods; publisher not identifiable from the file.",
    },
    "Farm-Animal-Diseases-final-7.4.2011.pdf": {
        "id": "KB1-LH-002",
        "title": "Code of Practice No. 7 of 2011: Farm Animal Diseases Epidemiology and Control Guidelines",
        "category": "livestock_health",
        "institution": "Federal Republic of Nigeria (Code of Practice)",
        "year": 2011,
        "doc_type": "Code of practice",
        "quality": "official",
        "topic": "Livestock diseases (retained for voice assistant)",
        "geography": "Nigeria",
        "status": "historical",
        "description": "National code of practice for farm animal disease epidemiology and control.",
    },
    "Herd-Health-Management-in-Farm-Animals.pdf": {
        "id": "KB1-LH-003",
        "title": "Herd Health Management in Farm Animals (NAERLS Extension Bulletin No. 198)",
        "category": "livestock_health",
        "institution": "National Agricultural Extension and Research Liaison Services (NAERLS)",
        "year": 2000,
        "doc_type": "Extension bulletin",
        "quality": "official",
        "topic": "Livestock health (retained for voice assistant)",
        "geography": "Nigeria",
        "status": "historical",
        "description": "NAERLS extension bulletin on herd health management.",
    },
    "crop-pest-and-diseases-managment.pdf": {
        "id": "KB1-PD-008",
        "title": "Guide on Crop Pest and Diseases Management",
        "category": "pests_diseases",
        "institution": "Institute of Agricultural Research and Training, Obafemi Awolowo University",
        "year": None,
        "doc_type": "Extension guide",
        "quality": "research",
        "topic": "Crop pests and diseases",
        "geography": "Nigeria",
        "status": "unknown",
        "description": "Scanned IAR&T guide to crop pest and disease management; OCR text sidecar produced.",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pdf_text(path: Path) -> tuple[int, int]:
    reader = PdfReader(str(path))
    text = "".join((page.extract_text() or "") for page in reader.pages)
    return len(reader.pages), len(text)


def slugify(value: str, max_length: int = 70) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:max_length].strip("-") or "document"


def infer_quality(institution: str) -> str:
    text = (institution or "").lower()
    if any(word in text for word in ["actionaid", "commonwealth", "world bank"]):
        return "secondary" if "world bank" not in text else "research"
    if any(word in text for word in ["iita", "cimmyt", "ifdc", "university", "research institute", "cgiar", "aeson", "fara"]):
        return "research"
    if any(word in text for word in ["ministry", "council", "budget office", "federal", "nafdac", "afdb", "african union", "fao", "nasc", "arcn", "naerls"]):
        return "official"
    return "unknown"


def infer_geography(record: dict[str, Any]) -> str:
    if record.get("geography"):
        return record["geography"]
    blob = f"{record.get('title','')} {record.get('institution','')}".lower()
    if "nigeria" in blob or any(word in blob for word in ["nasc", "naerls", "fmafs", "fmard", "arcn", "nigerian"]):
        return "Nigeria"
    if any(word in blob for word in ["african union", "au ", "ecowas", "caadp", "malabo"]):
        return "Africa"
    return "Global"


def ocr_pdf(pdf: Path, sidecar: Path) -> tuple[int, int]:
    if sidecar.exists():
        text = sidecar.read_text(encoding="utf-8", errors="ignore")
        return text.count("[page "), len(text)
    try:
        import pypdfium2 as pdfium
    except Exception:
        return 0, 0
    document = pdfium.PdfDocument(str(pdf))
    page_texts: list[str] = []
    for index in range(len(document)):
        page = document[index]
        image = page.render(scale=1.6).to_pil()
        with tempfile.TemporaryDirectory() as td:
            image_path = Path(td) / f"page-{index + 1}.png"
            image.save(image_path)
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(OCR_PS),
                    "-Path",
                    str(image_path.resolve()),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=180,
            )
        if result.stdout.strip():
            page_texts.append(f"[page {index + 1}]\n{result.stdout.strip()}")
    text = "\n\n".join(page_texts)
    if text.strip():
        sidecar.write_text(text + "\n", encoding="utf-8")
    return len(page_texts), len(text)


def catalogue_row(record: dict[str, Any]) -> list[Any]:
    return [
        record.get("id"),
        record.get("title"),
        record.get("kb"),
        record.get("category"),
        record.get("institution"),
        record.get("year"),
        record.get("period"),
        record.get("doc_type"),
        record.get("url"),
        record.get("retrieved_at") or date.today().isoformat(),
        record.get("quality") or record.get("source_quality") or "unknown",
        record.get("text_status") or "",
        record.get("ocr_status") or "",
        record.get("status", "unknown"),
        record.get("topic") or record.get("crop_relevance") or "",
        record.get("geography") or "Unknown",
        record.get("filename") or "",
        record.get("description", ""),
        record.get("verification_status", ""),
        record.get("sha256", ""),
        record.get("pages"),
        record.get("notes", ""),
    ]


def main() -> int:
    sources = json.loads((META / "sources.json").read_text(encoding="utf-8"))
    active_hashes: dict[str, str] = {}
    for existing in DOCUMENTS.rglob("*.pdf"):
        active_hashes[sha256(existing)] = existing.relative_to(ROOT).as_posix()
    records: list[dict[str, Any]] = []

    # 1. Promote candidate PDFs into the active KB (copy, never delete originals).
    for record in sources:
        filename = record.get("filename")
        if not filename:
            records.append(record)
            continue
        active_path = ROOT / filename
        if active_path.exists():
            digest = sha256(active_path)
            canonical = active_hashes.get(digest)
            if canonical and canonical != filename:
                record["filename"] = canonical
                record["notes"] = (record.get("notes", "") + " Duplicate remapped to active copy.").strip()
            records.append(record)
            continue
        source = CANDIDATES / filename
        if not source.exists():
            records.append(record)
            continue
        digest = sha256(source)
        if digest in active_hashes:
            record["filename"] = active_hashes[digest]
            record["notes"] = (record.get("notes", "") + " Duplicate content already active.").strip()
            records.append(record)
            continue
        target = DOCUMENTS / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        active_hashes[digest] = target.relative_to(ROOT).as_posix()
        record["filename"] = target.relative_to(ROOT).as_posix()
        records.append(record)

    # 2. Add new gap-filling documents.
    for source in NEW_SOURCES:
        path = NEW_DOCS / source["file"]
        if not path.exists():
            continue
        try:
            PdfReader(str(path))
        except Exception:
            continue
        digest = sha256(path)
        if digest in active_hashes:
            continue
        target = DOCUMENTS / source["kb"] / source["category"] / f"{source['id']}_{slugify(source['title'])}.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        active_hashes[digest] = target.relative_to(ROOT).as_posix()
        pages, chars = pdf_text(target)
        records.append(
            {
                "id": source["id"],
                "title": source["title"],
                "kb": source["kb"],
                "category": source["category"],
                "institution": source["institution"],
                "year": source["year"],
                "period": source["period"],
                "doc_type": source["doc_type"],
                "url": source["url"],
                "retrieved_at": date.today().isoformat(),
                "status": source["status"],
                "quality": source["quality"],
                "topic": source["topic"],
                "geography": source["geography"],
                "description": source["description"],
                "filename": target.relative_to(ROOT).as_posix(),
                "sha256": digest,
                "pages": pages,
                "text_chars": chars,
                "verification_status": "verified",
                "notes": "New gap-filling document.",
            }
        )

    # 3. Add legacy active documents not yet represented.
    for path in sorted(DOCUMENTS.rglob("*.pdf")):
        digest = sha256(path)
        if digest in active_hashes:
            continue
        relative = path.relative_to(DOCUMENTS).as_posix()
        info = EXISTING_SOURCES.get(path.name, {})
        pages, chars = pdf_text(path)
        record = {
            "id": info.get("id", f"KB1-LEG-{len(records)+1:03d}"),
            "title": info.get("title", path.stem.replace("-", " ").replace("_", " ")),
            "kb": path.relative_to(DOCUMENTS).parts[0],
            "category": info.get("category", "livestock_health"),
            "institution": info.get("institution", "Unknown"),
            "year": info.get("year"),
            "period": None,
            "doc_type": info.get("doc_type", "Document"),
            "url": "",
            "retrieved_at": date.fromtimestamp(path.stat().st_mtime).isoformat(),
            "status": info.get("status", "unknown"),
            "quality": info.get("quality", "unknown"),
            "topic": info.get("topic", ""),
            "geography": info.get("geography", "Unknown"),
            "description": info.get("description", ""),
            "filename": path.relative_to(ROOT).as_posix(),
            "sha256": digest,
            "pages": pages,
            "text_chars": chars,
            "verification_status": "verified" if chars else "downloaded_unverified",
            "notes": "Pre-existing active document.",
        }
        active_hashes[digest] = record["filename"]
        records.append(record)

    # 4. OCR every active PDF that has no usable text.
    ocr_completed = []
    ocr_failed = []
    for record in records:
        filename = record.get("filename")
        if not filename or not filename.startswith("documents/"):
            continue
        path = ROOT / filename
        if not path.exists() or path.suffix.lower() != ".pdf":
            continue
        try:
            pages, chars = pdf_text(path)
        except Exception:
            record["verification_status"] = "rejected_invalid"
            continue
        record["pages"] = pages
        record["text_chars"] = chars
        sidecar = path.with_name(path.name + ".ocr.txt")
        record["quality"] = record.get("quality") or infer_quality(record.get("institution", ""))
        record["geography"] = infer_geography(record)
        record["crop_relevance"] = record.get("topic", "")

        if chars >= 100:
            record["text_status"] = "extractable_text"
            record["ocr_status"] = "not_needed"
            continue
        if sidecar.exists():
            text = sidecar.read_text(encoding="utf-8", errors="ignore")
            record["text_chars"] = len(text)
            record["text_status"] = "ocr_text_sidecar"
            record["ocr_status"] = "completed" if len(text) > 200 else "failed"
            if record["ocr_status"] == "completed":
                ocr_completed.append(record["id"])
            continue
        if OCR_PS.exists():
            try:
                images, ocr_chars = ocr_pdf(path, sidecar)
            except Exception:
                images, ocr_chars = 0, 0
            record["text_chars"] = ocr_chars
            if ocr_chars > 200:
                record["text_status"] = "ocr_text_sidecar"
                record["ocr_status"] = "completed"
                ocr_completed.append(record["id"])
            else:
                record["text_status"] = "none"
                record["ocr_status"] = "failed"
                ocr_failed.append(record["id"])
        else:
            record["text_status"] = "none"
            record["ocr_status"] = "required"

    # 5. Write catalogue and sources.
    (META / "sources.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Catalogue"
    columns = [
        "Document ID",
        "Document Title",
        "Knowledge Base",
        "Category",
        "Issuing Institution",
        "Publication Year",
        "Effective Period",
        "Document Type",
        "Original Source URL",
        "Date Retrieved",
        "Source Quality",
        "Text Extraction",
        "OCR Status",
        "Policy/Document Status",
        "Crop Relevance",
        "Geographical Relevance",
        "Local Filename",
        "Short Description",
        "Verification Status",
        "SHA-256",
        "Pages",
        "Notes",
    ]
    sheet.append(columns)
    for record in sorted(records, key=lambda item: item.get("id", "")):
        sheet.append(catalogue_row(record))

    header_fill = PatternFill("solid", fgColor="1F4E3D")
    header_font = Font(color="FFFFFF", bold=True)
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = border
    widths = [14, 55, 10, 24, 38, 12, 16, 22, 55, 14, 18, 20, 14, 22, 30, 24, 60, 55, 22, 66, 8, 55]
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
    for record in sorted(records, key=lambda item: item.get("id", "")):
        if record.get("verification_status") == "manual_required":
            manual.append(
                [
                    record.get("id"),
                    record.get("title"),
                    record.get("kb"),
                    record.get("category"),
                    record.get("institution"),
                    record.get("url"),
                    record.get("notes", ""),
                ]
            )

    summary = workbook.create_sheet("Summary")
    summary.append(["Metric", "Value"])
    summary.append(["Sources declared", len(records)])
    summary.append(["Downloaded/active", sum(1 for r in records if r.get("filename"))])
    summary.append(["Manual retrieval", sum(1 for r in records if r.get("verification_status") == "manual_required")])
    summary.append(["OCR completed", len(ocr_completed)])
    summary.append(["OCR failed", len(ocr_failed)])
    summary.append([])
    summary.append(["KB", "Category", "Active", "Manual"])
    categories = sorted({(r.get("kb"), r.get("category")) for r in records})
    for kb, category in categories:
        subset = [r for r in records if r.get("kb") == kb and r.get("category") == category]
        summary.append(
            [
                kb,
                category,
                sum(1 for r in subset if r.get("filename")),
                sum(1 for r in subset if r.get("verification_status") == "manual_required"),
            ]
        )
    for cell in summary[1]:
        cell.fill = header_fill
        cell.font = header_font
    summary.column_dimensions["A"].width = 32
    summary.column_dimensions["B"].width = 32
    summary.column_dimensions["C"].width = 14
    summary.column_dimensions["D"].width = 14

    catalogue = META / "document_catalogue.xlsx"
    workbook.save(catalogue)

    new_count = sum(1 for record in records if str(record.get("notes", "")).startswith("New gap-filling"))
    report = [
        "# Knowledge base gap-filling and quality audit",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        f"- Existing active documents audited: {len(EXISTING_SOURCES)}",
        f"- New documents added: {new_count}",
        f"- Total active catalogue records: {len(records)}",
        f"- OCR completed: {len(ocr_completed)} ({', '.join(ocr_completed)})",
        f"- OCR failed: {len(ocr_failed)} ({', '.join(ocr_failed)})",
        "",
        "## Remaining gaps",
        "- Some current policy implementation reports and budget release data remain limited to project-level evidence.",
        "- State-level ADP reports were not acquired in this pass.",
        "- NBS National Agricultural Sample Survey 2023 and NAERLS mandate remain manual-retrieval items.",
        "",
        f"Catalogue: `{catalogue.relative_to(ROOT).as_posix()}`",
        f"Sources: `metadata/sources.json`",
    ]
    (META / "kb_audit_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"active files: {len(list(DOCUMENTS.rglob('*.pdf')))}")
    print(f"records: {len(records)} | new: {new_count} | OCR completed: {len(ocr_completed)} failed: {len(ocr_failed)}")
    print(f"catalogue: {catalogue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
