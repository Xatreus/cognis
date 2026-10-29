"""Bounded HTTP response parsing for untrusted agent/provider endpoints."""
from __future__ import annotations

import json
from typing import Any

import httpx


DEFAULT_MAX_RESPONSE_BYTES = 1_000_000


class TargetResponseTooLarge(RuntimeError):
    """Raised when an upstream target returns more data than Cognis will accept."""


async def post_json_bounded(
    client: httpx.AsyncClient,
    url: str,
    *,
    json_body: Any,
    headers: dict[str, str],
    timeout_seconds: float,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> Any:
    """POST JSON and parse a bounded response without buffering an unlimited body."""
    if max_response_bytes < 1:
        raise ValueError("max_response_bytes must be positive")

    body = bytearray()
    async with client.stream(
        "POST",
        url,
        json=json_body,
        headers=headers,
        timeout=timeout_seconds,
        follow_redirects=False,
    ) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > max_response_bytes:
                raise TargetResponseTooLarge(
                    f"Target response exceeded {max_response_bytes} bytes"
                )
            body.extend(chunk)

    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Target response was not valid JSON.") from exc
