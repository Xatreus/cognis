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
