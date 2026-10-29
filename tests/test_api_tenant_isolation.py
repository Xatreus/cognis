"""API-level authentication and tenant-isolation regression tests."""
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.storage.evaluations import save_evaluation


def _result(evaluation_id: str):
    return SimpleNamespace(
        model_dump=lambda mode="json": {
            "evaluation_id": evaluation_id,
            "suite": "tenant-regression",
            "status": "passed",
            "total": 1,
            "passed": 1,
            "failed": 0,
            "pass_rate": 1.0,
            "results": [],
            "metrics": None,
        }
    )


def test_production_api_fails_closed_when_authentication_is_unconfigured(monkeypatch):
    monkeypatch.setattr(main_module, "COGNIS_ENV", "production")
    monkeypatch.delenv("COGNIS_API_KEY", raising=False)
    monkeypatch.delenv("COGNIS_API_KEYS_JSON", raising=False)

    with TestClient(app) as client:
        response = client.get("/evaluations/history")

    assert response.status_code == 503
    assert "authentication is not configured" in response.text


def test_production_api_rejects_missing_and_invalid_bearer_tokens(monkeypatch):
    monkeypatch.setattr(main_module, "COGNIS_ENV", "production")
    monkeypatch.delenv("COGNIS_API_KEY", raising=False)
    monkeypatch.setenv("COGNIS_API_KEYS_JSON", json.dumps({"valid-test-token": "tenant-a"}))

    with TestClient(app) as client:
        missing = client.get("/evaluations/history")
        invalid = client.get(
            "/evaluations/history",
            headers={"Authorization": "Bearer definitely-not-valid"},
        )

    assert missing.status_code == 401
    assert invalid.status_code == 401


def test_api_history_isolated_by_authenticated_tenant(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "COGNIS_ENV", "production")
    monkeypatch.delenv("COGNIS_DATABASE_URL", raising=False)
    monkeypatch.delenv("COGNIS_API_KEY", raising=False)
    monkeypatch.setenv("COGNIS_DATABASE_PATH", str(tmp_path / "api-tenant-test.db"))
    monkeypatch.setenv(
        "COGNIS_API_KEYS_JSON",
        json.dumps({
            "test-token-tenant-a": "tenant-a",
            "test-token-tenant-b": "tenant-b",
        }),
    )

    save_evaluation(_result("tenant-a-eval"), tenant_id="tenant-a")
    save_evaluation(_result("tenant-b-eval"), tenant_id="tenant-b")

    with TestClient(app) as client:
        history_a = client.get(
            "/evaluations/history",
            headers={"Authorization": "Bearer test-token-tenant-a"},
        )
        history_b = client.get(
            "/evaluations/history",
            headers={"Authorization": "Bearer test-token-tenant-b"},
        )
        cross_tenant_detail = client.get(
            "/evaluations/history/tenant-b-eval",
            headers={"Authorization": "Bearer test-token-tenant-a"},
        )

    assert history_a.status_code == 200
    assert [item["evaluation_id"] for item in history_a.json()["items"]] == ["tenant-a-eval"]
    assert history_b.status_code == 200
    assert [item["evaluation_id"] for item in history_b.json()["items"]] == ["tenant-b-eval"]
    assert cross_tenant_detail.status_code == 404
