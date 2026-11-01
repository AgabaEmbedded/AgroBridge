"""Generation-LLM service shared by every agent.

Structured outputs are requested as JSON, validated with Pydantic, and retried once with
the validation error when the model returns malformed content. Transport errors surface as
``LLMServiceError`` so callers can degrade gracefully.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Type, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from services.config import settings

T = TypeVar("T", bound=BaseModel)

_client: AsyncOpenAI | None = None
logger = logging.getLogger("agrobridge.llm")


class LLMServiceError(RuntimeError):
    """Raised when the generation model cannot produce a usable response."""


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.llm_api_key or "missing-api-key",
            base_url=settings.llm_base_url,
            timeout=settings.agent_timeout_seconds,
            max_retries=0,
        )
    return _client


def _json_slice(text: str) -> str:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("response did not contain a JSON object")
    return text[start : end + 1]


async def chat_json(
    system: str,
    user: str,
    schema: Type[T],
    *,
    max_tokens: int | None = None,
    timeout: float | None = None,
    temperature: float | None = None,
) -> T:
    schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"{user}\n\n"
                "Return only a JSON object that validates against this JSON Schema. "
                "No prose, no markdown fences.\n"
                f"{schema_text}"
            ),
        },
    ]
    request = {
        "model": settings.llm_model,
        "messages": messages,
        "max_tokens": max_tokens or settings.max_output_tokens,
        "temperature": settings.temperature if temperature is None else temperature,
        "timeout": timeout or settings.agent_timeout_seconds,
        "response_format": {"type": "json_object"},
        "extra_body": {"thinking": {"type": "disabled"}},
    }

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            completion = await get_client().chat.completions.create(**request)
        except Exception as exc:  # network, timeout, provider errors
            logger.warning("LLM request failed: %s: %s", type(exc).__name__, str(exc)[:300])
            raise LLMServiceError(
                f"LLM request failed: {type(exc).__name__}: {str(exc)[:200]}"
            ) from exc

        content = (completion.choices[0].message.content or "").strip()
        try:
            return schema.model_validate(json.loads(_json_slice(content)))
        except (ValueError, ValidationError) as exc:
            last_error = exc
            if completion.choices[0].finish_reason == "length" and attempt == 0:
                request["max_tokens"] = min(4000, int(request["max_tokens"]) * 2)
            logger.warning(
                "invalid structured output (attempt %s): %s | finish=%s | content=%r",
                attempt,
                str(exc)[:300],
                completion.choices[0].finish_reason,
                content[:500],
            )
            if attempt == 0:
                messages.append({"role": "assistant", "content": content[:4000] or "{}"})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"That reply was invalid: {exc}. "
                            "Return only corrected JSON matching the schema."
                        ),
                    }
                )
                request["messages"] = messages
    raise LLMServiceError(f"Invalid structured LLM output: {last_error}")


async def chat_text(
    system: str,
    user: str,
    *,
    max_tokens: int | None = None,
    timeout: float | None = None,
    temperature: float | None = None,
) -> str:
    try:
        completion = await get_client().chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens or settings.max_output_tokens,
            temperature=settings.temperature if temperature is None else temperature,
            timeout=timeout or settings.agent_timeout_seconds,
            extra_body={"thinking": {"type": "disabled"}},
        )
    except Exception as exc:
        raise LLMServiceError(f"LLM request failed: {type(exc).__name__}") from exc
    text = (completion.choices[0].message.content or "").strip()
    if not text:
        raise LLMServiceError("LLM returned an empty completion")
    return text
