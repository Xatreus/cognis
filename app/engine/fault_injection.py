"""Small, opt-in fault injectors for testing agent error handling."""
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class FaultPlan:
    """A deterministic fault to apply to the next matching invocation."""

    kind: str
    message: str = "Injected test fault"

    def __post_init__(self) -> None:
        if self.kind not in {"raise", "empty_output", "malformed_output"}:
            raise ValueError("kind must be raise, empty_output, or malformed_output")


class FaultInjectingAgent:
    """Wrap a trusted agent to exercise failure paths in tests."""

    def __init__(self, agent: Any, plan: FaultPlan):
        self._agent = agent
        self._plan = plan

    def run(self, input_data: Any) -> Any:
        if self._plan.kind == "raise":
            raise RuntimeError(self._plan.message)
        if self._plan.kind == "empty_output":
            return ""
        if self._plan.kind == "malformed_output":
            return {"unexpected": object()}
        target = getattr(self._agent, "run", self._agent)
        return target(input_data)
