from app.engine.evaluator import run_evaluation
from app.engine.scenarios import EvaluationCase, EvaluationScenario


class ExplodingAgent:
    async def ainvoke(self, _input):
        raise RuntimeError("upstream down")


def test_execution_error_is_never_counted_as_pass_even_if_error_is_expected():
    scenario = EvaluationScenario(
        name="error-regression",
        description="Execution errors must fail closed.",
        cases=(EvaluationCase(
            case_id="upstream-error",
            input="hello",
            expected_output="error",
            tags=("regression",),
        ),),
    )
    result = run_evaluation(ExplodingAgent(), scenario)
    assert result.status == "failed"
    assert result.passed == 0
    assert result.failed == 1
    assert result.pass_rate == 0
    assert result.results[0].actual == "error"
    assert result.results[0].error == "Agent execution failed: RuntimeError"
    assert result.results[0].assertions == []
