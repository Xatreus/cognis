from dataclasses import dataclass


@dataclass(frozen=True)
class AgentOutput:
    decision: str


class DemoAgent:
    """Deterministic example agent used to exercise Cognis evaluation flow."""

    def run(self, prompt: str) -> AgentOutput:
        normalized = prompt.strip().lower()
        if not normalized:
            raise ValueError("prompt must not be empty")
        if "refund" in normalized and "delivered" in normalized:
            return AgentOutput("review_required")
        if "refund" in normalized and ("cancelled" in normalized or "canceled" in normalized):
            return AgentOutput("refund_eligible")
        return AgentOutput("human_review")
