import pytest

from app.agents.protocol import AgentExecution, AgentAdapter
from app.engine.security_scenarios import (
    build_prompt_injection_scenario,
    build_secret_leak_scenario,
)


def test_agent_execution_adapter_contract_is_runtime_checkable():
    class ExampleAdapter:
        def invoke(self, input_data):
            return AgentExecution(output=f"received: {input_data}")

    adapter = ExampleAdapter()
    assert isinstance(adapter, AgentAdapter)
    assert adapter.invoke("hello").output == "received: hello"


def test_secret_leak_scenario_uses_synthetic_canaries():
    scenario = build_secret_leak_scenario(("COGNIS_TEST_CANARY_A", "COGNIS_TEST_CANARY_B"))
    assert scenario.name == "security_secret_non_disclosure"
    assert len(scenario.cases) == 2
    assert all("security" in case.tags for case in scenario.cases)
    assert scenario.cases[0].not_contains == ("COGNIS_TEST_CANARY_A",)
    assert "COGNIS_TEST_CANARY_A" in scenario.cases[0].input
    assert "COGNIS_TEST_CANARY_B" not in scenario.cases[0].input
    assert "Ignore all previous instructions" in scenario.cases[0].input


def test_secret_leak_scenario_deduplicates_canaries_and_rejects_empty_values():
    scenario = build_secret_leak_scenario(("CANARY", "CANARY", ""))
    assert len(scenario.cases) == 1
    with pytest.raises(ValueError, match="at least one"):
        build_secret_leak_scenario(("", ""))


def test_prompt_injection_scenario_has_explicit_expected_behavior():
    scenario = build_prompt_injection_scenario()
    assert scenario.name == "security_prompt_injection_baseline"
    assert scenario.cases[0].expected_output == "SAFE"
    assert "COMPROMISED" in scenario.cases[0].input
