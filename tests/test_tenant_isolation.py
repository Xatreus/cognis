from types import SimpleNamespace

from app.storage.evaluations import get_evaluation, list_evaluations, save_evaluation


def fake_result(evaluation_id: str, suite: str = "tenant-test"):
    return SimpleNamespace(model_dump=lambda mode="json": {
        "evaluation_id": evaluation_id,
        "suite": suite,
        "status": "passed",
        "total": 1,
        "passed": 1,
        "failed": 0,
        "pass_rate": 1.0,
        "results": [],
        "metrics": None,
    })


def test_evaluation_history_is_scoped_to_tenant(tmp_path, monkeypatch):
    monkeypatch.delenv("COGNIS_DATABASE_URL", raising=False)
    monkeypatch.setenv("COGNIS_DATABASE_PATH", str(tmp_path / "tenant-test.db"))

    save_evaluation(fake_result("eval-a"), tenant_id="tenant-a")
    save_evaluation(fake_result("eval-b"), tenant_id="tenant-b")

    history_a = list_evaluations(tenant_id="tenant-a")
    history_b = list_evaluations(tenant_id="tenant-b")

    assert history_a["total"] == 1
    assert [item["evaluation_id"] for item in history_a["items"]] == ["eval-a"]
    assert history_b["total"] == 1
    assert [item["evaluation_id"] for item in history_b["items"]] == ["eval-b"]
    assert get_evaluation("eval-b", tenant_id="tenant-a") is None
    assert get_evaluation("eval-a", tenant_id="tenant-a")["result"]["evaluation_id"] == "eval-a"


def test_unknown_tenant_cannot_list_another_tenants_history(tmp_path, monkeypatch):
    monkeypatch.delenv("COGNIS_DATABASE_URL", raising=False)
    monkeypatch.setenv("COGNIS_DATABASE_PATH", str(tmp_path / "tenant-test.db"))
    save_evaluation(fake_result("private-eval"), tenant_id="customer-private")

    assert list_evaluations(tenant_id="attacker")["total"] == 0
    assert get_evaluation("private-eval", tenant_id="attacker") is None
