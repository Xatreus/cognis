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
