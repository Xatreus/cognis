from time import perf_counter
from uuid import uuid4
from app.agents.demo_agent import DemoAgent
from app.schemas.evaluations import CaseResult, EvaluationResponse

# Expected values are declared separately from the target agent implementation.
CASES = (
 {'case_id':'cancelled_refund','prompt':'Order cancelled; customer requests refund','expected':'refund_eligible'},
 {'case_id':'delivered_refund','prompt':'Order delivered; customer requests refund','expected':'review_required'},
 {'case_id':'general_question','prompt':'Where can I find my invoice?','expected':'human_review'},
 {'case_id':'empty_input','prompt':'','expected':'error'},
)

def run_demo_evaluation(include_traces: bool = True) -> EvaluationResponse:
    agent = DemoAgent()
    results = []
    for case in CASES:
        started = perf_counter()
        error = None
        try:
            actual = agent.run(case['prompt']).decision
        except ValueError as exc:
            actual, error = 'error', str(exc)
        results.append(CaseResult(case_id=case['case_id'], passed=actual == case['expected'], expected=case['expected'], actual=actual, duration_ms=round((perf_counter()-started)*1000, 3), error=error if include_traces else None))
    passed = sum(item.passed for item in results)
    total = len(results)
    return EvaluationResponse(evaluation_id=str(uuid4()), suite='demo', status='passed' if passed == total else 'failed', total=total, passed=passed, failed=total-passed, pass_rate=passed/total, results=results)
