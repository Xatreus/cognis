"""Operator-controlled egress proxy configuration tests."""
import pytest

from app.security.egress import (
    EgressProxyConfigurationError,
    connected_target_proxy_url,
    validate_egress_proxy_url,
)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "file:///etc/passwd",
        "ftp://proxy.internal:3128",
        "http://user:password@proxy.internal:3128",
        "http://proxy.internal:3128/path",
        "http://proxy.internal:bad",
    ],
)
def test_rejects_invalid_egress_proxy_urls(value):
    with pytest.raises(EgressProxyConfigurationError):
        validate_egress_proxy_url(value)


def test_accepts_operator_controlled_http_proxy():
    assert validate_egress_proxy_url("http://egress-proxy.internal:3128") == (
        "http://egress-proxy.internal:3128"
    )


def test_production_connected_targets_fail_closed_without_proxy(monkeypatch):
    monkeypatch.delenv("COGNIS_EGRESS_PROXY_URL", raising=False)
    with pytest.raises(EgressProxyConfigurationError, match="disabled in production"):
        connected_target_proxy_url(production=True)


def test_development_connected_targets_can_use_direct_connection(monkeypatch):
    monkeypatch.delenv("COGNIS_EGRESS_PROXY_URL", raising=False)
    assert connected_target_proxy_url(production=False) is None


def test_configured_proxy_is_returned(monkeypatch):
    monkeypatch.setenv("COGNIS_EGRESS_PROXY_URL", "http://egress-proxy.internal:3128")
    assert connected_target_proxy_url(production=True) == "http://egress-proxy.internal:3128"
