"""Evaluation orchestration for the deterministic demo target."""
from uuid import uuid4

from app.agents.demo_agent import DemoAgent
from app.engine.assertions import evaluate_assertions
from app.engine.runner import AgentExecutionError, normalize_output, run_agent
from app.engine.scenarios import EvaluationCase, EvaluationScenario
from app.observability.telemetry import summarize_run
from app.schemas.evaluations import (
    AssertionResultSchema,
    CaseResult,
    EvaluationMetrics,
    EvaluationResponse,
)

DEMO_SCENARIO = EvaluationScenario(
    name="demo",
    description="Basic deterministic refund-routing and input-validation checks.",
    cases=(
        EvaluationCase(
            case_id="cancelled_refund",
            input="Order cancelled; customer requests refund",
            expected_output="refund_eligible",
            tags=("correctness", "refund"),
        ),
        EvaluationCase(
            case_id="delivered_refund",
            input="Order delivered; customer requests refund",
            expected_output="review_required",
            tags=("correctness", "refund"),
        ),
        EvaluationCase(
            case_id="general_question",
            input="Where can I find my invoice?",
            expected_output="human_review",
            tags=("correctness", "general"),
        ),
        EvaluationCase(
            case_id="empty_input",
            input="",
            expected_output="error",
            tags=("robustness", "input-validation"),
        ),
    ),
)


def run_evaluation(agent, scenario: EvaluationScenario, include_traces: bool = True) -> EvaluationResponse:
    """Evaluate a callable or run/invoke-style agent against a scenario.

    Agent code runs in-process and must be trusted. The runner timeout does not
    sandbox untrusted code; see app.engine.isolation for the intended boundary.
    """
    case_results: list[CaseResult] = []
    for case in scenario.cases:
        error = None
        raw_output = None
        duration_ms = 0.0
        try:
            raw_output, duration_ms = _run_case(agent, case.input)
            actual = normalize_output(raw_output)
        except (AgentExecutionError, ValueError) as exc:
            actual = "error"
            error = str(exc)

        checks = evaluate_assertions(
            actual,
            expected=case.expected_output,
            contains=case.contains,
            not_contains=case.not_contains,
            latency_ms=duration_ms,
        )
        passed = bool(checks) and all(check.passed for check in checks)
        case_results.append(
            CaseResult(
                case_id=case.case_id,
                passed=passed,
                expected=normalize_output(case.expected_output),
                actual=actual,
                duration_ms=round(duration_ms, 3),
                error=error if include_traces else None,
                assertions=[
                    AssertionResultSchema(
                        name=check.name,
                        passed=check.passed,
                        message=check.message if include_traces else ("passed" if check.passed else "failed"),
                    )
                    for check in checks
                ],
                tags=list(case.tags),
            )
        )

    passed_count = sum(result.passed for result in case_results)
    total = len(case_results)
    metric_values = summarize_run(
        (result.duration_ms for result in case_results), passed_count, total
    )
    metrics = EvaluationMetrics(**metric_values)
    return EvaluationResponse(
        evaluation_id=str(uuid4()),
        suite=scenario.name,
        status="passed" if passed_count == total else "failed",
        total=total,
        passed=passed_count,
        failed=total - passed_count,
        pass_rate=passed_count / total if total else 0.0,
        results=case_results,
        metrics=metrics,
    )


def _run_case(agent, input_data):
    """Keep demo's deliberate ValueError as a testable target error outcome."""
    try:
        import asyncio
        return asyncio.run(run_agent(agent, input_data))
    except ValueError:
        raise
    except RuntimeError as exc:
        # asyncio.run cannot run inside an already-running loop. The HTTP endpoint
        # is synchronous today; async callers should call run_agent directly.
        if "asyncio.run() cannot be called" in str(exc):
            raise AgentExecutionError("Use run_agent from an async context.") from exc
        raise


def run_demo_evaluation(include_traces: bool = True) -> EvaluationResponse:
    """Backward-compatible entry point used by the existing API."""
    return run_evaluation(DemoAgent(), DEMO_SCENARIO, include_traces=include_traces)
