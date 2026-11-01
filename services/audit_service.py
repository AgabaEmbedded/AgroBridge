"""Audit trail for both workflows.

One JSON object per request is appended to ``logs/audit-YYYY-MM-DD.jsonl``. Records carry
inputs, agent outputs, retrieval citations and verification results, but never secrets or
raw credentials.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from services.config import settings

_SECRET_KEYS = re.compile(r"(api[_-]?key|token|password|secret|authorization)", re.IGNORECASE)


def new_audit_id() -> str:
    return uuid.uuid4().hex


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "<redacted>" if _SECRET_KEYS.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def write_audit(workflow: str, record: dict[str, Any], audit_id: str | None = None) -> str:
    audit_id = audit_id or new_audit_id()
    entry = {
        "audit_id": audit_id,
        "workflow": workflow,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **_redact(record),
    }
    if not settings.audit_enabled:
        return audit_id

    try:
        settings.audit_dir.mkdir(parents=True, exist_ok=True)
        filename = settings.audit_dir / f"audit-{datetime.now(timezone.utc):%Y%m%d}.jsonl"
        with filename.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass
    return audit_id
