import pytest

from app.engine.container_worker import (
    ContainerPolicy,
    ContainerWorkerError,
    _provider_environment,
    _request_archive,
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


def test_request_archive_contains_only_request_file():
    import io
    import tarfile
    payload = b'{"protocol_version":1}'
    with tarfile.open(fileobj=io.BytesIO(_request_archive(payload)), mode="r:") as archive:
        members = archive.getmembers()
        assert [item.name for item in members] == ["cognis-request.json"]
        assert archive.extractfile(members[0]).read() == payload
        assert members[0].mode == 0o400


def test_container_worker_rejects_unregistered_agent_before_docker():
    with pytest.raises(ContainerWorkerError, match="Unknown agent_id"):
        run_container_agent("user-supplied-module", "hello")


def test_container_policy_defaults_to_network_disabled():
    assert ContainerPolicy().network_enabled is False


def test_provider_environment_is_allowlisted(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-secret")
    monkeypatch.setenv("OTHER_SECRET", "should-not-pass")
    assert _provider_environment("demo") == {}
    assert _provider_environment("openrouter") == {
        "OPENROUTER_API_KEY": "test-secret"
    }
