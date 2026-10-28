import pytest

from app.engine.container_worker import (
    ContainerPolicy,
    ContainerWorkerError,
    _provider_environment,
    _request_payload,
    run_container_agent,
)


def test_container_policy_rejects_unbounded_limits():
    with pytest.raises(ValueError):
        ContainerPolicy(timeout_seconds=0)
    with pytest.raises(ValueError):
        ContainerPolicy(memory_limit_mb=32)
    with pytest.raises(ValueError):
        ContainerPolicy(cpu_limit=0)
    with pytest.raises(ValueError):
        ContainerPolicy(pids_limit=2)


def test_request_payload_is_valid_worker_protocol_json():
    import json

    payload = _request_payload("demo", "hello", 1024)
    parsed = json.loads(payload)
    assert parsed["protocol_version"] == 1
    assert parsed["agent_id"] == "demo"
    assert parsed["input"] == "hello"


def test_request_payload_rejects_oversized_input():
    with pytest.raises(ContainerWorkerError, match="size limit"):
        _request_payload("demo", "x" * 2048, 1024)


def test_container_worker_rejects_unregistered_agent_before_docker():
    with pytest.raises(ContainerWorkerError, match="Unknown agent_id"):
        run_container_agent("user-supplied-module", "hello")


def test_container_policy_defaults_to_network_disabled():
    assert ContainerPolicy().network_enabled is False


def test_provider_environment_is_allowlisted(monkeypatch):
    # Keep this test independent of provider settings in the developer's shell.
    for name in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "OPENROUTER_BASE_URL"):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-secret")
    monkeypatch.setenv("OTHER_SECRET", "should-not-pass")
    assert _provider_environment("demo") == {}
    assert _provider_environment("openrouter") == {
        "OPENROUTER_API_KEY": "test-secret"
    }


def test_production_mode_fails_closed_without_strong_api_key(monkeypatch):
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    env["COGNIS_ENV"] = "production"
    env.pop("COGNIS_API_KEY", None)
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert "Production requires COGNIS_API_KEY" in result.stderr


def test_production_mode_accepts_configured_api_key():
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    env["COGNIS_ENV"] = "production"
    env["COGNIS_API_KEY"] = "x" * 32
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
