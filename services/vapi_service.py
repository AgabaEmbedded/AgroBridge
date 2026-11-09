"""Vapi integration.

Vapi sends two kinds of traffic to this service:

1. Server events (assistant-request, status-update, end-of-call-report, ...).
2. Custom-LLM requests, because the transient assistant returned for inbound calls points its
   model at ``<public base>/vapi`` and Vapi appends ``/chat/completions``.

The custom LLM endpoint is OpenAI-compatible and streams SSE when ``stream=true``.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from agents.qa_graph import run_question_answer
from services.audit_service import new_audit_id
from services.config import settings

logger = logging.getLogger("agrobridge.vapi")
router = APIRouter(prefix="/vapi", tags=["vapi"])

FALLBACK = (
    "I am having trouble checking the guidance right now. Please try again shortly "
    "or contact your local agricultural extension officer."
)
FIRST_MESSAGE = "Hello! I am AgroBridge. What can I help you with?"


def _public_base(request: Request) -> str:
    if settings.vapi_public_base_url:
        return settings.vapi_public_base_url.rstrip("/")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    if host:
        return f"{proto}://{host}".rstrip("/")
    return str(request.base_url).rstrip("/")


def assistant_config(request: Request) -> dict[str, Any]:
    assistant: dict[str, Any] = {
        "name": "AgroBridge",
        "firstMessage": FIRST_MESSAGE,
        "model": {
            "provider": "custom-llm",
            "model": "agrobridge",
            "url": f"{_public_base(request)}/vapi",
        },
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-2-phonecall",
            "language": "en",
            "smartFormat": True,
            "keywords": [
                "maize:4",
                "AgroBridge:2",
                "soil:3",
                "seedbed:2",
                "fertilizer:2",
                "planting:2",
                "cassava:2",
                "rice:2",
                "tomato:2",
                "pepper:2",
            ],
        },
    }
    if settings.elevenlabs_voice_id:
        assistant["voice"] = {
            "provider": "11labs",
            "model": "eleven_flash_v2_5",
            "voiceId": settings.elevenlabs_voice_id,
            "optimizeStreamingLatency": 4,
        }
    return assistant


def _check_webhook_auth(request: Request) -> None:
    if not settings.vapi_webhook_secret:
        return
    supplied = request.headers.get("x-vapi-secret", "")
    if not secrets.compare_digest(supplied, settings.vapi_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid Vapi webhook secret.")


def _check_llm_auth(request: Request) -> None:
    if not settings.vapi_custom_llm_secret:
        return
    supplied = request.headers.get("authorization", "")
    expected = f"Bearer {settings.vapi_custom_llm_secret}"
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid custom-LLM credentials.")


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
            elif isinstance(part, str):
                parts.append(part)
        return " ".join(parts)
    return ""


def _history_and_question(messages: list[dict[str, Any]]) -> tuple[list[dict[str, str]], str]:
    user_indexes = [
        index
        for index, message in enumerate(messages)
        if message.get("role") == "user" and _content_text(message.get("content")).strip()
    ]
    if not user_indexes:
        return [], ""
    current_index = user_indexes[-1]
    question = _content_text(messages[current_index].get("content")).strip()
    history: list[dict[str, str]] = []
    for message in messages[:current_index]:
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = _content_text(message.get("content")).strip()
        if content:
            history.append({"role": role, "content": content})
    return history[-8:], question


def _conversation_id(request: Request, body: dict[str, Any]) -> str | None:
    call = body.get("call") or {}
    if isinstance(call, dict) and call.get("id"):
        return str(call["id"])
    header = request.headers.get("x-vapi-call-id")
    return header or None


async def _answer(question: str, history: list[dict[str, str]], conversation_id: str | None) -> dict[str, Any]:
    audit_id = new_audit_id()
    try:
        state = await run_question_answer(
            question,
            history=history,
            conversation_id=conversation_id,
            audit_id=audit_id,
            budget_seconds=settings.vapi_qa_budget_seconds,
            top_k=settings.top_k,
        )
        final = state.get("final") or {}
        answer = str(final.get("voice_answer") or final.get("answer") or FALLBACK).strip()
        return {
            "answer": answer or FALLBACK,
            "final": final,
            "audit_id": audit_id,
            "timings": state.get("timings") or {},
        }
    except Exception:
        logger.exception("Vapi QA turn failed")
        return {"answer": FALLBACK, "final": {}, "audit_id": audit_id, "timings": {}}


@router.post("/webhook")
async def vapi_webhook(request: Request) -> JSONResponse:
    _check_webhook_auth(request)
    body = await request.json()
    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(message, dict):
        raise HTTPException(status_code=400, detail="Expected a Vapi message object.")

    message_type = message.get("type")
    logger.info("Vapi webhook event: %s", message_type)

    if message_type == "assistant-request":
        return JSONResponse({"assistant": assistant_config(request)})

    if message_type == "tool-calls":
        return JSONResponse({"results": []})

    # status-update, end-of-call-report, transcript, conversation-update and other
    # informational events are acknowledged.
    return JSONResponse({"status": "received"})


@router.post("/chat/completions")
async def vapi_chat_completions(request: Request):
    _check_llm_auth(request)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Expected a JSON body.")

    messages = body.get("messages") or []
    history, question = _history_and_question(messages if isinstance(messages, list) else [])
    logger.info(
        "Vapi custom LLM turn: %d message(s), %d history message(s), call=%s",
        len(messages),
        len(history),
        _conversation_id(request, body),
    )
    result = await _answer(question, history, _conversation_id(request, body))

    response_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    model = str(body.get("model") or "agrobridge")
    answer = result["answer"]

    if not body.get("stream"):
        return JSONResponse(
            {
                "id": response_id,
                "object": "chat.completion",
                "created": created,
                "model": model,
                "system_fingerprint": None,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": answer},
                        "logprobs": None,
                        "finish_reason": "stop",
                    }
                ],
            }
        )

    def event(delta: dict[str, Any], finish_reason: str | None = None) -> str:
        payload = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "system_fingerprint": None,
            "choices": [
                {"index": 0, "delta": delta, "logprobs": None, "finish_reason": finish_reason}
            ],
        }
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def stream():
        yield event({"role": "assistant"})
        # The graph returns a complete answer; chunk it for the OpenAI SSE contract.
        for start in range(0, len(answer), 40):
            yield event({"content": answer[start : start + 40]})
        yield event({}, "stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
