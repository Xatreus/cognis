"""Generic scenario evaluator for trusted agent adapters."""
import asyncio
from uuid import uuid4

from app.agents.demo_agent import DemoAgent
from app.engine.assertions import evaluate_assertions
from app.engine.runner import AgentExecutionError, normalize_output, run_agent
from app.engine.scenarios import EvaluationCase, EvaluationScenario
from app.observability.trace_sanitizer import sanitize_tool_calls, sanitize_trace
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
        raw = None
        trace: dict = {}
        tool_calls: list[dict] = []
        try:
            raw, duration_ms = await run_agent(agent, case.input, timeout_seconds=timeout_seconds)
            actual = normalize_output(raw)
            if include_traces:
                trace_value = getattr(raw, "trace", {})
                tool_call_value = getattr(raw, "tool_calls", ())
                sanitized_trace = sanitize_trace(trace_value)
                trace = sanitized_trace if isinstance(sanitized_trace, dict) else {}
                tool_calls = sanitize_tool_calls(tool_call_value)
        except AgentExecutionError as exc:
            actual = "error"
            duration_ms = timeout_seconds * 1000 if "timeout" in str(exc).lower() else 0.0
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
        case_metadata = sanitize_trace(case.metadata)
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
            metadata=case_metadata if isinstance(case_metadata, dict) else {},
            tool_calls=tool_calls,
            trace=trace,
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
    """Synchronous wrapper for scripts and test suites."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_evaluation_async(agent, scenario, include_traces=include_traces))
    raise RuntimeError("run_evaluation() cannot be called from a running event loop; use run_evaluation_async()")


def run_demo_evaluation(include_traces: bool = True) -> EvaluationResponse:
    """Run the built-in deterministic scenario against the bundled demo agent."""
    return run_evaluation(DemoAgent(), DEMO_SCENARIO, include_traces=include_traces)
