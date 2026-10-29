"""Readiness must reflect the state of the persistence dependency."""
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


def test_readiness_returns_ready_when_storage_check_succeeds(monkeypatch):
    monkeypatch.setattr(main_module, "check_store", lambda: None)
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_returns_service_unavailable_when_storage_is_down(monkeypatch):
    def fail_check():
        raise RuntimeError("test-only database failure")

    monkeypatch.setattr(main_module, "check_store", fail_check)
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "Persistence backend is not ready"
