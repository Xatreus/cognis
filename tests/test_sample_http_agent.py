import asyncio

import httpx
from fastapi.testclient import TestClient

from app.engine.evaluator import DEMO_SCENARIO, run_evaluation_async
from app.engine.scenarios import EvaluationScenario
from app.engine.security_suite import security_scenario
from app.targets.http_agent import HTTPAgentTarget
from examples.sample_http_agent import app, respond


def test_sample_http_agent_maps_demo_inputs_to_expected_outputs():
    assert respond("Order cancelled; customer requests refund") == "refund_eligible"
    assert respond("Order delivered; customer requests refund") == "review_required"
    assert respond("Where can I find my invoice?") == "human_review"
    assert respond("") == "error"


def test_sample_http_agent_health_and_json_contract():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.post("/run", json={"input": "Where is my invoice?"})
    assert response.status_code == 200
    assert response.json() == {"output": "human_review"}


def test_connected_http_adapter_passes_demo_and_security_baseline():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            target = HTTPAgentTarget(
                endpoint_url="http://localhost/run",
                allow_private=True,
                client=client,
                timeout_seconds=2,
            )
            scenario = EvaluationScenario(
                name="sample_http_agent_acceptance",
                description="Acceptance check for the recruiter sample HTTP target.",
                cases=DEMO_SCENARIO.cases + security_scenario().cases,
            )
            result = await run_evaluation_async(target, scenario, timeout_seconds=3)

        assert result.total == 7
        assert result.passed == 7
        assert result.failed == 0
        assert result.pass_rate == 1.0

    asyncio.run(run())
