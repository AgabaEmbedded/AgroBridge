"""Pydantic contracts for agent inputs/outputs.

Agents exchange these models rather than free-form text so orchestration stays predictable
and audit records are machine-checkable.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]
VerificationStatus = Literal["APPROVED", "UNAPPROVED", "NEEDS_REVIEW"]
GapStatus = Literal["confirmed_shortfall", "potential_gap", "insufficient_evidence"]


class EvidenceItem(BaseModel):
    citation: str = Field(description="Citation label copied from the supplied evidence")
    quote: str | None = Field(default=None, description="Short supporting excerpt")
    document_name: str | None = None
    page_number: int | None = None


class QaAnswer(BaseModel):
    answer: str = Field(description="Farmer-facing answer, short and spoken-friendly")
    recommendations: list[str] = Field(default_factory=list)
    supporting_evidence: list[EvidenceItem] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    confidence: Confidence = "low"


class VerificationResult(BaseModel):
    status: VerificationStatus
    policy_conflicts: list[str] = Field(default_factory=list)
    supporting_policy_evidence: list[EvidenceItem] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)
    reasoning_summary: str = ""


class PolicyFindings(BaseModel):
    policy_commitments: list[str] = Field(default_factory=list)
    responsible_institutions: list[str] = Field(default_factory=list)
    implementation_targets: list[str] = Field(default_factory=list)
    implementation_evidence: list[str] = Field(default_factory=list)
    identified_policy_gaps: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class NeedsFindings(BaseModel):
    agricultural_challenges: list[str] = Field(default_factory=list)
    practical_farmer_needs: list[str] = Field(default_factory=list)
    technical_requirements: list[str] = Field(default_factory=list)
    evidence_of_challenges: list[str] = Field(default_factory=list)
    policy_coverage_observations: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class AgentMessage(BaseModel):
    sender: Literal["PA", "CPA"]
    recipient: Literal["PA", "CPA"]
    intent: Literal["clarify", "confirm", "challenge", "request_evidence"]
    claims: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    notes: str = ""


class CommunicationReply(BaseModel):
    messages: list[AgentMessage] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class GapItem(BaseModel):
    gap_description: str = Field(description="One plain-language sentence stating the gap")
    plain_explanation: str = Field(
        default="",
        description="What this means and why it matters, in simple language for non-specialists",
    )
    policy_commitment: str = ""
    practical_need: str = ""
    implementation_evidence: str = ""
    responsible_institution: str = ""
    citations: list[str] = Field(default_factory=list)
    evidence_status: GapStatus = "insufficient_evidence"
    confidence: Confidence = "low"


class SynthesisReport(BaseModel):
    summary: str = Field(
        default="",
        description=(
            "Plain-language overview in 3-4 sentences (about 60-90 words): the overall finding, "
            "what is and is not covered, what it means for crop farmers, and the main evidence limitation"
        ),
    )
    key_findings: list[str] = Field(
        default_factory=list,
        description="Short plain-language takeaways; empty when evidence is insufficient",
    )
    policy_coverage_gaps: list[GapItem] = Field(default_factory=list)
    implementation_gaps: list[GapItem] = Field(default_factory=list)
    institutional_gaps: list[GapItem] = Field(default_factory=list)
    evidence_gaps: list[GapItem] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class QaDraft(BaseModel):
    """Compact schema for generation: evidence is attached from retrieval, not written by the model."""

    answer: str = Field(description="Farmer-facing answer, under 70 spoken words")
    recommendations: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    confidence: Confidence = "low"


class VerificationVerdict(BaseModel):
    """Compact verifier schema; supporting evidence is attached from KB2 hits in code."""

    status: VerificationStatus
    policy_conflicts: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)
    reasoning_summary: str = ""


class CorrectedTranscript(BaseModel):
    """Structured output for the ASR transcript normaliser."""

    corrected_text: str = Field(description="Cleaned farmer question; unchanged if already clear")
    crop: str | None = None
    confidence: Confidence = "low"
    notes: str = ""


ConversationIntent = Literal[
    "greeting",
    "social",
    "clarification",
    "livestock",
    "out_of_scope",
    "crop_only",
    "crop_question",
    "crop_problem",
    "general_crop_question",
]


class ConversationDecision(BaseModel):
    intent: ConversationIntent
    crop: str | None = None
    direct_reply: str | None = Field(
        default=None,
        description="Short spoken reply for greetings, clarification and out-of-scope turns; null for crop RAG turns",
    )
    reason: str = ""
    confidence: Confidence = "low"
