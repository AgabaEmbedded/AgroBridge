"""Import manually downloaded documents into candidate_documents and documents.

- Classifies each PDF into KB1/KB2 and a category.
- Skips hash duplicates and the already-active Herd Health bulletin.
- Copies to candidate_documents/<KB>/<category>/ and documents/<KB>/<category>/.
- Runs OCR for image-only PDFs (PDFium + Windows OCR) and copies the sidecar to both trees.
- Appends metadata to metadata/sources.json; the catalogue is rebuilt by audit_extend_kb.py.
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

from pypdf import PdfReader

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Download docs"
CANDIDATES = ROOT / "candidate_documents"
DOCUMENTS = ROOT / "documents"
META = ROOT / "metadata"
OCR_PS = ROOT / "scripts" / "windows_ocr.ps1"

# filename: (kb, category, id, title, institution, year, status, quality, topic)
CLASSIFICATION: dict[str, tuple[str, str, str, str, str, int | None, str, str, str]] = {
    "Cassava P_D Catalogue_Final_English_Ritha Bumwe.pdf": ("KB1", "pests_diseases", "KB1-PD-009", "Pests and Diseases of Cassava: A Field Identification Guide", "International Institute of Tropical Agriculture (IITA)", 2025, "current", "research", "Cassava pests and diseases"),
    "Benisees-Production-and-Utilisation-in-Nigeria.pdf": ("KB1", "crop_production", "KB1-CP-011", "Beniseed Production and Utilisation in Nigeria (Extension Bulletin No. 154)", "NAERLS", None, "unknown", "official", "Beniseed"),
    "Bull-and-Ram-Fattening.pdf": ("KB1", "livestock_health", "KB1-LH-004", "Bull and Ram Fattening (Extension Bulletin No. 198)", "NAERLS", None, "unknown", "official", "Cattle; sheep"),
    "CASSAVA-Production-Processing-and-utilization.pdf": ("KB1", "crop_production", "KB1-CP-012", "Cassava Production, Processing and Utilization in Nigeria (Extension Bulletin No. 224)", "NAERLS", None, "unknown", "official", "Cassava"),
    "Construction-of-Multi-Purpose-Roaster.pdf": ("KB1", "mechanization", "KB1-ME-002", "Construction and Use of Multi-Purpose Roaster (Extension Bulletin No. 88)", "NAERLS", None, "historical", "official", "Farm equipment; processing"),
    "Control-of-Worms-in-Cattle-Sheep-and-Goats.pdf": ("KB1", "livestock_health", "KB1-LH-005", "Control of Worms in Cattle, Sheep and Goats (Extension Bulletin No. 172)", "NAERLS", None, "unknown", "official", "Livestock health"),
    "Duck-Production-in-Nigeria.pdf": ("KB1", "livestock_health", "KB1-LH-006", "Duck Production in Nigeria (Extension Bulletin No. 133)", "NAERLS", None, "unknown", "official", "Duck production"),
    "Economics-of-Aquaculture-Production.pdf": ("KB1", "aquaculture", "KB1-AQ-001", "Economics of Aquaculture Production (Extension Bulletin No. 107)", "NAERLS", None, "unknown", "official", "Aquaculture economics"),
    "Estimating-Farm-Machinery-Cost.pdf": ("KB1", "mechanization", "KB1-ME-003", "Estimating Farm Machinery Cost (Extension Bulletin No. 82)", "NAERLS", None, "historical", "official", "Farm machinery"),
    "Feed-Formulation-and-Feeding-Practices-in-Nigeria-Fish-Culture.pdf": ("KB1", "aquaculture", "KB1-AQ-002", "Feed Formulation and Feeding Practices in Nigeria Fish Culture (Extension Bulletin No. 152)", "NAERLS", None, "unknown", "official", "Aquaculture feed"),
    "Fish-Culture-in-Ponds.pdf": ("KB1", "aquaculture", "KB1-AQ-003", "Fish Culture in Ponds (Extension Bulletin No. 103)", "NAERLS", None, "unknown", "official", "Fish farming"),
    "Fish-Pond-Fertilization-Techniques.pdf": ("KB1", "aquaculture", "KB1-AQ-004", "Fish Pond Fertilization Techniques (Extension Bulletin No. 153)", "NAERLS", None, "unknown", "official", "Fish farming"),
    "Fish-Pond-Site-Selection-and-Construction.pdf": ("KB1", "aquaculture", "KB1-AQ-005", "Fish Pond Site Selection and Construction (Extension Bulletin No. 96)", "NAERLS", None, "unknown", "official", "Fish farming"),
    "Garlic-Production-Under-Irrigation.pdf": ("KB1", "water_management", "KB1-WM-002", "Garlic Production Under Irrigation (Extension Bulletin No. 205)", "NAERLS", None, "unknown", "official", "Irrigation; garlic"),
    "Harchery-Management-Practices-in-Poultry.pdf": ("KB1", "livestock_health", "KB1-LH-007", "Hatchery Management Practices in Poultry (Extension Bulletin No. 86)", "NAERLS", None, "unknown", "official", "Poultry"),
    "Heat-Tolerant-Tomato-Production-Under-Irrigation.pdf": ("KB1", "water_management", "KB1-WM-003", "Heat-Tolerant Tomato Production Under Irrigation (Extension Bulletin No. 242)", "NAERLS", 2016, "current", "official", "Irrigation; tomato"),
    "Herd-Health-Management-in-Farm-Animals.pdf": ("KB1", "livestock_health", "SKIP", "Herd Health Management in Farm Animals", "NAERLS", 2000, "historical", "official", "Livestock health"),
    "Improving-the-Performance-of-Local-Chikens.pdf": ("KB1", "livestock_health", "KB1-LH-008", "Improving the Performance of Local Chickens (Extension Bulletin No. 92)", "NAERLS", None, "unknown", "official", "Poultry"),
    "Integrated-Aquaculture-Technologies-for-Fish-Farmers.pdf": ("KB1", "aquaculture", "KB1-AQ-006", "Integrated Aquaculture Technologies for Fish Farmers (Extension Bulletin No. 229)", "NAERLS", 2013, "current", "official", "Aquaculture"),
    "Irrigated-Onion-Production-And-Management.pdf": ("KB1", "water_management", "KB1-WM-004", "Irrigated Onion Production and Management", "NAERLS", None, "unknown", "official", "Irrigation; onion"),
    "Irrigated-Pepper-Production.pdf": ("KB1", "water_management", "KB1-WM-005", "Irrigated Pepper Production (Extension Bulletin No. 240)", "NAERLS", 2016, "current", "official", "Irrigation; pepper"),
    "Leadership-and-Interpersonal-Skills.pdf": ("KB1", "extension", "KB1-EX-003", "Leadership and Interpersonal Skills (Extension Bulletin No. 81)", "NAERLS", None, "historical", "official", "Extension training"),
    "MAIZE-Production-Marketing-Processing-Utilization-In-Nigeria.pdf": ("KB1", "crop_production", "KB1-CP-013", "Maize Production, Marketing, Processing and Utilization in Nigeria (Extension Bulletin No. 217)", "NAERLS", None, "unknown", "official", "Maize"),
    "Major-Diseases-and-Pests-of-Forest-Trees-and-Their-Control-in-Nigeria.pdf": ("KB1", "pests_diseases", "KB1-PD-010", "Major Diseases and Pests of Forest Trees and Their Control in Nigeria (Extension Bulletin No. 178)", "NAERLS", None, "unknown", "official", "Forest tree pests"),
    "Management-of-Drugs-and-Veterinary-Equipment-on-the-Farm.pdf": ("KB1", "livestock_health", "KB1-LH-009", "Management of Drugs and Veterinary Equipment on the Farm (Extension Bulletin No. 145)", "NAERLS", None, "unknown", "official", "Livestock health"),
    "Onion-Productiona-and-Management-under-Irrigation.pdf": ("KB1", "water_management", "KB1-WM-006", "Onion Production and Management Under Irrigation (Extension Bulletin No. 204)", "NAERLS", None, "unknown", "official", "Irrigation; onion"),
    "Pepper-Production-Under-Irrigation.pdf": ("KB1", "water_management", "KB1-WM-007", "Pepper Production Under Irrigation (Extension Bulletin No. 206)", "NAERLS", None, "unknown", "official", "Irrigation; pepper"),
    "Preparation-Processing-and-Utilization-of-Fish-Products.pdf": ("KB1", "aquaculture", "KB1-AQ-007", "Preparation, Processing and Utilisation of Fish Products (Extension Bulletin No. 99)", "NAERLS", None, "unknown", "official", "Fish processing"),
    "Production-and-utilization-of-ogbono-Irvingia-Gabonensis.pdf": ("KB1", "crop_production", "KB1-CP-014", "Production and Utilization of Ogbono (Irvingia gabonensis) (Extension Bulletin No. 140)", "NAERLS", None, "unknown", "official", "Ogbono"),
    "Production-of-Gum-Arabic.pdf": ("KB1", "crop_production", "KB1-CP-015", "Production of Gum Arabic (Extension Bulletin No. 78)", "NAERLS", None, "unknown", "official", "Gum Arabic"),
    "Production-of-Lablab-in-Nigeria.pdf": ("KB1", "livestock_health", "KB1-LH-010", "Production of Lablab in Nigeria (Extension Bulletin No. 206)", "NAERLS", None, "unknown", "official", "Livestock feed"),
    "Restraining-Techniques-in-Farm-Animals.pdf": ("KB1", "livestock_health", "KB1-LH-011", "Restraining Techniques in Farm Animals (Extension Bulletin No. 147)", "NAERLS", None, "unknown", "official", "Livestock handling"),
    "Rice-Production-Processing-Utilization-and-Marketing-in-Nigeria.pdf": ("KB1", "crop_production", "SKIP", "Rice Production Bulletin", "NAERLS", None, "unknown", "official", "Rice"),
    "Rubber-Production-in-Nigeria.pdf": ("KB1", "crop_production", "KB1-CP-016", "Rubber Production in Nigeria (Extension Bulletin No. 213)", "NAERLS", None, "unknown", "official", "Rubber"),
    "Shikabrown-Production-and-Management.pdf": ("KB1", "livestock_health", "KB1-LH-012", "Shikabrown Chicken: Production and Management (Extension Bulletin No. 231)", "NAERLS", 2014, "current", "official", "Poultry"),
    "Snail-Production-Techniques-in-Nigeria.pdf": ("KB1", "livestock_health", "KB1-LH-013", "Snail Production Techniques in Nigeria (Extension Bulletin No. 108)", "NAERLS", None, "unknown", "official", "Snail production"),
    "The-Production-of-Guinea-Fowl-in-Nigeria.pdf": ("KB1", "livestock_health", "KB1-LH-014", "The Production of Guinea Fowl in Nigeria (Extension Bulletin No. 207)", "NAERLS", None, "unknown", "official", "Poultry"),
    "Tomato-Processing-and-Utilization.pdf": ("KB1", "crop_production", "KB1-CP-017", "Tomato Processing and Utilization (Extension Bulletin No. 241)", "NAERLS", 2016, "current", "official", "Tomato processing"),
    "Transporting-Fish-for-Culture.pdf": ("KB1", "aquaculture", "KB1-AQ-008", "Transporting Fish for Culture (Extension Bulletin No. 151)", "NAERLS", None, "unknown", "official", "Aquaculture"),
    "Water-Quality-Management-in-Fish-Culture.pdf": ("KB1", "aquaculture", "KB1-AQ-009", "Water Quality Management in Fish Culture (Extension Bulletin No. 98)", "NAERLS", None, "unknown", "official", "Aquaculture water"),
    "2025-Wet-Season-Agricultural-Performance-in-Nigeria.pdf": ("KB2", "budgets_statistics", "SKIP", "2025 Wet Season Performance", "NAERLS", 2025, "current", "official", "Statistics"),
    "ANRIN-PROCESSING-MANUAL-Corrected_0332571.pdf": ("KB1", "crop_production", "KB1-CP-018", "Processing, Preservation and Utilization of Produce from Homestead Gardens (ANRIN Manual)", "FMARD / World Bank ANRIN", None, "unknown", "official", "Crop processing; homestead gardens"),
    "Agric-Promotion-Policy_Green-Alternative_2016-2020_Final.pdf": ("KB2", "national_policies", "SKIP", "Agricultural Promotion Policy", "FMARD", 2016, "expired", "official", "Policy"),
    "FINALIZED-NAGS-2.0-ESSA-Document.pdf": ("KB2", "implementation_reports", "SKIP", "NAGS 2.0 ESSA", "FMAFS", 2025, "current", "official", "Programme"),
    "FMAFS-Road-Map-Strategies.pdf": ("KB2", "national_policies", "SKIP", "FMAFS priorities", "FMAFS", 2024, "current", "official", "Policy"),
    "Finalized_Cleared-NAGS-AP-FA-ESMP-TABLE.pdf": ("KB2", "implementation_reports", "KB2-IR-009", "NAGS-AP ESMP Template (Financing Agreement Annex)", "Federal Ministry of Finance; FMAFS", None, "current", "official", "Programme safeguards"),
    "GENERIC-HOMESTEAD-GARDEN-MANUAL.pdf": ("KB1", "crop_production", "KB1-CP-019", "Generic Homestead Garden Manual", "World Bank / FMARD", None, "unknown", "official", "Homestead gardening; poultry; small ruminants"),
    "HarvestPlus-Recipe-Book.pdf": ("KB1", "extension", "KB1-EX-004", "Biofortified Crops on My Plate: A National Biofortification Recipe Book", "HarvestPlus Nigeria", 2023, "current", "research", "Biofortified crops; nutrition"),
    "Key-Findings-NFCMS_Final-April-2024.pdf": ("KB2", "implementation_reports", "SKIP", "NFCMS key findings", "FMOH/FMARD", 2024, "current", "official", "Nutrition survey"),
    "NATIP_Implenetation_Plan-6years-Copy.pdf": ("KB2", "national_policies", "SKIP", "NATIP action plan", "FMAFS", 2023, "current", "official", "Policy"),
    "NFCMS-Report-Final_Preliminary-2022.pdf": ("KB2", "implementation_reports", "SKIP", "NFCMS preliminary", "FMOH/FMARD", 2022, "historical", "official", "Nutrition survey"),
    "NLTP-IP-DOC.pdf": ("KB2", "national_policies", "KB2-NP-010", "National Livestock Transformation Plan Implementation Plan", "Federal Ministry of Agriculture and Rural Development", None, "unknown", "official", "Livestock policy"),
    "National-Agricultural-Technology-and-Innovation-Policy-NATIP-2022-2027.pdf": ("KB2", "national_policies", "SKIP", "NATIP", "FMAFS", 2022, "current", "official", "Policy"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:70]


def pdf_stats(path: Path) -> tuple[int, int]:
    reader = PdfReader(str(path))
    return len(reader.pages), len("".join((p.extract_text() or "") for p in reader.pages))


def ocr_pdf(pdf: Path) -> str:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(pdf))
    pages = []
    for index in range(len(document)):
        image = document[index].render(scale=1.6).to_pil()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / f"page-{index + 1}.png"
            image.save(path)
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(OCR_PS), "-Path", str(path.resolve())],
                capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=180,
            )
        if result.stdout.strip():
            pages.append(f"[page {index + 1}]\n{result.stdout.strip()}")
    return "\n\n".join(pages)


def main() -> int:
    sources = json.loads((META / "sources.json").read_text(encoding="utf-8"))
    known_hashes = {r["sha256"] for r in sources if r.get("sha256")}
    for tree in (DOCUMENTS, CANDIDATES):
        for path in tree.rglob("*.pdf"):
            known_hashes.add(sha256(path))
    known_titles = {(r.get("title") or "").lower() for r in sources}

    added = []
    skipped = []
    pdfs = sorted(SOURCE.rglob("*.pdf"))
    for path in pdfs:
        info = CLASSIFICATION.get(path.name)
        if not info:
            skipped.append((path.name, "no classification rule"))
            continue
        kb, category, doc_id, title, institution, year, status, quality, topic = info
        if doc_id == "SKIP":
            skipped.append((path.name, "duplicate of active document"))
            continue
        if title.lower() in known_titles:
            skipped.append((path.name, "duplicate title"))
            continue
        digest = sha256(path)
        if digest in known_hashes:
            skipped.append((path.name, "duplicate hash"))
            continue
        if doc_id in {r["id"] for r in sources}:
            skipped.append((path.name, f"duplicate id {doc_id}"))
            continue

        filename = f"{doc_id}_{slugify(title)}.pdf"
        candidate_target = CANDIDATES / kb / category / filename
        document_target = DOCUMENTS / kb / category / filename
        candidate_target.parent.mkdir(parents=True, exist_ok=True)
        document_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, candidate_target)
        shutil.copy2(path, document_target)
        pages, chars = pdf_stats(document_target)
        sidecar = document_target.with_name(document_target.name + ".ocr.txt")
        if chars < 100:
            text = ocr_pdf(document_target)
            if text.strip():
                sidecar.write_text(text + "\n", encoding="utf-8")
                shutil.copy2(sidecar, candidate_target.with_name(candidate_target.name + ".ocr.txt"))
                chars = len(text)
        record = {
            "id": doc_id,
            "title": title,
            "kb": kb,
            "category": category,
            "institution": institution,
            "year": year,
            "period": None,
            "doc_type": "Extension bulletin" if "Extension Bulletin" in title or institution == "NAERLS" else "Technical document",
            "url": "",
            "retrieved_at": date.today().isoformat(),
            "status": status,
            "quality": quality,
            "topic": topic,
            "geography": "Nigeria",
            "description": f"Manually downloaded document: {title}.",
            "filename": document_target.relative_to(ROOT).as_posix(),
            "sha256": digest,
            "pages": pages,
            "text_chars": chars,
            "verification_status": "verified",
            "notes": "Imported from Download docs.",
        }
        sources.append(record)
        added.append(doc_id)
        known_hashes.add(digest)
        known_titles.add(title.lower())

    (META / "sources.json").write_text(json.dumps(sources, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"imported {len(added)}: {added}")
    print(f"skipped {len(skipped)}:")
    for name, reason in skipped:
        print(f"  {name} — {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
