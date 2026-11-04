"""Acquire, verify and catalogue AgroBridge candidate documents.

This is a document-acquisition tool: it does not touch application code or ingest into Chroma.
Run from the project root:

    python scripts/acquire_documents.py            # download/SKIP existing, rebuild catalogue
    python scripts/acquire_documents.py --dry-run  # catalogue only, no network

Outputs:
    candidate_documents/KB1/<category>/*.pdf
    candidate_documents/KB2/<category>/*.pdf
    metadata/document_catalogue.xlsx
    metadata/sources.json
    metadata/acquisition_report.md
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
import warnings
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from pypdf import PdfReader

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "candidate_documents"
METADATA = ROOT / "metadata"

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
]
KB2_CATEGORIES = [
    "national_policies",
    "laws_regulations",
    "institutional_mandates",
    "implementation_reports",
    "budgets_statistics",
    "international_frameworks",
]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Each entry is a curator-declared source with metadata supplied from the document itself or
# the issuing institution's page. `year=None` / `period=None` means "not verified" — we do not
# invent values. `manual=True` entries are recorded as requiring manual retrieval.
SOURCES: list[dict[str, Any]] = [
    # ------------------------------------------------------------------ KB2 policies
    {
        "id": "KB2-NP-001",
        "title": "National Agricultural Technology and Innovation Policy (NATIP) 2022-2027",
        "kb": "KB2",
        "category": "national_policies",
        "institution": "Federal Ministry of Agriculture and Food Security (FMAFS)",
        "year": 2022,
        "period": "2022-2027",
        "doc_type": "Policy framework",
        "url": "https://agriculture.gov.ng/wp-content/uploads/2024/06/National-Agricultural-Technology-and-Innovation-Policy-NATIP-2022-2027.pdf",
        "status": "current",
        "topic": "National agricultural policy",
        "description": "Six-year national policy covering technology, innovation, extension and value-chain priorities.",
    },
    {
        "id": "KB2-NP-002",
        "title": "NATIP 2022-2027 Action Plan and Monitoring & Evaluation Framework",
        "kb": "KB2",
        "category": "national_policies",
        "institution": "Federal Ministry of Agriculture and Food Security (FMAFS)",
        "year": 2023,
        "period": "2022-2027",
        "doc_type": "Implementation plan",
        "url": "https://agriculture.gov.ng/wp-content/uploads/2024/06/NATIP_Implenetation_Plan-6years-Copy.pdf",
        "status": "current",
        "topic": "Policy implementation",
        "description": "Action plan, targets and M&E framework for NATIP.",
    },
    {
        "id": "KB2-NP-003",
        "title": "Agricultural Promotion Policy (Green Alternative) 2016-2020",
        "kb": "KB2",
        "category": "national_policies",
        "institution": "Federal Ministry of Agriculture and Rural Development (FMARD)",
        "year": 2016,
        "period": "2016-2020",
        "doc_type": "Policy framework",
        "url": "https://agriculture.gov.ng/wp-content/uploads/2024/06/Agric-Promotion-Policy_Green-Alternative_2016-2020_Final.pdf",
        "status": "expired",
        "topic": "National agricultural policy",
        "description": "Previous federal agricultural promotion policy; retained for comparison with NATIP.",
    },
    {
        "id": "KB2-NP-004",
        "title": "Immediate, Short, Medium and Long Term Sector Priorities of the Honourable Ministers of Agriculture and Food Security",
        "kb": "KB2",
        "category": "national_policies",
        "institution": "Federal Ministry of Agriculture and Food Security (FMAFS)",
        "year": 2024,
        "period": None,
        "doc_type": "Sector priorities",
        "url": "https://agriculture.gov.ng/wp-content/uploads/2024/06/FMAFS-Road-Map-Strategies.pdf",
        "status": "current",
        "topic": "Agricultural development strategy",
        "description": "Ministerial sector priorities (immediate, short, medium and long term) for agriculture and food security; published under the FMAFS roadmap file name.",
    },
    {
        "id": "KB2-NP-005",
        "title": "National Agri-Food Systems Investment Plan (NASIP)",
        "kb": "KB2",
        "category": "national_policies",
        "institution": "Federal Ministry of Agriculture and Food Security (FMAFS)",
        "year": None,
        "period": None,
        "doc_type": "Investment plan",
        "url": "https://agriculture.gov.ng/wp-content/uploads/2026/03/Agricfood-System-Investment-Plan-1.pdf",
        "status": "current",
        "topic": "Agricultural investment",
        "description": "Investment plan aligned with NATIP and national/regional policy commitments.",
    },
    {
        "id": "KB2-NP-006",
        "title": "National Irrigation and Drainage Policy and Strategy",
        "kb": "KB2",
        "category": "national_policies",
        "institution": "Federal Ministry of Water Resources",
        "year": 2015,
        "period": None,
        "doc_type": "Policy and strategy",
        "url": "https://faolex.fao.org/docs/pdf/nig181432.pdf",
        "status": "unknown",
        "topic": "Irrigation and water management",
        "description": "National irrigation and drainage policy, objectives and implementation strategy.",
    },
    {
        "id": "KB2-NP-007",
        "title": "National Agricultural Extension Policy",
        "kb": "KB2",
        "category": "national_policies",
        "institution": "Federal Ministry of Agriculture and Food Security (FMAFS)",
        "year": None,
        "period": None,
        "doc_type": "Policy",
        "url": "https://faolex.fao.org/docs/pdf/nig235831.pdf",
        "status": "current",
        "topic": "Agricultural extension",
        "description": "National policy for agricultural extension and advisory services.",
    },
    {
        "id": "KB2-NP-008",
        "title": "One Health Strategic Plan 2019-2023",
        "kb": "KB2",
        "category": "national_policies",
        "institution": "Federal Ministry of Health; FMAFS; Federal Ministry of Environment",
        "year": 2019,
        "period": "2019-2023",
        "doc_type": "Strategic plan",
        "url": "https://ncdc.gov.ng/themes/common/docs/protocols/93_1566785462.pdf",
        "status": "expired",
        "topic": "One Health, zoonoses",
        "description": "National One Health coordination plan covering human, animal and environmental health.",
    },
    {
        "id": "KB2-BS-003",
        "title": "National Agricultural Sample Survey 2023 - survey documentation",
        "kb": "KB2",
        "category": "budgets_statistics",
        "institution": "National Bureau of Statistics (NBS)",
        "year": 2023,
        "period": None,
        "doc_type": "Statistical survey",
        "url": "https://microdata.nigerianstat.gov.ng/index.php/catalog/173",
        "status": "current",
        "topic": "Agricultural statistics",
        "description": "NASS 2023 survey; the NBS site offers metadata/microdata rather than a direct public PDF, so the report requires manual retrieval.",
        "manual": True,
        "manual_reason": "No direct public PDF endpoint; NBS catalogue requires registration/manual download.",
    },
    # ------------------------------------------------------------------ KB2 laws / regulations
    {
        "id": "KB2-LR-001",
        "title": "National Agricultural Seeds Act 2019 (Official Gazette No. 142B)",
        "kb": "KB2",
        "category": "laws_regulations",
        "institution": "Federal Republic of Nigeria / National Agricultural Seeds Council",
        "year": 2019,
        "period": None,
        "doc_type": "Act",
        "url": "https://seedcouncil.gov.ng/wp-content/uploads/2020/07/Official-Gazatte-No.-142B-NASC-Act-2019.pdf",
        "status": "current",
        "topic": "Seed law",
        "description": "Act establishing the National Agricultural Seeds Council and regulating seed production, certification and marketing.",
    },
    {
        "id": "KB2-LR-002",
        "title": "National Agricultural Seeds Decree 1992 (Seed Act)",
        "kb": "KB2",
        "category": "laws_regulations",
        "institution": "Federal Republic of Nigeria",
        "year": 1992,
        "period": None,
        "doc_type": "Act (historical)",
        "url": "https://seedcouncil.gov.ng/wp-content/uploads/2016/11/Seed_Act.pdf",
        "status": "historical",
        "topic": "Seed law",
        "description": "Earlier seed legislation, retained for historical comparison; superseded by later seed-sector legislation.",
    },
    {
        "id": "KB2-LR-003",
        "title": "Third Party Seed Certification Regulations 2025",
        "kb": "KB2",
        "category": "laws_regulations",
        "institution": "National Agricultural Seeds Council (NASC)",
        "year": 2025,
        "period": None,
        "doc_type": "Regulation",
        "url": "https://seedcouncil.gov.ng/wp-content/uploads/2026/07/Third-Party-Seed-Certification-Regulations-2025.pdf",
        "status": "current",
        "topic": "Seed certification",
        "description": "Regulations for third-party seed certification.",
    },
    {
        "id": "KB2-LR-004",
        "title": "National Harmonized Plant Varieties Registration and Release Regulations 2025",
        "kb": "KB2",
        "category": "laws_regulations",
        "institution": "National Agricultural Seeds Council (NASC)",
        "year": 2025,
        "period": None,
        "doc_type": "Regulation",
        "url": "https://seedcouncil.gov.ng/wp-content/uploads/2026/07/National-Harmonized-Plant-Varieties-Registration-and-Release-Regulations-2025.pdf",
        "status": "current",
        "topic": "Plant variety registration",
        "description": "Harmonised rules for registering and releasing plant varieties.",
    },
    {
        "id": "KB2-LR-005",
        "title": "National Early Generation Seed Production Liberalization Regulation 2025",
        "kb": "KB2",
        "category": "laws_regulations",
        "institution": "National Agricultural Seeds Council (NASC)",
        "year": 2025,
        "period": None,
        "doc_type": "Regulation",
        "url": "https://seedcouncil.gov.ng/wp-content/uploads/2026/07/National-Early-Generation-Seed-Production-Liberalization-Regulation-2025.pdf",
        "status": "current",
        "topic": "Seed systems",
        "description": "Regulation liberalising early-generation seed production.",
    },
    {
        "id": "KB2-LR-006",
        "title": "Fertilizer Registration Regulations (NAFDAC draft)",
        "kb": "KB2",
        "category": "laws_regulations",
        "institution": "National Agency for Food and Drug Administration and Control (NAFDAC)",
        "year": None,
        "period": None,
        "doc_type": "Draft regulation",
        "url": "https://www.nafdac.gov.ng/wp-content/uploads/Files/Resources/Regulations/New_Draft_Regulations/Fertilizer-Registration-Regulations.pdf",
        "status": "draft",
        "topic": "Fertilizer regulation",
        "description": "Draft fertilizer registration regulations; status must be confirmed before use as binding law.",
    },
    # ------------------------------------------------------------------ KB2 institutional mandates
    {
        "id": "KB2-IM-001",
        "title": "Agricultural Research Council of Nigeria Act",
        "kb": "KB2",
        "category": "institutional_mandates",
        "institution": "Federal Republic of Nigeria",
        "year": None,
        "period": None,
        "doc_type": "Act (mandate)",
        "url": "https://faolex.fao.org/docs/pdf/nig120194.pdf",
        "status": "current",
        "topic": "Research institutions",
        "description": "Establishment Act defining ARCN's mandate and its relationship with national agricultural research institutes.",
    },
    {
        "id": "KB2-IM-002",
        "title": "NAERLS mandate",
        "kb": "KB2",
        "category": "institutional_mandates",
        "institution": "National Agricultural Extension and Research Liaison Services (NAERLS)",
        "year": None,
        "period": None,
        "doc_type": "Institutional mandate",
        "url": "https://naerls.gov.ng/mandate",
        "status": "current",
        "topic": "Extension institution",
        "description": "Official mandate page; published as HTML with no stable PDF, so manual capture is required.",
        "manual": True,
        "manual_reason": "Mandate is HTML-only; no downloadable PDF on the official page.",
    },
    {
        "id": "KB2-IM-003",
        "title": "National Agricultural Seeds Council Strategic Plan 2020-2024",
        "kb": "KB2",
        "category": "institutional_mandates",
        "institution": "National Agricultural Seeds Council (NASC)",
        "year": 2019,
        "period": "2020-2024",
        "doc_type": "Strategic plan",
        "url": "https://seedcouncil.gov.ng/wp-content/uploads/2020/02/STRATEGIC-PLAN-NASC-FINAL-APPROVED.pdf",
        "status": "historical",
        "topic": "Seed regulation",
        "description": "NASC strategy, targets and institutional priorities for the seed sector.",
    },
    {
        "id": "KB2-IM-004",
        "title": "National Agricultural Development Fund (Establishment) Act 2022",
        "kb": "KB2",
        "category": "institutional_mandates",
        "institution": "Federal Republic of Nigeria",
        "year": 2022,
        "period": None,
        "doc_type": "Act",
        "url": "https://app.lawyersguide.ng/laws/national-agricultural-development-fund-establishment-act-2022",
        "status": "current",
        "topic": "Agricultural finance",
        "description": "Act establishing the National Agricultural Development Fund; only an HTML legal-portal copy was located, so a PDF requires manual retrieval.",
        "manual": True,
        "manual_reason": "No official PDF verified; HTML legal-portal copy only.",
    },
    # ------------------------------------------------------------------ KB2 implementation evidence
    {
        "id": "KB2-IR-001",
        "title": "2025 Wet Season Agricultural Performance in Nigeria",
        "kb": "KB2",
        "category": "implementation_reports",
        "institution": "Federal Ministry of Agriculture and Food Security (FMAFS)",
        "year": 2025,
        "period": "2025 wet season",
        "doc_type": "Performance report",
        "url": "https://agriculture.gov.ng/wp-content/uploads/2025/10/2025-Wet-Season-Agricultural-Performance-in-Nigeria.pdf",
        "status": "current",
        "topic": "Agricultural performance",
        "description": "Government report on 2025 wet-season agricultural performance.",
    },
    {
        "id": "KB2-IR-002",
        "title": "National Food Consumption and Micronutrient Survey 2022 - Preliminary Report",
        "kb": "KB2",
        "category": "implementation_reports",
        "institution": "Federal Ministry of Agriculture and Food Security; partners",
        "year": 2022,
        "period": None,
        "doc_type": "Survey report",
        "url": "https://agriculture.gov.ng/wp-content/uploads/2024/06/NFCMS-Report-Final_Preliminary-2022.pdf",
        "status": "historical",
        "topic": "Food security and nutrition",
        "description": "Preliminary national food consumption and micronutrient survey report.",
    },
    {
        "id": "KB2-IR-003",
        "title": "Key Findings: National Food Consumption and Micronutrient Survey (April 2024)",
        "kb": "KB2",
        "category": "implementation_reports",
        "institution": "Federal Ministry of Agriculture and Food Security; partners",
        "year": 2024,
        "period": None,
        "doc_type": "Survey findings",
        "url": "https://agriculture.gov.ng/wp-content/uploads/2024/06/Key-Findings-NFCMS_Final-April-2024.pdf",
        "status": "current",
        "topic": "Food security and nutrition",
        "description": "Key findings summary from the national food consumption survey.",
    },
    {
        "id": "KB2-IR-004",
        "title": "NAGS 2.0 Environmental and Social System Assessment (ESSA)",
        "kb": "KB2",
        "category": "implementation_reports",
        "institution": "Federal Ministry of Agriculture and Food Security (FMAFS)",
        "year": 2025,
        "period": None,
        "doc_type": "Programme assessment",
        "url": "https://agriculture.gov.ng/wp-content/uploads/2025/06/FINALIZED-NAGS-2.0-ESSA-Document.pdf",
        "status": "current",
        "topic": "Programme implementation",
        "description": "Environmental and social assessment for the NAGS 2.0 programme.",
    },
    # ------------------------------------------------------------------ KB2 budgets / statistics
    {
        "id": "KB2-BS-001",
        "title": "2025 Appropriation Act (as passed)",
        "kb": "KB2",
        "category": "budgets_statistics",
        "institution": "Budget Office of the Federation",
        "year": 2025,
        "period": "2025 fiscal year",
        "doc_type": "Budget law",
        "url": "https://budgetoffice.gov.ng/index.php/2025-appropriation-act-as-passed/2025-appropriation-act-as-passed/download",
        "status": "current",
        "topic": "Agricultural budget",
        "description": "Federal appropriation act; contains ministry and programme allocations, not expenditure outcomes.",
    },
    {
        "id": "KB2-BS-002",
        "title": "Analysis of Agriculture Budgetary Allocations and Performance 2023-2025",
        "kb": "KB2",
        "category": "budgets_statistics",
        "institution": "ActionAid Nigeria (independent analysis)",
        "year": 2025,
        "period": "2023-2025",
        "doc_type": "Budget analysis (secondary)",
        "url": "https://nigeria.actionaid.org/sites/nigeria/files/publications/F%26A%20Analysis%20of%20Agriculture%20Budgetary%20Allocations%20and%20Performance.pdf",
        "status": "current",
        "topic": "Budget performance",
        "description": "Independent analysis of agricultural budget allocations and performance; secondary source.",
    },
    # ------------------------------------------------------------------ KB2 international
    {
        "id": "KB2-IF-001",
        "title": "Malabo Declaration on Accelerated Agricultural Growth and Transformation",
        "kb": "KB2",
        "category": "international_frameworks",
        "institution": "African Union",
        "year": 2014,
        "period": "2015-2025",
        "doc_type": "Declaration",
        "url": "https://au.int/sites/default/files/documents/31247-doc-malabo_declaration_2014_11_26.pdf",
        "status": "current",
        "topic": "CAADP / regional commitments",
        "description": "AU Malabo Declaration and its agricultural transformation commitments.",
    },
    {
        "id": "KB2-IF-002",
        "title": "5th CAADP Biennial Review Report",
        "kb": "KB2",
        "category": "international_frameworks",
        "institution": "African Union Commission",
        "year": 2026,
        "period": "2015-2025",
        "doc_type": "Accountability report",
        "url": "https://au.int/sites/default/files/English%20-%20The%205th%20CAADP%20Biennial%20Review%20Report.pdf",
        "status": "current",
        "topic": "CAADP accountability",
        "description": "Continental biennial review of Malabo/CAADP implementation, including country performance.",
    },
    {
        "id": "KB2-IF-003",
        "title": "AU 2003 Maputo Declaration on Agriculture and Food Security",
        "kb": "KB2",
        "category": "international_frameworks",
        "institution": "African Union / AUDA-NEPAD",
        "year": 2003,
        "period": None,
        "doc_type": "Declaration",
        "url": "https://www.nepad.org/file-download/download/public/15057",
        "status": "historical",
        "topic": "CAADP origins",
        "description": "Maputo Declaration committing African governments to agricultural investment targets.",
    },
    {
        "id": "KB2-IF-004",
        "title": "FAO Voluntary Guidelines on the Responsible Governance of Tenure (VGGT)",
        "kb": "KB2",
        "category": "international_frameworks",
        "institution": "Food and Agriculture Organization (FAO)",
        "year": 2012,
        "period": None,
        "doc_type": "International guidelines",
        "url": "https://www.fao.org/3/i2801e/i2801e.pdf",
        "status": "current",
        "topic": "Land tenure",
        "description": "International guidelines on responsible governance of land, fisheries and forests.",
    },
    {
        "id": "KB2-IF-005",
        "title": "FAO Voluntary Guidelines on the Right to Adequate Food",
        "kb": "KB2",
        "category": "international_frameworks",
        "institution": "Food and Agriculture Organization (FAO)",
        "year": 2004,
        "period": None,
        "doc_type": "International guidelines",
        "url": "https://www.fao.org/3/y7937e/y7937e.pdf",
        "status": "current",
        "topic": "Food security",
        "description": "International guidelines on the progressive realisation of the right to adequate food.",
    },
    # ------------------------------------------------------------------ KB1 crop production
    {
        "id": "KB1-CP-001",
        "title": "Guide to Maize Production in Northern Nigeria (Revised 2020)",
        "kb": "KB1",
        "category": "crop_production",
        "institution": "International Institute of Tropical Agriculture (IITA); Feed the Future Nigeria",
        "year": 2020,
        "period": None,
        "doc_type": "Production guide",
        "url": "https://biblio.iita.org/documents/U20BkKamaraMaizeNothomNodev.pdf-0fe7595936d0dfc6f3535474610e8cbe.pdf",
        "status": "current",
        "topic": "Maize",
        "description": "Practical maize production guide for northern Nigeria: land preparation, varieties, spacing, fertilizer, pests and harvest.",
    },
    {
        "id": "KB1-CP-002",
        "title": "Maize Production Manual (IITA Manual Series No. 8, Vol. 1)",
        "kb": "KB1",
        "category": "crop_production",
        "institution": "International Institute of Tropical Agriculture (IITA)",
        "year": 1982,
        "period": None,
        "doc_type": "Production manual",
        "url": "https://biblio.iita.org/documents/U82ManIitaProductionNothomNodev.pdf-9fce0a6ccf8448043986682d83036bc0.pdf",
        "status": "historical",
        "topic": "Maize",
        "description": "Historical IITA maize production manual; useful for agronomic background, not current recommendations.",
    },
    {
        "id": "KB1-CP-003",
        "title": "Training Manual for Maize Production in Nigeria",
        "kb": "KB1",
        "category": "crop_production",
        "institution": "National Cereals Research Institute (NCRI), Badeggi; OCP Africa",
        "year": None,
        "period": None,
        "doc_type": "Training manual",
        "url": "https://agrinigeriaprodsa.blob.core.windows.net/agrifarmer/ac6c4faf-04c0-42a1-9fe0-e7a9b5e7d652.pdf",
        "status": "unknown",
        "topic": "Maize",
        "description": "NCRI training manual for maize production in Nigeria.",
    },
    {
        "id": "KB1-CP-004",
        "title": "Guide to Rice Production in Northern Nigeria (Revised 2020)",
        "kb": "KB1",
        "category": "crop_production",
        "institution": "International Institute of Tropical Agriculture (IITA); Feed the Future Nigeria",
        "year": 2020,
        "period": None,
        "doc_type": "Production guide",
        "url": "https://biblio.iita.org/documents/U20BkKamaiRiceNothomNodev.pdf-82380f79ed883f6cdf6aeca6a2738b15.pdf",
        "status": "current",
        "topic": "Rice",
        "description": "Rice production guide for northern Nigeria: ecologies, varieties, agronomy and post-harvest.",
    },
    {
        "id": "KB1-CP-005",
        "title": "Training Manual for Rice Production in Nigeria",
        "kb": "KB1",
        "category": "crop_production",
        "institution": "National Cereals Research Institute (NCRI), Badeggi; OCP Africa",
        "year": None,
        "period": None,
        "doc_type": "Training manual",
        "url": "https://agrinigeriaprodsa.blob.core.windows.net/agrifarmer/9f50c4ab-2074-4bae-97f3-50ef085ba9cb.pdf",
        "status": "unknown",
        "topic": "Rice",
        "description": "NCRI training manual for rice production in Nigeria.",
    },
    {
        "id": "KB1-CP-006",
        "title": "Growing Cassava in Nigeria (Commercial Crop Production Guide)",
        "kb": "KB1",
        "category": "crop_production",
        "institution": "USAID; ICS-Nigeria; IITA",
        "year": 2003,
        "period": None,
        "doc_type": "Production guide",
        "url": "https://biblio.iita.org/documents/U03ManIitaGrowingNothomNodev.pdf-8f9fd4aaa5294d9319f26833c5c0a2a4.pdf",
        "status": "historical",
        "topic": "Cassava",
        "description": "Commercial cassava production guide for Nigeria.",
    },
    {
        "id": "KB1-CP-007",
        "title": "Cassava in Tropical Africa: A Reference Manual",
        "kb": "KB1",
        "category": "crop_production",
        "institution": "International Institute of Tropical Agriculture (IITA)",
        "year": 1990,
        "period": None,
        "doc_type": "Reference manual",
        "url": "https://biblio.iita.org/documents/U90ManIitaCassavaNothomNodev.pdf-52ca5ad61b1fba9127fc406b6a6982a2.pdf",
        "status": "historical",
        "topic": "Cassava",
        "description": "Historical IITA reference manual on cassava production and utilisation.",
    },
    {
        "id": "KB1-CP-008",
        "title": "Growing Rice in Kano State, Northwestern Nigeria",
        "kb": "KB1",
        "category": "crop_production",
        "institution": "International Institute of Tropical Agriculture (IITA)",
        "year": None,
        "period": None,
        "doc_type": "Research/technology guide",
        "url": "https://biblio.iita.org/documents/U22BkKamaraRiceNothomDev.pdf-341314c6a3862c674662b0da079721f3.pdf",
        "status": "unknown",
        "topic": "Rice",
        "description": "Rice production research and guidance for Kano State.",
    },
    {
        "id": "KB1-CP-009",
        "title": "Starting a Cassava Farm",
        "kb": "KB1",
        "category": "crop_production",
        "institution": "International Institute of Tropical Agriculture (IITA)",
        "year": None,
        "period": None,
        "doc_type": "Extension guide",
        "url": "https://www.iita.org/wp-content/uploads/2016/06/Starting_a_cassava_farm.pdf",
        "status": "unknown",
        "topic": "Cassava",
        "description": "Short cassava establishment guide; the IITA upload endpoint now returns 404.",
        "manual": True,
        "manual_reason": "Official IITA upload URL returns 404; no stable mirror confirmed.",
    },
    # ------------------------------------------------------------------ KB1 seeds
    {
        "id": "KB1-SV-001",
        "title": "Nigeria Early Generation Seed Study (2016)",
        "kb": "KB1",
        "category": "seeds_varieties",
        "institution": "Nigerian Seed Portal Initiative / partners",
        "year": 2016,
        "period": None,
        "doc_type": "Study report",
        "url": "https://www.seedportal.org.ng/admin/media/documents/Early%20Generation%20Seeds%20Study%20Report%20(2016).pdf",
        "status": "historical",
        "topic": "Seed systems",
        "description": "Assessment of early-generation seed systems and improved varieties in Nigeria.",
    },
    {
        "id": "KB1-SV-002",
        "title": "West African Catalogue of Plant Species and Varieties (2008)",
        "kb": "KB1",
        "category": "seeds_varieties",
        "institution": "Food and Agriculture Organization (FAO); West African partners",
        "year": 2008,
        "period": None,
        "doc_type": "Catalogue",
        "url": "https://www.fao.org/4/i0062e/i0062e.pdf",
        "status": "historical",
        "topic": "Varieties",
        "description": "Regional catalogue of plant species and varieties, including West African crop varieties.",
    },
    # ------------------------------------------------------------------ KB1 soil
    {
        "id": "KB1-SF-001",
        "title": "Optimizing Fertilizer Use within Integrated Soil Fertility Management in Nigeria",
        "kb": "KB1",
        "category": "soil_fertilizer",
        "institution": "IFDC / OFRA partners",
        "year": None,
        "period": None,
        "doc_type": "Technical chapter",
        "url": "https://ifdc.org/wp-content/uploads/2026/01/OFRA-Chapter-12_Nigeria_HR.pdf",
        "status": "unknown",
        "topic": "Soil fertility; fertilizer",
        "description": "Nigeria chapter on fertilizer recommendations and integrated soil fertility management.",
    },
    # ------------------------------------------------------------------ KB1 pests/diseases
    {
        "id": "KB1-PD-001",
        "title": "Disease Control in Cassava Farms: IPM Field Guide for Extension Agents",
        "kb": "KB1",
        "category": "pests_diseases",
        "institution": "International Institute of Tropical Agriculture (IITA)",
        "year": 2000,
        "period": None,
        "doc_type": "Field guide",
        "url": "https://farm-d.org/wp-content/uploads/2024/03/Disease-control-IPM-Guide-Cassava.pdf",
        "status": "historical",
        "topic": "Cassava diseases",
        "description": "IPM field guide for cassava disease identification and control.",
    },
    {
        "id": "KB1-PD-002",
        "title": "Common Pests and Diseases of Cassava and Control",
        "kb": "KB1",
        "category": "pests_diseases",
        "institution": "Ministry of Agriculture Liberia; IITA (SAPEC)",
        "year": None,
        "period": None,
        "doc_type": "Extension guide",
        "url": "https://www.moa.gov.lr/sites/default/files/documents/3.%20Common%20Pests%20and%20Diseases%20of%20Cassava%20and%20Control.pdf",
        "status": "unknown",
        "topic": "Cassava pests and diseases",
        "description": "Illustrated cassava pest and disease guide; the downloaded PDF is image-only and needs OCR.",
    },
    {
        "id": "KB1-PD-003",
        "title": "Maize Diseases: A Guide for Field Identification",
        "kb": "KB1",
        "category": "pests_diseases",
        "institution": "CIMMYT",
        "year": None,
        "period": None,
        "doc_type": "Field guide",
        "url": "https://repository.cimmyt.org/server/api/core/bitstreams/d14102da-8e31-414e-ab2d-932f31292265/content",
        "status": "unknown",
        "topic": "Maize diseases",
        "description": "Illustrated field guide for identifying maize diseases.",
    },
    {
        "id": "KB1-PD-004",
        "title": "Fall Armyworm Field Handbook: Identification and Management",
        "kb": "KB1",
        "category": "pests_diseases",
        "institution": "FAO; CABI",
        "year": 2019,
        "period": None,
        "doc_type": "Field handbook",
        "url": "https://www.cabi.org/wp-content/uploads/FAW-pocket-guide.pdf",
        "status": "current",
        "topic": "Fall armyworm; maize",
        "description": "Pocket field handbook for fall armyworm identification and management.",
    },
    {
        "id": "KB1-PD-005",
        "title": "Integrated Management of the Fall Armyworm on Maize: Farmer Field School Guide",
        "kb": "KB1",
        "category": "pests_diseases",
        "institution": "Food and Agriculture Organization (FAO)",
        "year": 2018,
        "period": None,
        "doc_type": "Training guide",
        "url": "https://openknowledge.fao.org/server/api/core/bitstreams/c43afcac-6262-4152-afd4-70cd4ac46584/content",
        "status": "current",
        "topic": "Fall armyworm; maize",
        "description": "Farmer Field School guide to integrated fall armyworm management in Africa.",
    },
    {
        "id": "KB1-PD-006",
        "title": "Guidance on Integrated Pest Management for the World's Major Crop Pests and Diseases",
        "kb": "KB1",
        "category": "pests_diseases",
        "institution": "Food and Agriculture Organization (FAO)",
        "year": None,
        "period": None,
        "doc_type": "Technical guidance",
        "url": "https://openknowledge.fao.org/server/api/core/mapping?url=https://openknowledge.fao.org/3/cd4890en/cd4890en.pdf",
        "status": "current",
        "topic": "Integrated pest management",
        "description": "IPM guidance for major crop pests and diseases.",
    },
    {
        "id": "KB1-PD-007",
        "title": "Guidelines for Monitoring Diseases, Pests and Weeds in Cereal Crops",
        "kb": "KB1",
        "category": "pests_diseases",
        "institution": "Food and Agriculture Organization (FAO)",
        "year": 2016,
        "period": None,
        "doc_type": "Monitoring guidelines",
        "url": "https://www.fao.org/3/i5550e/i5550e.pdf",
        "status": "current",
        "topic": "Cereals; pest monitoring",
        "description": "Field monitoring guidelines for cereal diseases, pests and weeds.",
    },
    # ------------------------------------------------------------------ KB1 climate
    {
        "id": "KB1-CE-001",
        "title": "Climate-Smart Agriculture Sourcebook",
        "kb": "KB1",
        "category": "climate_environment",
        "institution": "Food and Agriculture Organization (FAO)",
        "year": 2013,
        "period": None,
        "doc_type": "Sourcebook",
        "url": "https://www.fao.org/3/i3325e/i3325e.pdf",
        "status": "historical",
        "topic": "Climate-smart agriculture",
        "description": "Comprehensive sourcebook on climate-smart agriculture, landscapes and food security.",
    },
    # ------------------------------------------------------------------ KB1 mechanization
    {
        "id": "KB1-ME-001",
        "title": "Agricultural Mechanization Policies and Strategies in Nigeria",
        "kb": "KB1",
        "category": "mechanization",
        "institution": "Commonwealth Secretariat (chapter authors)",
        "year": None,
        "period": None,
        "doc_type": "Book chapter",
        "url": "https://comsec-web-static.s3.eu-west-1.amazonaws.com/s3fs-public/ilibrary/chapter-pdfs/6313.pdf",
        "status": "historical",
        "topic": "Mechanization",
        "description": "Review of Nigerian agricultural mechanization policies and strategies.",
    },
    {
        "id": "KB1-EX-002",
        "title": "AESON 2021 Conference Book of Abstracts",
        "kb": "KB1",
        "category": "extension",
        "institution": "Agricultural Extension Society of Nigeria (AESON); Federal University of Technology Minna",
        "year": 2021,
        "period": None,
        "doc_type": "Conference abstracts",
        "url": "http://irepo.futminna.edu.ng:8080/jspui/bitstream/123456789/14891/1/Book%20of%20Abstract%20AESON-OGUN%202021%20FINAL.pdf",
        "status": "historical",
        "topic": "Agricultural extension",
        "description": "Conference abstracts on extension methods and delivery in Nigeria.",
    },
    # ------------------------------------------------------------------ KB1 research/statistics
    {
        "id": "KB1-RS-001",
        "title": "Cassava Development in Nigeria: A Country Case Study",
        "kb": "KB1",
        "category": "research_statistics",
        "institution": "Federal Ministry of Agriculture and Natural Resources; FAO",
        "year": None,
        "period": None,
        "doc_type": "Country case study",
        "url": "https://www.fao.org/4/a0154e/a0154e02.pdf",
        "status": "historical",
        "topic": "Cassava",
        "description": "Country case study on cassava development in Nigeria.",
    },
    {
        "id": "KB1-RS-002",
        "title": "Growing Maize with Cassava in Nigeria",
        "kb": "KB1",
        "category": "research_statistics",
        "institution": "USAID; ICS-Nigeria",
        "year": None,
        "period": None,
        "doc_type": "Production guide",
        "url": "https://cgspace.cgiar.org/bitstreams/87ba8a33-ae73-46a0-9751-87dd70606d0e/download",
        "status": "historical",
        "topic": "Maize; cassava",
        "description": "Commercial crop production guide for intercropping maize with cassava.",
    },
    # ------------------------------------------------------------------ gaps recorded explicitly
]


def slugify(value: str, max_length: int = 70) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:max_length].strip("-") or "document"


def title_tokens(title: str) -> list[str]:
    stop = {"the", "and", "for", "with", "from", "report", "guide", "manual", "policy"}
    return [
        token
        for token in re.findall(r"[a-z0-9]{4,}", title.lower())
        if token not in stop
    ]


def extract_pdf_info(path: Path) -> tuple[int, int]:
    reader = PdfReader(str(path))
    text = "".join((page.extract_text() or "") for page in reader.pages)
    return len(reader.pages), len(text)


def verify_title(path: Path, title: str) -> tuple[str, int, int]:
    reader = PdfReader(str(path))
    sample = "\n".join(
        (page.extract_text() or "") for page in reader.pages[:5]
    ).lower()
    tokens = title_tokens(title)
    if not tokens:
        return "downloaded_unverified", 0, 0
    matched = sum(1 for token in tokens if token in sample)
    ratio = matched / len(tokens)
    return ("verified" if ratio >= 0.45 else "downloaded_unverified"), matched, len(tokens)


def download(source: dict[str, Any], destinations: dict[str, Path], dry_run: bool) -> dict[str, Any]:
    record = {
        **source,
        "retrieved_at": date.today().isoformat(),
        "filename": "",
        "sha256": "",
        "pages": None,
        "text_chars": None,
        "ocr_required": None,
        "verification_status": "manual_required" if source.get("manual") else "",
        "notes": source.get("manual_reason", ""),
    }
    if source.get("manual"):
        return record
    previous = PREVIOUS.get(source["id"])
    if (
        previous
        and previous.get("filename")
        and previous.get("title") == source["title"]
        and (CANDIDATES / previous["filename"]).exists()
        and previous.get("verification_status") in {"verified", "downloaded_unverified"}
    ):
        for key in ("filename", "sha256", "pages", "text_chars", "ocr_required", "verification_status", "notes", "retrieved_at"):
            if key in previous:
                record[key] = previous[key]
        record["filename"] = str(record["filename"]).replace("\\", "/")
        return record
    if dry_run:
        record["verification_status"] = "not_downloaded_dry_run"
        return record

    url = source["url"]
    folder = destinations[source["category"]]
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{source['id']}_{slugify(source['title'])}.pdf"
    target = folder / filename

    if target.exists():
        record["filename"] = target.relative_to(CANDIDATES).as_posix()
        record["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        record["verification_status"], matched, total = verify_title(target, source["title"])
        record["pages"], record["text_chars"] = extract_pdf_info(target)
        record["ocr_required"] = record["text_chars"] == 0
        record["notes"] = f"Existing file reused; title tokens {matched}/{total}."
        return record

    try:
        response = requests.get(
            url,
            headers={"User-Agent": UA},
            timeout=180,
            stream=True,
            allow_redirects=True,
        )
        if response.status_code != 200:
            record["verification_status"] = "manual_required"
            record["notes"] = f"HTTP {response.status_code}"
            return record
        content = response.content
    except Exception as exc:  # network/timeouts; one attempt only
        record["verification_status"] = "manual_required"
        record["notes"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return record

    if not content.startswith(b"%PDF") or len(content) < 10_000:
        record["verification_status"] = "rejected_invalid"
        record["notes"] = f"Not a usable PDF (bytes={len(content)})."
        return record

    digest = hashlib.sha256(content).hexdigest()
    record["sha256"] = digest
    if digest in HASHES:
        existing = CANDIDATES / HASHES[digest]
        record["filename"] = HASHES[digest]
        try:
            record["pages"], record["text_chars"] = extract_pdf_info(existing)
            record["ocr_required"] = record["text_chars"] == 0
            status, matched, total = verify_title(existing, source["title"])
            record["verification_status"] = status
            record["notes"] = (
                f"Identical content already present at {HASHES[digest]}; "
                f"title tokens {matched}/{total}."
            )
        except Exception as exc:
            record["verification_status"] = "downloaded_unverified"
            record["notes"] = f"Identical content at {HASHES[digest]}; parse failed: {type(exc).__name__}."
        return record

    target.write_bytes(content)
    try:
        pages, chars = extract_pdf_info(target)
    except Exception as exc:
        target.unlink(missing_ok=True)
        record["verification_status"] = "rejected_invalid"
        record["notes"] = f"PDF parse failed: {type(exc).__name__}"
        return record

    status, matched, total = verify_title(target, source["title"])
    HASHES[digest] = filename
    record.update(
        filename=target.relative_to(CANDIDATES).as_posix(),
        pages=pages,
        text_chars=chars,
        ocr_required=chars == 0,
        verification_status=status,
        notes=f"Title tokens {matched}/{total} found in first pages.",
    )
    if chars == 0:
        record["notes"] += " No extractable text; OCR required."
    return record


def build_directories() -> dict[str, Path]:
    destinations: dict[str, Path] = {}
    for category in KB1_CATEGORIES:
        destinations[category] = CANDIDATES / "KB1" / category
    for category in KB2_CATEGORIES:
        destinations[category] = CANDIDATES / "KB2" / category
    for folder in destinations.values():
        folder.mkdir(parents=True, exist_ok=True)
    METADATA.mkdir(parents=True, exist_ok=True)
    return destinations


def write_excel(records: list[dict[str, Any]]) -> Path:
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
        "Verification Status",
        "Policy/Document Status",
        "Local Filename",
        "Short Description",
        "Relevant Crop/Topic",
        "SHA-256",
        "Pages",
        "OCR Required",
        "Notes",
    ]
    sheet.append(columns)
    for record in sorted(records, key=lambda item: item["id"]):
        sheet.append(
            [
                record["id"],
                record["title"],
                record["kb"],
                record["category"],
                record["institution"],
                record.get("year"),
                record.get("period"),
                record["doc_type"],
                record["url"],
                record["retrieved_at"],
                record["verification_status"],
                record.get("status", "unknown"),
                record.get("filename", ""),
                record["description"],
                record.get("topic", ""),
                record.get("sha256", ""),
                record.get("pages"),
                "yes" if record.get("ocr_required") else ("no" if record.get("ocr_required") is False else ""),
                record.get("notes", ""),
            ]
        )

    header_fill = PatternFill("solid", fgColor="1F4E3D")
    header_font = Font(color="FFFFFF", bold=True)
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = border
    widths = [14, 55, 10, 24, 40, 12, 16, 22, 55, 14, 22, 20, 55, 60, 28, 66, 8, 10, 55]
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
        if record["verification_status"] == "manual_required":
            manual.append(
                [
                    record["id"],
                    record["title"],
                    record["kb"],
                    record["category"],
                    record["institution"],
                    record["url"],
                    record.get("notes", ""),
                ]
            )
    for cell in manual[1]:
        cell.fill = header_fill
        cell.font = header_font
    for column, width in zip("ABCDEFG", [14, 55, 10, 24, 40, 55, 55]):
        manual.column_dimensions[column].width = width

    summary = workbook.create_sheet("Summary")
    downloaded = [r for r in records if r["verification_status"] in {"verified", "downloaded_unverified"}]
    manual_records = [r for r in records if r["verification_status"] == "manual_required"]
    summary.append(["Metric", "Value"])
    summary.append(["Total sources declared", len(records)])
    summary.append(["Downloaded", len(downloaded)])
    summary.append(["Manual retrieval required", len(manual_records)])
    summary.append(["Rejected duplicates", sum(1 for r in records if r["verification_status"] == "rejected_duplicate")])
    summary.append(["Rejected invalid", sum(1 for r in records if r["verification_status"] == "rejected_invalid")])
    summary.append([])
    summary.append(["KB", "Category", "Downloaded", "Manual"])
    for kb in ("KB1", "KB2"):
        categories = KB1_CATEGORIES if kb == "KB1" else KB2_CATEGORIES
        for category in categories:
            subset = [r for r in records if r["kb"] == kb and r["category"] == category]
            summary.append(
                [
                    kb,
                    category,
                    sum(1 for r in subset if r["verification_status"] in {"verified", "downloaded_unverified"}),
                    sum(1 for r in subset if r["verification_status"] == "manual_required"),
                ]
            )
    for cell in summary[1]:
        cell.fill = header_fill
        cell.font = header_font
    summary.column_dimensions["A"].width = 32
    summary.column_dimensions["B"].width = 32
    summary.column_dimensions["C"].width = 14
    summary.column_dimensions["D"].width = 14

    output = METADATA / "document_catalogue.xlsx"
    workbook.save(output)
    return output


def write_report(records: list[dict[str, Any]], catalogue: Path) -> Path:
    downloaded = [r for r in records if r["verification_status"] in {"verified", "downloaded_unverified"}]
    manual = [r for r in records if r["verification_status"] == "manual_required"]
    duplicates = [r for r in records if r["verification_status"] == "rejected_duplicate"]
    invalid = [r for r in records if r["verification_status"] == "rejected_invalid"]
    lines = [
        "# Document acquisition report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Totals",
        f"- Sources declared: {len(records)}",
        f"- Downloaded and usable: {len(downloaded)}",
        f"- Manual retrieval required: {len(manual)}",
        f"- Rejected duplicates: {len(duplicates)}",
        f"- Rejected invalid: {len(invalid)}",
        "",
        "## By knowledge base and category",
        "",
        "| KB | Category | Downloaded | Manual |",
        "|---|---|---|---|",
    ]
    for kb in ("KB1", "KB2"):
        categories = KB1_CATEGORIES if kb == "KB1" else KB2_CATEGORIES
        for category in categories:
            subset = [r for r in records if r["kb"] == kb and r["category"] == category]
            lines.append(
                f"| {kb} | {category} | "
                f"{sum(1 for r in subset if r['verification_status'] in {'verified', 'downloaded_unverified'})} | "
                f"{sum(1 for r in subset if r['verification_status'] == 'manual_required')} |"
            )
    institutions = sorted({r["institution"] for r in downloaded})
    lines += ["", "## Institutions represented", ""] + [f"- {item}" for item in institutions]
    lines += ["", "## Manual retrieval", ""]
    if manual:
        lines += [f"- {r['id']}: {r['title']} ({r['url'] or 'no URL'}) — {r.get('notes', '')}" for r in manual]
    else:
        lines.append("- None")
    lines += [
        "",
        "## Gaps",
        "- KB1 water management: no downloadable Nigeria-specific technical manual verified; the national irrigation policy is catalogued under KB2.",
        "- KB1 extension: national extension policy is in KB2; KB1 holds the AESON 2021 abstracts, but a full technical extension manual/report remains a gap.",
        "- KB2 budgets: appropriation act is a budget law; actual expenditure evidence remains limited to the ActionAid analysis.",
        "- KB2 statistics: NBS NASS 2023 report requires manual retrieval (no direct public PDF).",
        "",
        f"Catalogue: `{catalogue.relative_to(ROOT).as_posix()}`",
    ]
    output = METADATA / "acquisition_report.md"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


HASHES: dict[str, str] = {}
PREVIOUS: dict[str, dict[str, Any]] = {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Acquire AgroBridge candidate documents.")
    parser.add_argument("--dry-run", action="store_true", help="build catalogue without downloading")
    args = parser.parse_args()

    destinations = build_directories()
    previous_path = METADATA / "sources.json"
    if previous_path.exists():
        try:
            for previous in json.loads(previous_path.read_text(encoding="utf-8")):
                PREVIOUS[previous["id"]] = previous
        except (json.JSONDecodeError, KeyError):
            pass
    for existing in CANDIDATES.rglob("*.pdf"):
        HASHES[hashlib.sha256(existing.read_bytes()).hexdigest()] = existing.relative_to(CANDIDATES).as_posix()

    records: list[dict[str, Any]] = []
    for index, source in enumerate(SOURCES, start=1):
        record = download(source, destinations, args.dry_run)
        records.append(record)
        print(
            f"[{index}/{len(SOURCES)}] {source['id']}: {record['verification_status']}"
            + (f" ({record['filename']})" if record.get("filename") else "")
        )
        if not args.dry_run and not source.get("manual"):
            time.sleep(0.3)

    catalogue = write_excel(records)
    report = write_report(records, catalogue)
    (METADATA / "sources.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Catalogue: {catalogue}")
    print(f"Report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
