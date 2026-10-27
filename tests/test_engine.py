import asyncio
import time

import pytest

from app.engine.assertions import evaluate_assertions
from app.engine.fault_injection import FaultInjectingAgent, FaultPlan
from app.engine.runner import AgentExecutionError, normalize_output, run_agent
from app.engine.scenarios import EvaluationCase, EvaluationScenario
from app.engine.evaluator import run_evaluation
from app.observability.telemetry import summarize_run


def test_scenario_rejects_duplicate_case_ids():
    case = EvaluationCase(case_id="same", input="x")
    with pytest.raises(ValueError, match="unique"):
        EvaluationScenario(name="duplicate", cases=(case, case))


def test_normalize_common_agent_outputs():
    assert normalize_output({"output": "hello"}) == "hello"
    assert normalize_output({"decision": "approve"}) == "approve"
    assert normalize_output(None) == ""


def test_runner_supports_sync_callable():
    output, duration = asyncio.run(run_agent(lambda value: {"output": value.upper()}, "hello"))
    assert output == {"output": "HELLO"}
    assert duration >= 0


def test_runner_supports_async_agent():
    async def agent(value):
        return {"answer": value + "!"}

    output, duration = asyncio.run(run_agent(agent, "hello"))
    assert output == {"answer": "hello!"}
    assert duration >= 0


def test_runner_times_out_slow_agent():
    def slow(_):
        time.sleep(0.1)
        return "late"

    with pytest.raises(AgentExecutionError, match="timeout"):
        asyncio.run(run_agent(slow, "x", timeout_seconds=0.01))


def test_assertions_check_expected_output_and_secret_patterns():
    results = evaluate_assertions("approved", expected="approved", not_contains=("password",))
    assert all(item.passed for item in results)
    leak = evaluate_assertions("api_key=AKIA1234567890ABCDEF")
    secret_check = next(item for item in leak if item.name == "obvious_secret_leak")
    assert not secret_check.passed


def test_fault_injector_exercises_failure_path():
    wrapped = FaultInjectingAgent(lambda _: "ok", FaultPlan(kind="raise"))
    with pytest.raises(RuntimeError, match="Injected"):
        wrapped.run("input")


def test_metrics_include_latency_percentiles():
    metrics = summarize_run([1, 2, 3, 4], passed=3, total=4)
    assert metrics["pass_rate"] == 0.75
    assert metrics["latency_mean_ms"] == 2.5
    assert metrics["latency_p95_ms"] == 4


def test_generic_evaluator_accepts_callable_agent():
    scenario = EvaluationScenario(
        name="simple",
        cases=(
            EvaluationCase(case_id="hello", input="hello", expected_output="hello world"),
        ),
    )
    result = run_evaluation(lambda value: value + " world", scenario)
    assert result.status == "passed"
    assert result.results[0].passed
    assert result.metrics is not None
    assert result.metrics.pass_rate == 1.0
