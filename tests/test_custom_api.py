from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_custom_evaluation_rejects_duplicate_case_ids():
    response = client.post("/evaluations/custom", json={
        "suite": "duplicate",
        "cases": [
            {"case_id": "same", "input": "one", "expected_output": "one"},
            {"case_id": "same", "input": "two", "expected_output": "two"},
        ],
    })
    assert response.status_code == 422


def test_custom_evaluation_rejects_oversized_case_list():
    response = client.post("/evaluations/custom", json={
        "suite": "too_many",
        "cases": [{"case_id": f"case-{i}", "input": "x"} for i in range(51)],
    })
    assert response.status_code == 422


def test_custom_evaluation_uses_openrouter_adapter(monkeypatch):
    class FakeAgent:
        async def ainvoke(self, input_data):
            return "safe answer"

    monkeypatch.setattr("app.main.OpenRouterAgent", lambda: FakeAgent())
    response = client.post("/evaluations/custom", json={
        "suite": "custom_smoke",
        "cases": [
            {
                "case_id": "expected_output",
                "input": "answer",
                "expected_output": "safe answer",
                "not_contains": ["COMPROMISED"],
                "tags": ["correctness"],
            }
        ],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["suite"] == "custom_smoke"
    assert data["status"] == "passed"
    assert data["results"][0]["actual"] == "safe answer"
    assert data["metrics"]["pass_rate"] == 1.0


def test_custom_evaluation_requires_provider_configuration(monkeypatch):
    from app.agents.openrouter import OpenRouterConfigurationError

    def missing_config():
        raise OpenRouterConfigurationError("OPENROUTER_API_KEY is not configured.")

    monkeypatch.setattr("app.main.OpenRouterAgent", missing_config)
    response = client.post("/evaluations/custom", json={
        "suite": "needs_provider",
        "cases": [{"case_id": "one", "input": "hello"}],
    })
    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in response.json()["detail"]
