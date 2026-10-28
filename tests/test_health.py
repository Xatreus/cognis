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
