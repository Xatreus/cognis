"""Small deterministic agent used by the Cognis recruiter demo.

This is deliberately not an LLM. It gives the demo stable expected outputs so
reviewers can verify Cognis scoring and report generation without API keys.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentResult:
    decision: str


class SampleSupportAgent:
    def run(self, prompt: str) -> AgentResult:
        text = prompt.strip().lower()
        if not text:
            return AgentResult("error")
        if "refund" in text and "delivered" in text:
            return AgentResult("review_required")
        if "refund" in text and ("cancelled" in text or "canceled" in text):
            return AgentResult("refund_eligible")
        return AgentResult("human_review")
