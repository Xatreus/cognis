from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_task():
    response = client.post("/tasks", json={"task": "investigate service"})

    assert response.status_code == 200
    assert response.json() == {
        "message": "Task received",
        "task": "investigate service",
        "status": "pending",
    }


def test_empty_task_check():
    response = client.post("/tasks", json={"task": ""})
    assert response.status_code == 422


def test_security_headers_are_set():
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_protected_endpoint_requires_bearer_token_when_key_configured(monkeypatch):
    monkeypatch.setenv("COGNIS_API_KEY", "test-secret-key-that-is-long-enough")
    denied = client.post("/evaluations", json={"suite": "demo"})
    assert denied.status_code == 401

    allowed = client.post(
        "/evaluations",
        json={"suite": "demo"},
        headers={"Authorization": "Bearer test-secret-key-that-is-long-enough"},
    )
    assert allowed.status_code == 200


def test_health_endpoint_remains_public_when_auth_is_configured(monkeypatch):
    monkeypatch.setenv("COGNIS_API_KEY", "test-secret-key-that-is-long-enough")
    response = client.get("/health/ready")
    assert response.status_code == 200
