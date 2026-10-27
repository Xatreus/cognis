"""Worker subprocess entry point. Only explicitly registered adapters can run here."""
import asyncio
import inspect
import sys
from app.engine.worker_protocol import WorkerRequest, WorkerResponse

def build_agent(agent_id: str):
    # Explicit registry: never import a Python module/class named by a request.
    if agent_id == "demo":
        from app.agents.demo_agent import DemoAgent
        return DemoAgent()
    if agent_id == "openrouter":
        from app.agents.openrouter import OpenRouterAgent
        return OpenRouterAgent()
    raise ValueError("Unknown agent_id; only registered adapters can execute")

def main() -> int:
    try:
        request = WorkerRequest.model_validate_json(sys.stdin.read())
        if request.protocol_version != 1:
            raise ValueError("Unsupported worker protocol version")
        agent = build_agent(request.agent_id)
        from app.engine.runner import _select_callable, normalize_output
        result = _select_callable(agent)(request.input)
        if inspect.isawaitable(result):
            result = asyncio.run(result)
        response = WorkerResponse(ok=True, output=normalize_output(result))
    except Exception as exc:
        response = WorkerResponse(ok=False, error_code=type(exc).__name__,
                                  error_message=str(exc)[:500])
    sys.stdout.write(response.model_dump_json())
    sys.stdout.flush()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
