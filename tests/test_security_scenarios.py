from app.agents.protocol import AgentExecution
from app.engine.security_scenarios import build_secret_leak_scenario


def test_agent_execution_adapter_contract_is_runtime_checkable():
    class ExampleAdapter:
        def invoke(self, input_data):
            return AgentExecution(output=f"received: {input_data}")

    adapter = ExampleAdapter()
    assert isinstance(adapter, __import__("app.agents.protocol", fromlist=["AgentAdapter"]).AgentAdapter)
    assert adapter.invoke("hello").output == "received: hello"


def test_secret_leak_scenario_uses_caller_supplied_canaries():
    scenario = build_secret_leak_scenario(("COGNIS_TEST_CANARY_A", "COGNIS_TEST_CANARY_B"))
    assert scenario.name == "security_secret_non_disclosure"
    assert len(scenario.cases) == 2
    assert all("security" in case.tags for case in scenario.cases)
    assert scenario.cases[0].not_contains == ("COGNIS_TEST_CANARY_A",)


def test_secret_leak_scenario_rejects_empty_canary_set():
    import pytest

    with pytest.raises(ValueError, match="at least one"):
        build_secret_leak_scenario(("", ""))
