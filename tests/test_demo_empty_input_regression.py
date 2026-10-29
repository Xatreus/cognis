from app.agents.demo_agent import DemoAgent
from app.engine.evaluator import DEMO_SCENARIO, run_evaluation


def test_demo_agent_empty_input_is_a_normal_validation_output():
    output = DemoAgent().run("")
    assert output.decision == "error"


def test_demo_empty_input_is_not_an_execution_error():
    result = run_evaluation(DemoAgent(), DEMO_SCENARIO)
    case = next(item for item in result.results if item.case_id == "empty_input")
    assert case.actual == "error"
    assert case.error is None
    assert case.passed is True
    assert case.assertions
