"""Fail-closed validation for production API bearer-token configuration."""
from __future__ import annotations

import json
from collections.abc import Mapping


MIN_PRODUCTION_TOKEN_LENGTH = 32


def validate_production_auth_config(env: Mapping[str, str]) -> None:
    """Raise ValueError for missing, malformed, or weak production API tokens."""
    if env.get("COGNIS_ENV", "development").strip().lower() != "production":
        return

    legacy_key = env.get("COGNIS_API_KEY", "").strip()
    raw_map = env.get("COGNIS_API_KEYS_JSON", "").strip()

    if legacy_key and len(legacy_key) < MIN_PRODUCTION_TOKEN_LENGTH:
        raise ValueError(
            f"COGNIS_API_KEY must be at least {MIN_PRODUCTION_TOKEN_LENGTH} characters in production."
        )

    if not legacy_key and not raw_map:
        raise ValueError(
            "Production requires COGNIS_API_KEY or COGNIS_API_KEYS_JSON."
        )

    if raw_map:
        try:
            mapping = json.loads(raw_map)
        except json.JSONDecodeError as exc:
            raise ValueError("COGNIS_API_KEYS_JSON must contain a valid JSON object.") from exc

        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("COGNIS_API_KEYS_JSON must be a non-empty JSON object.")

        for token, tenant_id in mapping.items():
            if not isinstance(token, str) or len(token) < MIN_PRODUCTION_TOKEN_LENGTH:
                raise ValueError(
                    f"Every production API token must be at least {MIN_PRODUCTION_TOKEN_LENGTH} characters."
                )
            if not isinstance(tenant_id, str) or not tenant_id.strip():
                raise ValueError("Every production API token must map to a non-empty tenant ID.")
