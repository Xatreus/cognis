"""Agent execution adapter with sync/async support and per-case timing."""
import asyncio
import inspect
import json
from time import perf_counter
from typing import Any


class AgentExecutionError(RuntimeError):
    """Raised when the target agent cannot be invoked or exceeds its timeout."""


def normalize_output(value: Any) -> str:
    """Convert common agent/framework response shapes to a stable text value."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("output", "content", "response", "answer", "result", "decision"):
            if key in value:
                return normalize_output(value[key])
        return json.dumps(value, sort_keys=True, default=str)
    for attr in ("content", "output", "response", "answer", "decision"):
        if hasattr(value, attr):
            return normalize_output(getattr(value, attr))
    if isinstance(value, (list, tuple)):
        return json.dumps(value, default=str)
    return str(value)


def _select_callable(agent: Any):
    # Prefer async-native methods to avoid blocking the event loop.
    for name in ("ainvoke", "arun", "invoke", "run"):
        method = getattr(agent, name, None)
        if callable(method):
            return method
    if callable(agent):
        return agent
    raise AgentExecutionError(
        "Agent must be callable or expose one of: ainvoke, arun, invoke, run."
    )


async def run_agent(agent: Any, input_data: Any, timeout_seconds: float = 30.0) -> tuple[Any, float]:
    """Run an agent with a timeout and return (raw output, elapsed milliseconds).

    Synchronous functions execute in a worker thread. A timeout stops waiting for
    that thread but cannot forcibly terminate arbitrary Python code; untrusted
    agents require process/container isolation, which this runner does not provide.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    target = _select_callable(agent)
    started = perf_counter()

    async def invoke():
        if inspect.iscoroutinefunction(target):
            return await target(input_data)
        result = await asyncio.to_thread(target, input_data)
        if inspect.isawaitable(result):
            return await result
        return result

    try:
        output = await asyncio.wait_for(invoke(), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise AgentExecutionError(f"Agent exceeded {timeout_seconds:.3f}s timeout.") from exc
    except AgentExecutionError:
        raise
    except Exception as exc:
        raise AgentExecutionError(f"Agent execution failed: {type(exc).__name__}") from exc

    return output, (perf_counter() - started) * 1000
