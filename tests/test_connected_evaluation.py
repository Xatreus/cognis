import asyncio

from fastapi.testclient import TestClient

from app.main import app


def test_connected_endpoint_runs_user_supplied_target_and_persists_no_credentials(monkeypatch, tmp_path):
    import app.targets.openai_compatible as provider

    calls = []
    class FakeTarget:
        def __init__(self, **kwargs):
            calls.append({"model": kwargs["model"], "api_key": kwargs["api_key"]})
        async def ainvoke(self, input_data):
            return "SAFE" if "REFUSED" not in str(input_data) else "REFUSED"

    monkeypatch.setattr(provider, "OpenAICompatibleTarget", FakeTarget)
    monkeypatch.setenv("COGNIS_DATABASE_PATH", str(tmp_path / "cognis-test.db"))
    with TestClient(app) as client:
        response = client.post("/evaluations/connected", json={
            "target_type": "model",
            "provider": "gemini",
            "api_key": "temporary-test-secret",
            "model": "test-model",
            "suite": "security",
            "timeout_seconds": 5,
        })
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["suite"] == "connected_security"
        assert result["total"] == 3
        assert calls == [{"model": "test-model", "api_key": "temporary-test-secret"}]
        history = client.get("/evaluations/history?limit=10&offset=0").json()
        detail = client.get("/evaluations/history/" + result["evaluation_id"]).json()
        assert history["total"] == 1
        assert "temporary-test-secret" not in str(history)
        assert "temporary-test-secret" not in str(detail)


def test_connected_endpoint_rejects_missing_model_credentials():
    with TestClient(app) as client:
        response = client.post("/evaluations/connected", json={
            "target_type": "model", "provider": "openai", "suite": "security"
        })
        assert response.status_code == 422


def test_connected_endpoint_blocks_private_agent_urls_by_default(monkeypatch):
    monkeypatch.setenv("COGNIS_ALLOW_PRIVATE_AGENT_URLS", "false")
    with TestClient(app) as client:
        response = client.post("/evaluations/connected", json={
            "target_type": "http_agent",
            "endpoint_url": "https://127.0.0.1:9000/run",
            "suite": "security"
        })
        assert response.status_code == 422
