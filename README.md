# Cognis

Cognis is an extensible agent evaluation and reliability-testing platform. The current milestone establishes a reusable Python evaluation core and keeps the FastAPI demo endpoint backwards compatible.

## Current capabilities

- FastAPI health endpoints and a typed demo evaluation API.
- Provider-neutral test cases and named evaluation scenarios.
- A runner that accepts callable agents and common `run`, `invoke`, `arun`, or `ainvoke` interfaces, normalizes common response shapes, and measures latency.
- Deterministic assertions for expected output, required/forbidden text, latency budgets, and obvious credential-like output patterns.
- Per-case pass/fail, assertion details, tags, and aggregate pass-rate/latency metrics (mean, p50, p95, max).
- Opt-in fault-injection helpers for trusted test agents.
- GitHub Actions CI and Docker deployment foundation.

## Run locally

Use Python 3.12.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

## Tests

```powershell
python -m pytest -q
```

## Demo API

Submit `POST /evaluations` with:

```json
{"suite":"demo","include_traces":true}
```

Health endpoints are `/health/live` and `/health/ready`.

## Architecture

```text
Evaluation API / SDK
        |
        v
Scenario + cases ---> Agent adapter/runner ---> Target agent
        |                     |                    |
        v                     v                    v
Assertions              Timing/errors         Agent output
        \                     |                    /
         \                    v                   /
          +---------- Results + metrics ----------+
```

The core runner is reusable from Python, but the HTTP endpoint currently exposes only the deterministic `demo` suite. Real model-provider integrations and a general-purpose public agent-submission API are not implemented yet.

## Security and isolation limitations

The current secret-pattern check is a heuristic for obvious credential-like output, **not** a complete secret detector or security certification. Real agent security evaluation needs threat-model-specific scenarios, adversarial test corpora, tool-call and side-effect inspection, policy checks, and (where applicable) human or model-assisted judging.

The runner executes target code in-process. Its timeout limits how long Cognis waits but does not safely terminate arbitrary Python code or sandbox a hostile agent. Do not run untrusted agents in this process. A future isolated worker should use process/container boundaries, resource limits, restricted network and filesystem access, and controlled credentials.

## Production readiness

This is an engineering foundation, **not yet a production-ready multi-tenant SaaS**. Persistent run storage, authentication/authorization, tenant isolation, quotas/rate limiting, durable workers, cancellation, model-provider adapters, robust secret redaction, and a frontend are not yet implemented. Do not expose it as a public multi-user service until these controls, security tests, and load tests are implemented and reviewed.

## Roadmap

1. Expand correctness, robustness, and security scenario packs.
2. Add provider/agent adapters (starting with OpenRouter) without coupling the core runner to a vendor.
3. Add adversarial prompt and tool-use evaluation with trace capture and policy assertions.
4. Add persistent evaluation history, authenticated projects, quotas, and isolated workers.
5. Add richer metrics, tracing, regression comparisons, and load/performance tests.
