"""Generic scenario evaluator for trusted agent adapters."""
import asyncio
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
        EvaluationCase(case_id="cancelled_refund", input="Order cancelled; customer requests refund",
                       expected_output="refund_eligible", tags=("correctness", "refund")),
        EvaluationCase(case_id="delivered_refund", input="Order delivered; customer requests refund",
                       expected_output="review_required", tags=("correctness", "refund")),
        EvaluationCase(case_id="general_question", input="Where can I find my invoice?",
                       expected_output="human_review", tags=("correctness", "general")),
        EvaluationCase(case_id="empty_input", input="", expected_output="error",
                       tags=("robustness", "input-validation")),
    ),
)


async def run_evaluation_async(
    agent,
    scenario: EvaluationScenario,
    include_traces: bool = True,
    timeout_seconds: float = 30.0,
) -> EvaluationResponse:
    """Evaluate one trusted agent over a named scenario.

    Agent code executes in this process. The timeout bounds how long Cognis waits;
    it is not a sandbox and cannot safely terminate arbitrary target code.
    """
    results: list[CaseResult] = []
    for case in scenario.cases:
        error = None
        try:
            raw, duration_ms = await run_agent(agent, case.input, timeout_seconds=timeout_seconds)
            actual = normalize_output(raw)
        except (AgentExecutionError, ValueError) as exc:
            actual = "error"
            duration_ms = timeout_seconds * 1000 if isinstance(exc, AgentExecutionError) and "timeout" in str(exc).lower() else 0.0
            error = str(exc)

        # Execution failures must never become PASS just because generic output
        # safety assertions pass (or because a case expects the literal "error").
        if error is not None:
            checks = []
            passed = False
        else:
            checks = evaluate_assertions(
                actual,
                expected=case.expected_output,
                contains=case.contains,
                not_contains=case.not_contains,
                latency_ms=duration_ms,
                max_latency_ms=case.max_latency_ms,
            )
            passed = bool(checks) and all(item.passed for item in checks)
        results.append(CaseResult(
            case_id=case.case_id,
            passed=passed,
            expected=normalize_output(case.expected_output),
            actual=actual,
            duration_ms=round(duration_ms, 3),
            error=error if include_traces else None,
            assertions=[
                AssertionResultSchema(
                    name=item.name,
                    passed=item.passed,
                    message=item.message if include_traces else ("passed" if item.passed else "failed"),
                )
                for item in checks
            ],
            tags=list(case.tags),
        ))

    passed_count = sum(item.passed for item in results)
    total = len(results)
    metrics = EvaluationMetrics(**summarize_run((item.duration_ms for item in results), passed_count, total))
    return EvaluationResponse(
        evaluation_id=str(uuid4()),
        suite=scenario.name,
        status="passed" if passed_count == total else "failed",
        total=total,
        passed=passed_count,
        failed=total-passed_count,
        pass_rate=passed_count / total if total else 0.0,
        results=results,
        metrics=metrics,
    )


def run_evaluation(agent, scenario: EvaluationScenario, include_traces: bool = True) -> EvaluationResponse:
    """Synchronous entry point; use run_evaluation_async inside an event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_evaluation_async(agent, scenario, include_traces))
    raise RuntimeError("run_evaluation cannot run inside an event loop; await run_evaluation_async instead")


def run_demo_evaluation(include_traces: bool = True) -> EvaluationResponse:
    """Backward-compatible deterministic demo evaluation."""
    return run_evaluation(DemoAgent(), DEMO_SCENARIO, include_traces=include_traces)
