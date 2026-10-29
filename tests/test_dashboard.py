from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_page_and_assets_are_served():
    client = TestClient(app)
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Cognis" in page.text
    assert '/static/dashboard.css' in page.text
    assert '/static/dashboard.js' in page.text

    css = client.get("/static/dashboard.css")
    js = client.get("/static/dashboard.js")
    assert css.status_code == 200
    assert "--mint" in css.text
    assert js.status_code == 200
    assert "/evaluations/history" in js.text
    assert "/evaluations" in js.text
    assert "quality-forbidden-tools" in page.text
    assert "forbidden_tools" in js.text
    assert "tool_call_evidence_available" in js.text


def test_dashboard_response_has_browser_security_headers():
    response = TestClient(app).get("/dashboard")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "script-src 'self'" in response.headers["content-security-policy"]
