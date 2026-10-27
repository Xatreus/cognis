"""Deterministic assertions for correctness and basic output-safety checks.

These checks are useful signals, not a substitute for a full security review or
adversarial testing. Security checks must be interpreted in context.
"""
from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class AssertionResult:
    name: str
    passed: bool
    message: str


# Deliberately conservative patterns for obvious credential-like output.
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)(?:api[_-]?key|client[_-]?secret|access[_-]?token)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,}"),
)


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value)


def evaluate_assertions(
    actual: Any,
    *,
    expected: Any | None = None,
    contains: tuple[str, ...] = (),
    not_contains: tuple[str, ...] = (),
    latency_ms: float | None = None,
    max_latency_ms: float | None = None,
    check_secrets: bool = True,
) -> list[AssertionResult]:
    """Evaluate deterministic checks without asking an LLM to grade itself."""
    text = _as_text(actual)
    results: list[AssertionResult] = []

    if expected is not None:
        results.append(AssertionResult(
            name="exact_match",
            passed=actual == expected or text == _as_text(expected),
            message="Output matches expected value." if (actual == expected or text == _as_text(expected)) else "Output did not match expected value.",
        ))

    for fragment in contains:
        ok = fragment in text
        results.append(AssertionResult(
            name="contains",
            passed=ok,
            message=f"Required text {fragment!r} found." if ok else f"Required text {fragment!r} missing.",
        ))

    for fragment in not_contains:
        ok = fragment not in text
        results.append(AssertionResult(
            name="not_contains",
            passed=ok,
            message=f"Forbidden text {fragment!r} absent." if ok else f"Forbidden text {fragment!r} present.",
        ))

    if max_latency_ms is not None and latency_ms is not None:
        ok = latency_ms <= max_latency_ms
        results.append(AssertionResult(
            name="latency_budget",
            passed=ok,
            message=f"Latency {latency_ms:.3f} ms is within budget." if ok else f"Latency {latency_ms:.3f} ms exceeded {max_latency_ms:.3f} ms.",
        ))

    if check_secrets:
        matches = [pattern.search(text) for pattern in _SECRET_PATTERNS]
        leaked = next((match.group(0) for match in matches if match), None)
        results.append(AssertionResult(
            name="obvious_secret_leak",
            passed=leaked is None,
            message="No obvious credential pattern detected." if leaked is None else "Output contains a pattern resembling a secret; inspect securely.",
        ))

    return results
