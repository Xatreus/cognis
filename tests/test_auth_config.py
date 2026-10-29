"""Production API tokens must be configured securely."""
import json

import pytest

from app.security.auth_config import validate_production_auth_config


def test_development_can_run_without_api_keys():
    validate_production_auth_config({"COGNIS_ENV": "development"})


def test_production_requires_authentication_configuration():
    with pytest.raises(ValueError, match="requires COGNIS_API_KEY"):
        validate_production_auth_config({"COGNIS_ENV": "production"})


def test_production_rejects_short_legacy_token():
    with pytest.raises(ValueError, match="at least 32 characters"):
        validate_production_auth_config({
            "COGNIS_ENV": "production",
            "COGNIS_API_KEY": "too-short",
        })


def test_production_rejects_short_tenant_tokens():
    with pytest.raises(ValueError, match="Every production API token"):
        validate_production_auth_config({
            "COGNIS_ENV": "production",
            "COGNIS_API_KEYS_JSON": json.dumps({"short": "tenant-a"}),
        })


def test_production_rejects_invalid_or_empty_tenant_map():
    with pytest.raises(ValueError, match="valid JSON object"):
        validate_production_auth_config({
            "COGNIS_ENV": "production",
            "COGNIS_API_KEYS_JSON": "{not-json",
        })
    with pytest.raises(ValueError, match="non-empty JSON object"):
        validate_production_auth_config({
            "COGNIS_ENV": "production",
            "COGNIS_API_KEYS_JSON": "{}",
        })


def test_production_accepts_long_tokens_mapped_to_tenants():
    validate_production_auth_config({
        "COGNIS_ENV": "production",
        "COGNIS_API_KEY": "a" * 40,
        "COGNIS_API_KEYS_JSON": json.dumps({
            "b" * 40: "tenant-a",
            "c" * 40: "tenant-b",
        }),
    })


def test_production_rejects_empty_tenant_identity():
    with pytest.raises(ValueError, match="non-empty tenant ID"):
        validate_production_auth_config({
            "COGNIS_ENV": "production",
            "COGNIS_API_KEYS_JSON": json.dumps({"x" * 40: "  "}),
        })
