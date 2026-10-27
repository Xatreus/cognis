"""Worker entry point for registered adapters inside an isolated container."""
import argparse
import asyncio
import inspect
import json
import sys
from pathlib import Path
from app.engine.worker_protocol import WorkerRequest, WorkerResponse


def build_agent(agent_id: str):
    # Never import a module/class supplied by a request.
    if agent_id == "demo":
        from app.agents.demo_agent import DemoAgent
        return DemoAgent()
    if agent_id == "openrouter":
        from app.agents.openrouter import OpenRouterAgent
        return OpenRouterAgent()
    raise ValueError("Unknown agent_id; only registered adapters can execute")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-file", help="Read the JSON request from a transient file")
    args = parser.parse_args()
    try:
        raw = Path(args.request_file).read_text(encoding="utf-8") if args.request_file else sys.stdin.readline()
        request = WorkerRequest.model_validate_json(raw)
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
