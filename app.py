from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from agents.gap_graph import run_gap_analysis
from agents.qa_graph import run_question_answer
from services.audit_service import new_audit_id
from services.config import settings
from services.embedding_service import dimension, warmup
from services.retrieval_service import collection_count

load_dotenv(Path(__file__).resolve().parent / ".env")

LOG_DIR = settings.audit_dir
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_handlers: list[logging.Handler] = [logging.StreamHandler()]
if not os.getenv("AGROBRIDGE_NO_FILE_LOG"):
    _handlers.append(logging.FileHandler(LOG_DIR / "agrobridge.log", encoding="utf-8"))
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, handlers=_handlers)
logger = logging.getLogger("agrobridge")

SYSTEM_FALLBACK = (
    "I am unable to check the guidance right now. Please try again shortly "
    "or contact your local agricultural extension officer."
)

# Short-term conversation memory: in-process only, keyed by the provider's
# conversation/call id (or a hash of the caller number), dropped after the TTL or cap.
_conversation_history: dict[str, dict[str, Any]] = {}


def parse_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    try:
        return dict(payload)
    except Exception:
        return {}


async def read_payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").lower()
    try:
        if "application/json" in content_type:
            return parse_payload(await request.json())
        form = await request.form()
        return parse_payload(form)
    except Exception:
        try:
            return parse_payload(await request.json())
        except Exception:
            return {}


def conversation_key(data: dict[str, Any]) -> str | None:
    """Identify a call/chat session from the webhook payload.

    Prefers provider ids; falls back to a truncated SHA-256 of the caller number so raw
    phone numbers are never stored. Returns None when the payload has no stable id; that
    turn stays stateless instead of sharing memory with other callers.
    """
    for name in (
        "conversation_id",
        "conversationId",
        "call_id",
        "callId",
        "call_sid",
        "callSid",
        "session_id",
        "sessionId",
    ):
        value = data.get(name)
        if value:
            return str(value)
    for name in (
        "from",
        "caller",
        "from_number",
        "fromNumber",
        "caller_number",
        "phone",
        "phone_number",
    ):
        value = data.get(name)
        if value:
            digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:24]
            return f"caller:{digest}"
    return None


def load_history(key: str | None) -> list[dict[str, str]]:
    if not key:
        return []
    entry = _conversation_history.get(key)
    if entry is None:
        return []
    if time.monotonic() - entry["updated"] > settings.history_ttl_seconds:
        _conversation_history.pop(key, None)
        return []
    return list(entry["messages"])


