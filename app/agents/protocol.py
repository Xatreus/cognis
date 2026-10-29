"""Stable adapter contracts for connecting heterogeneous agents to Cognis.

Framework-specific integrations should implement this boundary instead of
coupling the evaluator to a vendor SDK. Keep tool calls/traces in metadata when
the underlying framework exposes them; never put credentials in trace payloads.
"""
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class AgentExecution:
    """Normalized execution result supplied by a framework-specific adapter."""

    output: Any
    tool_calls: tuple[dict[str, Any], ...] = ()
    trace: dict[str, Any] = field(default_factory=dict)
    tool_call_evidence_available: bool | None = None


@runtime_checkable
class AgentAdapter(Protocol):
    """Minimal adapter contract for one invocation of an agent."""

    def invoke(self, input_data: Any) -> AgentExecution | Any:
        """Execute one input and return output or an AgentExecution."""
        ...


@runtime_checkable
class AsyncAgentAdapter(Protocol):
    """Optional async adapter contract for frameworks with native async APIs."""

    async def ainvoke(self, input_data: Any) -> AgentExecution | Any:
        """Execute one input asynchronously."""
        ...
