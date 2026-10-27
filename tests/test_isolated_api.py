from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_isolated_evaluation_runs_registered_demo_worker():
    response = client.post("/evaluations/isolated", json={
        "agent_id": "demo",
        "suite": "isolated-demo",
        "timeout_seconds": 10,
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


def test_isolated_evaluation_rejects_unregistered_agent():
    response = client.post("/evaluations/isolated", json={
        "agent_id": "arbitrary-python",
        "suite": "bad-agent",
        "cases": [{"case_id": "one", "input": "hello"}],
    })
    assert response.status_code == 422
