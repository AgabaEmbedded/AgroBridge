"""Central configuration for AgroBridge services and agents.

Every setting is environment-driven so agent code never hardcodes model names, keys,
paths or budgets. Values mirror the existing `.env` names where they already existed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    return _env(name, "true" if default else "false").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    base_dir: Path = BASE_DIR
    documents_dir: Path = field(default_factory=lambda: BASE_DIR / "documents")
    chroma_dir: Path = field(default_factory=lambda: BASE_DIR / "chroma_db")
    audit_dir: Path = field(default_factory=lambda: BASE_DIR / "logs")
    embedding_model: str = field(default_factory=lambda: _env("EMBEDDING_MODEL", "intfloat/multilingual-e5-small"))
    kb1_collection: str = field(default_factory=lambda: _env("KB1_COLLECTION", "agrobridge_kb1"))
    kb2_collection: str = field(default_factory=lambda: _env("KB2_COLLECTION", "agrobridge_kb2"))

    # Generation LLM (independent of the embedding model).
    llm_api_key: str = field(default_factory=lambda: _env("DEEPSEEK_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: _env("DEEPSEEK_MODEL", "deepseek-flash"))
    llm_base_url: str = field(default_factory=lambda: _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    llm_timeout_seconds: float = field(default_factory=lambda: _env_float("LLM_TIMEOUT_SECONDS", 8.0))
    agent_timeout_seconds: float = field(default_factory=lambda: _env_float("AGENT_TIMEOUT_SECONDS", 45.0))
    max_output_tokens: int = field(default_factory=lambda: _env_int("MAX_OUTPUT_TOKENS", 220))
    qa_answer_max_tokens: int = field(default_factory=lambda: _env_int("QA_ANSWER_MAX_TOKENS", 320))
    verifier_max_tokens: int = field(default_factory=lambda: _env_int("VERIFIER_MAX_TOKENS", 300))
    temperature: float = field(default_factory=lambda: _env_float("LLM_TEMPERATURE", 0.2))

    # Retrieval.
    top_k: int = field(default_factory=lambda: _env_int("TOP_K", 6))
    gap_top_k: int = field(default_factory=lambda: _env_int("GAP_TOP_K", 6))
    min_relevance_distance: float = field(default_factory=lambda: _env_float("MIN_RELEVANCE_DISTANCE", 0.15))

    # Question-answer workflow.
    verifier_enabled: bool = field(default_factory=lambda: _env_bool("VERIFIER_ENABLED", True))
    max_revisions: int = field(default_factory=lambda: _env_int("MAX_REVISIONS", 2))
    qa_budget_seconds: float = field(default_factory=lambda: _env_float("QA_BUDGET_SECONDS", 4.3))
    qa_debug_budget_seconds: float = field(default_factory=lambda: _env_float("QA_DEBUG_BUDGET_SECONDS", 60.0))

    # Policy Analyzer workflow.
    gap_max_rounds: int = field(default_factory=lambda: _env_int("GAP_MAX_ROUNDS", 2))
    gap_timeout_seconds: float = field(default_factory=lambda: _env_float("GAP_TIMEOUT_SECONDS", 240.0))
    gap_max_output_tokens: int = field(default_factory=lambda: _env_int("GAP_MAX_OUTPUT_TOKENS", 1200))

    # Conversation memory (voice turns).
    history_max_messages: int = field(default_factory=lambda: _env_int("HISTORY_MAX_MESSAGES", 8))
    history_ttl_seconds: float = field(default_factory=lambda: _env_float("HISTORY_TTL_SECONDS", 1800))

    # Transcript robustness: an optional LLM normaliser before routing, and/or a prompt hint.
    transcript_correction_enabled: bool = field(
        default_factory=lambda: _env_bool("TRANSCRIPT_CORRECTION_ENABLED", True)
    )
    transcript_correction_timeout: float = field(
        default_factory=lambda: _env_float("TRANSCRIPT_CORRECTION_TIMEOUT", 3.0)
    )
    noisy_transcript_hint: bool = field(
        default_factory=lambda: _env_bool("NOISY_TRANSCRIPT_HINT", True)
    )

    debug_api_token: str = field(default_factory=lambda: _env("DEBUG_API_TOKEN", ""))
    gap_api_token: str = field(default_factory=lambda: _env("GAP_API_TOKEN", ""))
    # Vapi telephony integration.
    vapi_public_base_url: str = field(default_factory=lambda: _env("VAPI_PUBLIC_BASE_URL", ""))
    vapi_webhook_secret: str = field(default_factory=lambda: _env("VAPI_WEBHOOK_SECRET", ""))
    vapi_custom_llm_secret: str = field(default_factory=lambda: _env("VAPI_CUSTOM_LLM_SECRET", ""))
    elevenlabs_voice_id: str = field(
        default_factory=lambda: (
            _env("ELEVENLABS_VOICE_ID", "") or _env("ELEVENLAB_VOICE_ID", "")
        ).strip()
    )

    frontend_origins: list[str] = field(
        default_factory=lambda: [
            item.strip()
            for item in _env(
                "FRONTEND_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
            ).split(",")
            if item.strip()
        ]
    )
    audit_enabled: bool = field(default_factory=lambda: _env_bool("AUDIT_ENABLED", True))


settings = Settings()
