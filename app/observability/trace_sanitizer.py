"""Bound and redact optional agent trace metadata before returning or persisting it.

This is defense-in-depth, not a guarantee that arbitrary user data or PII is
removed. Treat traces as sensitive, collect them only when explicitly enabled,
and configure retention/access controls for deployments.
"""
from __future__ import annotations

import re
from typing import Any

_MAX_DEPTH = 6
_MAX_ITEMS = 100
_MAX_STRING_CHARS = 2_000
_REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"(?i)(authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"secret|password|credential|cookie|private[_-]?key|client[_-]?secret)"
)
_STRING_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def _sanitize_string(value: str) -> str:
    result = value[:_MAX_STRING_CHARS]
    for pattern in _STRING_PATTERNS:
        result = pattern.sub(_REDACTED, result)
    return result


def sanitize_trace(value: Any, *, _depth: int = 0) -> Any:
    """Return a JSON-friendly, bounded trace with common credential patterns redacted."""
    if _depth >= _MAX_DEPTH:
        return "[MAX_DEPTH]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_ITEMS:
                cleaned["_truncated"] = True
                break
            safe_key = _sanitize_string(str(key))[:100]
            cleaned[safe_key] = (
                _REDACTED
                if _SENSITIVE_KEY.search(safe_key)
                else sanitize_trace(item, _depth=_depth + 1)
            )
        return cleaned
    if isinstance(value, (list, tuple)):
        result = [sanitize_trace(item, _depth=_depth + 1) for item in value[:_MAX_ITEMS]]
        if len(value) > _MAX_ITEMS:
            result.append("[TRUNCATED]")
        return result
    return _sanitize_string(str(value))


def sanitize_tool_calls(value: Any) -> list[dict[str, Any]]:
    """Sanitize tool-call records and ignore entries with unsupported shapes."""
    if not isinstance(value, (list, tuple)):
        return []
    cleaned = []
    for item in value[:_MAX_ITEMS]:
        safe_item = sanitize_trace(item)
        if isinstance(safe_item, dict):
            cleaned.append(safe_item)
    return cleaned
