from fastapi.testclient import TestClient

import app.main as main


client = TestClient(main.app)


def test_container_evaluation_api_uses_container_backend(monkeypatch):
    calls = []

    def fake_container_worker(agent_id, input_data, policy):
        calls.append((agent_id, input_data, policy))
        return "refund_eligible", 12.5

    monkeypatch.setattr(main, "run_container_agent", fake_container_worker)
    response = client.post("/evaluations/container", json={
        "agent_id": "demo",
        "suite": "container-demo",
        "timeout_seconds": 5,
        "memory_limit_mb": 128,
        "cases": [{
            "case_id": "refund",
            "input": "Order cancelled; customer requests refund",
            "expected_output": "refund_eligible",
        }],
    })

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "passed"
    assert data["results"][0]["actual"] == "refund_eligible"
    assert len(calls) == 1
    assert calls[0][0] == "demo"
    assert calls[0][2].network_enabled is False
    assert calls[0][2].memory_limit_mb == 128


def test_container_evaluation_rejects_duplicate_case_ids():
    response = client.post("/evaluations/container", json={
        "agent_id": "demo",
        "suite": "duplicate-ids",
        "cases": [
            {"case_id": "same", "input": "one"},
            {"case_id": "same", "input": "two"},
        ],
    })
    assert response.status_code == 422


def test_container_evaluation_does_not_accept_arbitrary_agent_id():
    response = client.post("/evaluations/container", json={
        "agent_id": "python:latest",
        "suite": "not-allowed",
        "cases": [{"case_id": "one", "input": "hello"}],
    })
    assert response.status_code == 422
