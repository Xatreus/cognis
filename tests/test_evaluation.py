from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_demo_evaluation_passes_all_cases():
    response = client.post('/evaluations', json={'suite':'demo'})
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 4 and data['passed'] == 4 and data['failed'] == 0
    assert data['pass_rate'] == 1.0

def test_traces_can_be_hidden():
    data = client.post('/evaluations', json={'suite':'demo','include_traces':False}).json()
    case = next(x for x in data['results'] if x['case_id'] == 'empty_input')
    assert case['actual'] == 'error' and case['error'] is None

def test_unknown_suite_is_rejected():
    assert client.post('/evaluations', json={'suite':'unknown'}).status_code == 422


def test_evaluation_is_persisted_and_retrievable(monkeypatch, tmp_path):
    monkeypatch.setenv("COGNIS_DATABASE_PATH", str(tmp_path / "test-cognis.db"))
    response = client.post("/evaluations", json={"suite": "demo"})
    assert response.status_code == 200
    evaluation_id = response.json()["evaluation_id"]

    history = client.get("/evaluations/history")
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["evaluation_id"] == evaluation_id

    detail = client.get(f"/evaluations/history/{evaluation_id}")
    assert detail.status_code == 200
    assert detail.json()["result"]["evaluation_id"] == evaluation_id
    assert detail.json()["result"]["passed"] == 4


def test_unknown_evaluation_history_returns_404(monkeypatch, tmp_path):
    monkeypatch.setenv("COGNIS_DATABASE_PATH", str(tmp_path / "empty.db"))
    response = client.get("/evaluations/history/not-a-real-id")
    assert response.status_code == 404


def test_history_pagination_validation():
    assert client.get("/evaluations/history?limit=0").status_code == 422
    assert client.get("/evaluations/history?offset=-1").status_code == 422
