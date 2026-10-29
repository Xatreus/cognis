import asyncio

from app.agents.protocol import AgentExecution
from app.engine.evaluator import run_evaluation_async
from app.engine.scenarios import EvaluationCase, EvaluationScenario
from app.observability.trace_sanitizer import sanitize_tool_calls, sanitize_trace


def test_trace_sanitizer_redacts_sensitive_keys_and_common_token_patterns():
    trace = {
        "authorization": "Bearer very-secret-token-123456",
        "api_key": "provider-secret",
        "event": "tool_call",
        "detail": "received Bearer very-secret-token-123456 from upstream",
        "nested": {"client_secret": "do-not-keep"},
    }

    cleaned = sanitize_trace(trace)

    assert cleaned["authorization"] == "[REDACTED]"
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["client_secret"] == "[REDACTED]"
    assert "very-secret-token-123456" not in cleaned["detail"]
    assert cleaned["event"] == "tool_call"


def test_trace_sanitizer_bounds_depth_items_and_strings():
    deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": "value"}}}}}}}
    cleaned = sanitize_trace(deep)
    assert "[MAX_DEPTH]" in str(cleaned)

    oversized = {f"field-{index}": index for index in range(150)}
    assert sanitize_trace(oversized)["_truncated"] is True
    assert len(sanitize_trace("x" * 5000)) == 2000


def test_trace_sanitizer_enforces_global_node_and_character_budgets():
    wide_nested = {f"branch-{i}": [{"leaf": "x" * 1000} for _ in range(100)] for i in range(100)}
    cleaned = sanitize_trace(wide_nested)
    rendered = str(cleaned)
    assert "[TRUNCATED]" in rendered or "'_truncated': True" in rendered
    assert len(rendered) < 300_000


def test_tool_call_sanitizer_only_returns_dict_records():
    calls = [{"name": "search", "arguments": {"api_key": "secret"}}, "unsupported"]
    assert sanitize_tool_calls(calls) == [
        {"name": "search", "arguments": {"api_key": "[REDACTED]"}}
    ]


def test_evaluator_captures_sanitized_adapter_trace_when_enabled():
    scenario = EvaluationScenario(
        name="trace-contract",
        cases=(EvaluationCase(case_id="one", input="hello", expected_output="ok"),),
    )

    class TracedAgent:
        async def ainvoke(self, input_data):
            return AgentExecution(
                output="ok",
                tool_calls=({"name": "lookup", "arguments": {"authorization": "Bearer secret-token-123456"}},),
                trace={"step": "lookup", "api_key": "should-not-persist"},
            )

    result = asyncio.run(run_evaluation_async(TracedAgent(), scenario, include_traces=True))
    case = result.results[0]
    assert case.passed is True
    assert case.tool_calls == [
        {"name": "lookup", "arguments": {"authorization": "[REDACTED]"}}
    ]
    assert case.trace == {"step": "lookup", "api_key": "[REDACTED]"}


def test_evaluator_omits_trace_metadata_when_disabled():
    scenario = EvaluationScenario(
        name="trace-disabled",
        cases=(EvaluationCase(case_id="one", input="hello", expected_output="ok"),),
    )

    class TracedAgent:
        async def ainvoke(self, input_data):
            return AgentExecution(
                output="ok",
                tool_calls=({"name": "lookup", "arguments": {"token": "secret"}},),
                trace={"detail": "private trace"},
            )

    result = asyncio.run(run_evaluation_async(TracedAgent(), scenario, include_traces=False))
    assert result.results[0].tool_calls == []
    assert result.results[0].trace == {}
