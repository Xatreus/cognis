from datetime import datetime, timezone

from app.engine.evaluator import run_evaluation
from examples.sample_agent import SampleSupportAgent
from scripts.run_demo import build_scenario, render_markdown


def test_recruiter_demo_passes_correctness_and_security_cases():
    result = run_evaluation(SampleSupportAgent(), build_scenario())

    assert result.status == "passed"
    assert result.total == 6
    assert result.passed == 6
    assert result.failed == 0
    assert result.pass_rate == 1.0
    assert result.metrics is not None
    assert result.metrics.latency_mean_ms is not None
    assert result.metrics.latency_p50_ms is not None
    assert result.metrics.latency_p95_ms is not None
    assert result.metrics.latency_max_ms is not None

    security_cases = [case for case in result.results if "security" in case.tags]
    assert len(security_cases) == 2
    assert all(case.passed for case in security_cases)


def test_demo_report_includes_metrics_failures_and_security_results():
    result = run_evaluation(SampleSupportAgent(), build_scenario())
    report = render_markdown(result, datetime.now(timezone.utc).isoformat())

    assert "Pass rate:** 6/6 (100.0%)" in report
    assert "Failures:** 0" in report
    assert "Security-tagged checks:** 2/2 passed" in report
    assert "Latency" in report
    assert "Case results" in report
    assert "prompt_injection_canary" in report
