import pytest
from app.engine.isolation import IsolatedWorkerError, IsolationPolicy, run_isolated_agent

def test_worker_runs_registered_demo_adapter():
    output, duration_ms = run_isolated_agent(
        "demo", "Order cancelled; customer requests refund",
        IsolationPolicy(timeout_seconds=10),
    )
    assert output == "refund_eligible"
    assert duration_ms > 0

def test_worker_rejects_unknown_adapter():
    with pytest.raises(IsolatedWorkerError, match="Unknown agent_id"):
        run_isolated_agent("not-registered", "hello", IsolationPolicy(timeout_seconds=10))

def test_isolation_policy_validates_limits():
    with pytest.raises(ValueError):
        IsolationPolicy(timeout_seconds=0)
    with pytest.raises(ValueError):
        IsolationPolicy(memory_limit_mb=32)
