"""Gap-analysis agents: policy analyst (KB2), needs analyst (KB1), communication, synthesis."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from agents import prompts
from agents.evidence import (
    format_evidence,
    sanitize_citations,
    sanitize_evidence,
    sanitize_report,
)
from agents.runtime import call_timeout, expired, timings_with
from agents.schemas import (
    AgentMessage,
    CommunicationReply,
    GapItem,
    NeedsFindings,
    PolicyFindings,
    SynthesisReport,
)
from services.audit_service import write_audit
from services.config import settings
from services.llm_service import LLMServiceError, chat_json
from services.retrieval_service import search_kb1, search_kb2


def _merge_hits(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for hit in group:
            merged.setdefault(hit["citation"], hit)
    return list(merged.values())


def _sanitize_messages(messages: list[AgentMessage], hits: list[dict[str, Any]]) -> list[AgentMessage]:
    cleaned: list[AgentMessage] = []
    for message in messages:
        evidence, _ = sanitize_evidence(message.evidence, hits)
        citations, _ = sanitize_citations(message.citations, hits)
        cleaned.append(
            AgentMessage(
                sender=message.sender,
                recipient=message.recipient,
                intent=message.intent,
                claims=message.claims,
                questions=message.questions,
                evidence=evidence,
                citations=citations,
                notes=message.notes,
            )
        )
    return cleaned


async def policy_analyst_node(state: dict) -> dict:
    started = time.monotonic()
    query = (
        state["query"]
        + " government policy commitments implementation targets budgets institutions "
        "implementation report evaluation"
    )
    try:
        hits = await asyncio.to_thread(search_kb2, query, None, settings.gap_top_k)
    except Exception:
        return {
            "policy": PolicyFindings().model_dump(),
            "policy_hits": [],
            "error": "kb2_retrieval_error",
            "timings": timings_with(state, ga1_ms=(time.monotonic() - started) * 1000),
        }

    if not hits or expired(state, minimum=3.0):
        return {
            "policy": PolicyFindings().model_dump(),
            "policy_hits": hits,
            "timings": timings_with(state, ga1_ms=(time.monotonic() - started) * 1000),
        }

    user = (
        f"Policy analysis question: {state['query']}\n\n"
        f"KB2 policy/implementation evidence:\n{format_evidence(hits)}\n\n"
        "Extract commitments, institutions, targets, implementation evidence and policy gaps."
    )
    try:
        findings = await chat_json(
            prompts.GA1_SYSTEM,
            user,
            PolicyFindings,
            max_tokens=settings.gap_max_output_tokens,
            timeout=call_timeout(state, 0.85),
        )
    except LLMServiceError:
        return {
            "policy": PolicyFindings().model_dump(),
            "policy_hits": hits,
            "error": "ga1_llm_error",
            "timings": timings_with(state, ga1_ms=(time.monotonic() - started) * 1000),
        }

    findings.citations, _ = sanitize_citations(findings.citations, hits)
    return {
        "policy": findings.model_dump(),
        "policy_hits": hits,
        "timings": timings_with(state, ga1_ms=(time.monotonic() - started) * 1000),
    }


async def needs_analyst_node(state: dict) -> dict:
    started = time.monotonic()
    try:
        hits = await asyncio.to_thread(
            search_kb1,
            f"{state['query']} farmer challenges technical requirements extension services",
            None,
            settings.gap_top_k,
        )
    except Exception:
        return {
            "needs": NeedsFindings().model_dump(),
            "needs_hits": [],
            "error": "kb1_retrieval_error",
            "timings": timings_with(state, ga2_ms=(time.monotonic() - started) * 1000),
        }

    policy = state.get("policy") or {}
    if not hits or expired(state, minimum=3.0):
        return {
            "needs": NeedsFindings().model_dump(),
            "needs_hits": hits,
            "timings": timings_with(state, ga2_ms=(time.monotonic() - started) * 1000),
        }

    user = (
        f"Analysis question: {state['query']}\n\n"
        f"GA1 policy findings:\n{json.dumps(policy, ensure_ascii=False)}\n\n"
        f"KB1 agricultural evidence:\n{format_evidence(hits)}\n\n"
        "Identify practical challenges, farmer needs, technical requirements and coverage observations."
    )
    try:
        findings = await chat_json(
            prompts.GA2_SYSTEM,
            user,
            NeedsFindings,
            max_tokens=settings.gap_max_output_tokens,
            timeout=call_timeout(state, 0.85),
        )
    except LLMServiceError:
        return {
            "needs": NeedsFindings().model_dump(),
            "needs_hits": hits,
            "error": "ga2_llm_error",
            "timings": timings_with(state, ga2_ms=(time.monotonic() - started) * 1000),
        }

    findings.citations, _ = sanitize_citations(findings.citations, hits)
    return {
        "needs": findings.model_dump(),
        "needs_hits": hits,
        "timings": timings_with(state, ga2_ms=(time.monotonic() - started) * 1000),
    }


def _communication_context(state: dict, messages: list[dict[str, Any]]) -> str:
    return (
        f"Analysis question: {state['query']}\n\n"
        f"GA1 findings:\n{json.dumps(state.get('policy') or {}, ensure_ascii=False)}\n\n"
        f"GA2 findings:\n{json.dumps(state.get('needs') or {}, ensure_ascii=False)}\n\n"
        f"Conversation so far:\n{json.dumps(messages[-8:], ensure_ascii=False)}"
    )


async def communication_node(state: dict) -> dict:
    """One structured exchange per round, alternating direction."""
    started = time.monotonic()
    rounds = int(state.get("rounds") or 0)
    max_rounds = int(state.get("max_rounds") or settings.gap_max_rounds)
    messages = list(state.get("messages") or [])
    policy_hits = list(state.get("policy_hits") or [])
    needs_hits = list(state.get("needs_hits") or [])

    if rounds >= max_rounds or expired(state, minimum=5.0):
        return {"rounds": max_rounds}

    context = _communication_context(state, messages)
    ga2_to_ga1 = rounds % 2 == 0

    try:
        if ga2_to_ga1:
            ask = await chat_json(
                prompts.GA2_COMMUNICATION_SYSTEM,
                context
                + "\n\nAsk GA1 whether the identified needs are covered by commitments, "
                "implementation evidence or budgets.",
                CommunicationReply,
                max_tokens=settings.gap_max_output_tokens,
                timeout=call_timeout(state, 0.6),
            )
            asked = _sanitize_messages(ask.messages, policy_hits + needs_hits)
            for message in asked:
                message.sender, message.recipient = "GA2", "GA1"

            query = " ".join(
                message.questions[0] if message.questions else message.notes
                for message in asked
            ) or state["query"]
            extra = await asyncio.to_thread(search_kb2, query, None, settings.gap_top_k)
            policy_hits = _merge_hits(policy_hits, extra)

            reply_context = (
                context
                + f"\n\nGA2's questions:\n{json.dumps([m.model_dump() for m in asked], ensure_ascii=False)}"
                + f"\n\nKB2 evidence:\n{format_evidence(extra)}"
            )
            reply = await chat_json(
                prompts.GA1_COMMUNICATION_SYSTEM,
                reply_context,
                CommunicationReply,
                max_tokens=settings.gap_max_output_tokens,
                timeout=call_timeout(state, 0.8),
            )
            answered = _sanitize_messages(reply.messages, policy_hits)
            for message in answered:
                message.sender, message.recipient = "GA1", "GA2"
        else:
            ask = await chat_json(
                prompts.GA1_COMMUNICATION_TO_GA2_SYSTEM,
                context
                + "\n\nAsk GA2 whether policy assumptions match technical and farmer realities.",
                CommunicationReply,
                max_tokens=settings.gap_max_output_tokens,
                timeout=call_timeout(state, 0.6),
            )
            asked = _sanitize_messages(ask.messages, policy_hits + needs_hits)
            for message in asked:
                message.sender, message.recipient = "GA1", "GA2"

            query = " ".join(
                message.questions[0] if message.questions else message.notes
                for message in asked
            ) or state["query"]
            extra = await asyncio.to_thread(search_kb1, query, None, settings.gap_top_k)
            needs_hits = _merge_hits(needs_hits, extra)

            reply_context = (
                context
                + f"\n\nGA1's questions:\n{json.dumps([m.model_dump() for m in asked], ensure_ascii=False)}"
                + f"\n\nKB1 evidence:\n{format_evidence(extra)}"
            )
            reply = await chat_json(
                prompts.GA2_COMMUNICATION_TO_GA1_SYSTEM,
                reply_context,
                CommunicationReply,
                max_tokens=settings.gap_max_output_tokens,
                timeout=call_timeout(state, 0.8),
            )
            answered = _sanitize_messages(reply.messages, needs_hits)
            for message in answered:
                message.sender, message.recipient = "GA2", "GA1"
    except LLMServiceError:
        return {
            "rounds": max_rounds,
            "messages": messages,
            "policy_hits": policy_hits,
            "needs_hits": needs_hits,
            "error": "communication_error",
            "timings": timings_with(state, communication_ms=(time.monotonic() - started) * 1000),
        }

    messages.extend(message.model_dump() for message in asked)
    messages.extend(message.model_dump() for message in answered)
    return {
        "rounds": rounds + 1,
        "messages": messages,
        "policy_hits": policy_hits,
        "needs_hits": needs_hits,
        "timings": timings_with(state, communication_ms=(time.monotonic() - started) * 1000),
    }


async def synthesis_node(state: dict) -> dict:
    started = time.monotonic()
    policy_hits = list(state.get("policy_hits") or [])
    needs_hits = list(state.get("needs_hits") or [])
    messages = list(state.get("messages") or [])
    all_hits = _merge_hits(policy_hits, needs_hits)

    if not all_hits:
        report = SynthesisReport(
            summary=(
                "No policy or agricultural evidence was retrieved, so no gap can be established."
            ),
            evidence_gaps=[
                GapItem(
                    gap_description="No relevant documents were retrieved from KB1 or KB2.",
                    evidence_status="insufficient_evidence",
                    confidence="low",
                )
            ],
            limitations=["Ingest documents into documents/KB1 and documents/KB2, then re-run."],
        )
    else:
        user = (
            f"Analysis question: {state['query']}\n\n"
            f"GA1 findings:\n{json.dumps(state.get('policy') or {}, ensure_ascii=False)}\n\n"
            f"GA2 findings:\n{json.dumps(state.get('needs') or {}, ensure_ascii=False)}\n\n"
            f"Communication history:\n{json.dumps(messages, ensure_ascii=False)}\n\n"
            f"Retrieved evidence:\n{format_evidence(all_hits, max_chars=900)}\n\n"
            "Synthesise the four gap categories, distinguishing confirmed shortfall, potential gap "
            "and insufficient evidence."
        )
        try:
            report = await chat_json(
                prompts.SYNTHESIS_SYSTEM,
                user,
                SynthesisReport,
                max_tokens=settings.gap_max_output_tokens,
                timeout=call_timeout(state, 0.9),
            )
        except LLMServiceError:
            report = SynthesisReport(
                summary="Synthesis failed after both agents produced findings.",
                limitations=["LLM synthesis error; see agent findings and communication history."],
                citations=[],
            )

    report, dropped = sanitize_report(report, all_hits)
    audit_record = {
        "query": state.get("query", ""),
        "agents_invoked": ["ga1", "ga2", "communication", "synthesis"],
        "rounds": state.get("rounds", 0),
        "knowledge_bases": ["KB1", "KB2"],
        "retrieved_citations": [hit.get("citation") for hit in needs_hits],
        "policy_citations": [hit.get("citation") for hit in policy_hits],
        "policy_findings": state.get("policy") or {},
        "needs_findings": state.get("needs") or {},
        "communication": messages,
        "synthesis": report.model_dump(),
        "timings": state.get("timings") or {},
        "dropped_citations": dropped,
        "error": state.get("error"),
    }
    write_audit("gap_analysis", audit_record, state.get("audit_id"))

    return {
        "synthesis": report.model_dump(),
        "dropped_citations": dropped,
        "timings": timings_with(state, synthesis_ms=(time.monotonic() - started) * 1000),
    }
