"""Production egress proxy policy for user-supplied connected targets."""
from __future__ import annotations

import os
from urllib.parse import urlparse


class EgressProxyConfigurationError(ValueError):
    """Raised when production connected-target egress is not safely configured."""


def validate_egress_proxy_url(value: str) -> str:
    """Validate an operator-controlled HTTP(S) proxy URL, never a user-supplied URL."""
    parsed = urlparse(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise EgressProxyConfigurationError(
            "COGNIS_EGRESS_PROXY_URL must be an HTTP(S) proxy URL without embedded credentials, path, query, or fragment."
        )
    try:
        parsed.port
    except ValueError as exc:
        raise EgressProxyConfigurationError("COGNIS_EGRESS_PROXY_URL contains an invalid port.") from exc
    return value.strip().rstrip("/")


def connected_target_proxy_url() -> str | None:
    """Return the configured egress proxy, failing closed for production targets."""
    value = os.getenv("COGNIS_EGRESS_PROXY_URL", "").strip()
    if not value:
        from app.main import COGNIS_ENV
        if COGNIS_ENV == "production":
            raise EgressProxyConfigurationError(
                "Connected-target evaluation is disabled in production until a policy-enforcing COGNIS_EGRESS_PROXY_URL is configured."
            )
        return None
    return validate_egress_proxy_url(value)
