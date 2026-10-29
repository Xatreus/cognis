"""Bound and redact optional agent trace metadata before returning or persisting it.

This is defense-in-depth, not a guarantee that arbitrary user data or PII is
removed. Treat traces as sensitive, collect them only when explicitly enabled,
and configure retention/access controls for deployments.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_MAX_DEPTH = 6
_MAX_ITEMS = 100
_MAX_NODES = 5_000
_MAX_TOTAL_CHARS = 100_000
_MAX_STRING_CHARS = 2_000
_REDACTED = "[REDACTED]"
_TRUNCATED = "[TRUNCATED]"
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


@dataclass
class _Budget:
    nodes_left: int = _MAX_NODES
    chars_left: int = _MAX_TOTAL_CHARS


def _sanitize_string(value: str, budget: _Budget) -> str:
    if budget.chars_left <= 0:
        return _TRUNCATED
    result = value[: min(_MAX_STRING_CHARS, budget.chars_left)]
    budget.chars_left -= len(result)
    for pattern in _STRING_PATTERNS:
        result = pattern.sub(_REDACTED, result)
    return result


def _sanitize(value: Any, *, depth: int, budget: _Budget) -> Any:
    if budget.nodes_left <= 0 or budget.chars_left <= 0:
        return _TRUNCATED
    budget.nodes_left -= 1
    if depth >= _MAX_DEPTH:
        return "[MAX_DEPTH]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_string(value, budget)
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_ITEMS or budget.nodes_left <= 0 or budget.chars_left <= 0:
                cleaned["_truncated"] = True
                break
            safe_key = _sanitize_string(str(key), budget)[:100]
            if _SENSITIVE_KEY.search(safe_key):
                cleaned[safe_key] = _REDACTED
            else:
                cleaned[safe_key] = _sanitize(item, depth=depth + 1, budget=budget)
        return cleaned
    if isinstance(value, (list, tuple)):
        result = []
        for item in value[:_MAX_ITEMS]:
            if budget.nodes_left <= 0 or budget.chars_left <= 0:
                result.append(_TRUNCATED)
                break
            result.append(_sanitize(item, depth=depth + 1, budget=budget))
        if len(value) > _MAX_ITEMS:
            result.append(_TRUNCATED)
        return result
    return _sanitize_string(str(value), budget)


def sanitize_trace(value: Any) -> Any:
    """Return a JSON-friendly, redacted trace under shared node/character budgets."""
    return _sanitize(value, depth=0, budget=_Budget())


def sanitize_tool_calls(value: Any) -> list[dict[str, Any]]:
    """Sanitize tool-call records and ignore entries with unsupported shapes."""
    if not isinstance(value, (list, tuple)):
        return []
    cleaned = []
    budget = _Budget()
    for item in value[:_MAX_ITEMS]:
        if budget.nodes_left <= 0 or budget.chars_left <= 0:
            break
        safe_item = _sanitize(item, depth=0, budget=budget)
        if isinstance(safe_item, dict):
            cleaned.append(safe_item)
    return cleaned
