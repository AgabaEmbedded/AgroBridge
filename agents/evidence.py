"""Helpers to format retrieved evidence and enforce citation integrity."""

from __future__ import annotations

import re
from typing import Any

from agents.schemas import EvidenceItem, QaAnswer, SynthesisReport, VerificationResult

_INTERNAL_REFERENCE_RE = re.compile(
    r"\[[^\]]*(?:KB[12]|p\.?\s*\d+|c\.?\s*\d+|chunk|document)[^\]]*\]"
    r"|\bKB\s*(?:1|2|one|two)\b(?:\s*[/:.-]?\s*[A-Za-z0-9_]+){0,3}"
    r"|\b(?:document|chunk|source)[ _-]?(?:id|index|ref(?:erence)?)\s*[:#]?\s*[A-Za-z0-9_./-]+"
    r"|\b(?:page|p)\.?\s*\d+\b"
    r"|\bchunk\s+\d+\b",
    re.IGNORECASE,
)


def sanitize_spoken_text(text: str) -> str:
    """Remove internal retrieval labels and metadata from farmer-facing speech."""
    cleaned = _INTERNAL_REFERENCE_RE.sub(" ", str(text or ""))
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"([.!?])\s*([.!?])+", r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" ,;:")


def format_evidence(hits: list[dict[str, Any]], max_chars: int = 1200) -> str:
    blocks = []
    for hit in hits:
        blocks.append(f"[{hit['citation']}]\n{hit['text'][:max_chars]}")
    return "\n\n".join(blocks) if blocks else "(no evidence retrieved)"


def citation_index(hits: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {hit["citation"]: hit for hit in hits}


def _resolve(citation: str, index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if not citation:
        return None
    if citation in index:
        return index[citation]
    lowered = citation.strip().lower()
    for label, hit in index.items():
        if label.lower() == lowered:
            return hit
    return None


def sanitize_citations(
    citations: list[str], hits: list[dict[str, Any]]
) -> tuple[list[str], list[str]]:
    """Keep only citations that exist in the retrieved evidence."""
    index = citation_index(hits)
    kept: list[str] = []
    dropped: list[str] = []
    for citation in citations:
        hit = _resolve(str(citation), index)
        if hit is None:
            dropped.append(str(citation))
        elif hit["citation"] not in kept:
            kept.append(hit["citation"])
    return kept, dropped


def sanitize_evidence(
    items: list[EvidenceItem], hits: list[dict[str, Any]]
) -> tuple[list[EvidenceItem], list[str]]:
    index = citation_index(hits)
    kept: list[EvidenceItem] = []
    dropped: list[str] = []
    for item in items:
        hit = _resolve(item.citation, index)
        if hit is None:
            dropped.append(item.citation)
            continue
        kept.append(
            EvidenceItem(
                citation=hit["citation"],
                quote=item.quote,
                document_name=hit.get("document_name"),
                page_number=hit.get("page_number"),
            )
        )
    return kept, dropped


def sanitize_answer(answer: QaAnswer, hits: list[dict[str, Any]]) -> tuple[QaAnswer, list[str]]:
    citations, dropped = sanitize_citations(answer.citations, hits)
    evidence, evidence_dropped = sanitize_evidence(answer.supporting_evidence, hits)
    dropped.extend(evidence_dropped)
    return (
        QaAnswer(
            answer=answer.answer,
            recommendations=answer.recommendations,
            supporting_evidence=evidence,
            citations=citations,
            confidence=answer.confidence,
        ),
        dropped,
    )


def sanitize_verification(
    result: VerificationResult, hits: list[dict[str, Any]]
) -> tuple[VerificationResult, list[str]]:
    citations, dropped = sanitize_citations(result.citations, hits)
    evidence, evidence_dropped = sanitize_evidence(result.supporting_policy_evidence, hits)
    dropped.extend(evidence_dropped)
    return (
        VerificationResult(
            status=result.status,
            policy_conflicts=result.policy_conflicts,
            supporting_policy_evidence=evidence,
            citations=citations,
            revision_instructions=result.revision_instructions,
            reasoning_summary=result.reasoning_summary,
        ),
        dropped,
    )


def sanitize_report(
    report: SynthesisReport, hits: list[dict[str, Any]]
) -> tuple[SynthesisReport, list[str]]:
    citations, dropped = sanitize_citations(report.citations, hits)
    for section in (
        report.policy_coverage_gaps,
        report.implementation_gaps,
        report.institutional_gaps,
        report.evidence_gaps,
    ):
        for gap in section:
            kept, removed = sanitize_citations(gap.citations, hits)
            gap.citations = kept
            dropped.extend(removed)
    report.citations = citations
    return report, dropped