def save_history(key: str | None, question: str, answer: str) -> None:
    if not key:
        return
    entry = _conversation_history.setdefault(key, {"messages": [], "updated": 0.0})
    entry["messages"].extend(
        [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
    )
    del entry["messages"][: -max(1, settings.history_max_messages)]
    entry["updated"] = time.monotonic()
    if len(_conversation_history) > 1000:
        cutoff = entry["updated"] - settings.history_ttl_seconds
        for stale_key in [k for k, v in _conversation_history.items() if v["updated"] < cutoff]:
            _conversation_history.pop(stale_key, None)


def clear_history(key: str | None) -> None:
    if key:
        _conversation_history.pop(key, None)


def describe_hits(hits: list[dict[str, Any]], preview_chars: int = 200) -> list[dict[str, Any]]:
    described = []
    for hit in hits:
        distance = float(hit.get("distance", 0.0))
        described.append(
            {
                "citation": hit.get("citation"),
                "document_name": hit.get("document_name"),
                "page_number": hit.get("page_number"),
                "chunk_index": hit.get("chunk_index"),
                "knowledge_base": hit.get("knowledge_base"),
                "distance": round(distance, 4),
                "used": distance <= settings.min_relevance_distance,
                "preview": str(hit.get("text", ""))[:preview_chars],
            }
        )
    return described


async def answer_farmer(question: str, conversation_id: str | None = None) -> dict[str, Any]:
    """Run the question-answer graph for a voice turn and return its final state."""
    history = load_history(conversation_id)
    audit_id = new_audit_id()
    state = await run_question_answer(
        question,
        history=history,
        conversation_id=conversation_id,
        audit_id=audit_id,
        budget_seconds=settings.qa_budget_seconds,
        top_k=settings.top_k,
    )
    final = state.get("final") or {}
    voice_answer = str(final.get("voice_answer") or SYSTEM_FALLBACK)
    save_history(conversation_id, question, voice_answer)
    return {
        "audit_id": audit_id,
        "final": final,
        "draft": state.get("draft") or {},
        "verification": state.get("verification") or {},
        "hits": state.get("hits") or [],
        "policy_hits": state.get("policy_hits") or [],
        "timings": state.get("timings") or {},
        "history_used": len(history),
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await run_in_threadpool(warmup)
        logger.info(
            "Embedding model ready (dim=%s); KB1=%s chunks, KB2=%s chunks",
            dimension(),
            collection_count("KB1"),
            collection_count("KB2"),
        )
    except Exception:
        logger.exception("Could not initialize the embedding model or knowledge bases")
    yield


app = FastAPI(title="AgroBridge", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Gap-Token", "X-Debug-Token"],
)


@app.get("/health")
async def health() -> dict[str, Any]:
    kb1 = await run_in_threadpool(collection_count, "KB1")
    kb2 = await run_in_threadpool(collection_count, "KB2")
    return {
        "status": "ok",
        "model": settings.llm_model,
        "indexed_chunks": kb1,
        "kb1_chunks": kb1,
        "kb2_chunks": kb2,
        "verifier_enabled": settings.verifier_enabled,
        "max_revisions": settings.max_revisions,
        "qa_budget_seconds": settings.qa_budget_seconds,
    }


def debug_allowed(request: Request) -> bool:
    host = request.client.host if request.client else ""
    if host in {"127.0.0.1", "::1"}:
        return True
    return bool(settings.debug_api_token) and secrets.compare_digest(
        request.headers.get("x-debug-token", ""), settings.debug_api_token
    )


@app.post("/debug/ask")
async def debug_ask(request: Request) -> JSONResponse:
    """Run the full QA graph (with verification/revision) and expose diagnostics.

    Local requests are always allowed. Remote callers must set DEBUG_API_TOKEN and send
    it as the X-Debug-Token header.
    """
    if not debug_allowed(request):
        raise HTTPException(
            status_code=403,
            detail=(
                "Debug endpoint is local-only. Set DEBUG_API_TOKEN and send "
                "X-Debug-Token to call it remotely."
            ),
        )

    data = await read_payload(request)
    question = str(
        data.get("question") or data.get("transcription") or data.get("text") or ""
    ).strip()
    top_k = max(1, min(int(data.get("top_k") or settings.top_k), 20))
    key = conversation_key(data)
    if str(data.get("reset_history", "")).lower() in {"1", "true", "yes"}:
        clear_history(key)
    history = load_history(key)

    started = time.perf_counter()
    audit_id = new_audit_id()
    state = await run_question_answer(
        question,
        history=history,
        conversation_id=key,
        audit_id=audit_id,
        budget_seconds=settings.qa_debug_budget_seconds,
        top_k=top_k,
    )
    total_ms = round((time.perf_counter() - started) * 1000, 1)

    final = state.get("final") or {}
    draft = state.get("draft") or {}
    verification = state.get("verification") or {}
    hits = state.get("hits") or []
    policy_hits = state.get("policy_hits") or []

    result = {
        "question": question,
        "conversation_id": key,
        "audit_id": audit_id,
        "stage": final.get("verification_status") or state.get("error") or "NEEDS_REVIEW",
        "answer": final.get("answer") or draft.get("answer") or "",
        "voice_answer": final.get("voice_answer") or "",
        "intent": final.get("intent") or state.get("intent"),
        "crop": final.get("crop") or state.get("crop"),
        "raw_question": final.get("raw_question") or state.get("raw_question") or question,
        "corrected_question": final.get("corrected_question") or state.get("corrected_question") or state.get("question"),
        "correction": state.get("correction") or final.get("correction") or {},
        "correction_status": state.get("correction_status"),
        "citations": final.get("citations") or [],
        "draft": draft,
        "verification": verification,
        "revisions": final.get("revisions", 0),
        "history_used": len(history),
        "hits": describe_hits(hits),
        "policy_hits": describe_hits(policy_hits),
        "timings": state.get("timings") or {},
        "total_ms": total_ms,
        "index": {
            "kb1_collection": settings.kb1_collection,
            "kb2_collection": settings.kb2_collection,
            "kb1_chunks": await run_in_threadpool(collection_count, "KB1"),
            "kb2_chunks": await run_in_threadpool(collection_count, "KB2"),
        },
        "config": {
            "model": settings.llm_model,
            "top_k": top_k,
            "max_revisions": settings.max_revisions,
            "verifier_enabled": settings.verifier_enabled,
            "min_relevance_distance": settings.min_relevance_distance,
            "max_output_tokens": settings.max_output_tokens,
            "qa_budget_seconds": settings.qa_debug_budget_seconds,
            "history_max_messages": settings.history_max_messages,
            "history_ttl_seconds": settings.history_ttl_seconds,
        },
        "dropped_citations": state.get("dropped_citations") or [],
    }
    if key:
        save_history(key, question, result["voice_answer"] or result["answer"])
    return JSONResponse(result)


@app.post("/api/gap-analysis")
async def gap_analysis(request: Request) -> JSONResponse:
    """Run the independent gap-analysis graph (KB2 policy + KB1 needs + communication)."""
    if settings.gap_api_token and not secrets.compare_digest(
        request.headers.get("x-gap-token", ""), settings.gap_api_token
    ):
        raise HTTPException(status_code=403, detail="Invalid or missing X-Gap-Token.")

    data = await read_payload(request)
    query = str(data.get("query") or data.get("question") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="A non-empty 'query' is required.")
    if len(query) > 2000:
        raise HTTPException(status_code=400, detail="'query' must be 2000 characters or fewer.")

    max_rounds = data.get("max_rounds")
    if max_rounds is not None:
        try:
            max_rounds = max(0, min(int(max_rounds), 4))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="'max_rounds' must be an integer.")

    audit_id = new_audit_id()
    try:
        state = await run_gap_analysis(query, max_rounds=max_rounds, audit_id=audit_id)
    except Exception:
        logger.exception("Gap-analysis workflow failed")
        raise HTTPException(status_code=502, detail="Gap-analysis workflow failed.") from None

    report = state.get("synthesis") or {}
    if not report:
        raise HTTPException(status_code=502, detail="Gap-analysis produced no report.")

    return JSONResponse(
        {
            "audit_id": audit_id,
            "query": query,
            "report": report,
            "communication": state.get("messages") or [],
            "rounds": state.get("rounds", 0),
            "policy_findings": state.get("policy") or {},
            "needs_findings": state.get("needs") or {},
            "timings": state.get("timings") or {},
            "dropped_citations": state.get("dropped_citations") or [],
        }
    )


@app.post("/")
async def handle_voicebip_webhook(request: Request):
    data = await read_payload(request)
    event_type = data.get("event") or data.get("event_type")
    key = conversation_key(data)
    logger.info(
        "Received Voicebip event: %s (memory: %s)", event_type, "keyed" if key else "stateless"
    )

    if event_type in {"call.initiated", "call.completed", "call.barge_in"}:
        return JSONResponse({"status": "received"})

    if event_type == "call.idle_silence":
        prompt = "Are you still there? Please tell me which crop or animal you need help with."
        return JSONResponse({"response": prompt, "text": prompt})

    if event_type == "turn":
        farmer_speech = str(data.get("transcription") or data.get("text") or "").strip()
        try:
            result = await answer_farmer(farmer_speech, key)
            reply = str(result["final"].get("voice_answer") or SYSTEM_FALLBACK)
        except Exception:
            logger.exception("Question-answer workflow failed")
            reply = SYSTEM_FALLBACK
        return JSONResponse({"response": reply, "text": reply})

    return JSONResponse(
        {
            "response": "Hello from AgroBridge. Please tell me what crop or animal you need help with.",
            "text": "Hello from AgroBridge. Please tell me what crop or animal you need help with.",
        }
    )


if __name__ == "__main__":
    import uvicorn

    # log_config=None keeps uvicorn from replacing the root handlers configured above,
    # so access and error lines land in logs/agrobridge.log too.
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False, log_config=None)
