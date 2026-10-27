# Cognis

Cognis is an extensible agent evaluation and reliability-testing platform. This repository contains a reusable Python evaluation core and a deterministic FastAPI demo endpoint.

## Current capabilities

- Typed, provider-neutral evaluation cases and named scenarios.
- A minimal agent adapter contract for sync/async framework integrations.
- A runner supporting callable agents and common `run`, `invoke`, `arun`, and `ainvoke` interfaces.
- Deterministic output assertions, required/forbidden text checks, latency budgets, and a heuristic for obvious credential-like output.
- A configurable secret non-disclosure scenario using caller-provided synthetic canaries.
- Per-case results and aggregate pass-rate/latency metrics (mean, p50, p95, max).
- Opt-in fault-injection helpers for trusted agents.
- FastAPI health endpoints, Docker deployment foundation, and GitHub Actions CI.

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
Scenario + cases ---> Agent adapter/runner ---> Target agent
        |                     |                    |
        v                     v                    v
Assertions              Timing/errors         Agent output
        \                     |                    /
         \                    v                   /
          +---------- Results + metrics ----------+
```

The core runner is reusable from Python. The HTTP endpoint currently exposes only the deterministic `demo` suite; the adapter protocol is a foundation for integrations, not a set of completed vendor/framework adapters. Real model-provider integrations and a general-purpose public agent-submission API are not implemented yet.

## Security and isolation limitations

The secret non-disclosure scenario checks whether an output contains caller-supplied synthetic canaries. The output credential-pattern check is also heuristic. **Neither is a comprehensive security benchmark or certification.** Serious agent security evaluation needs threat-model-specific adversarial cases, tool-call and side-effect inspection, policy checks, robust trace handling, and (where appropriate) human or model-assisted judging.

The runner executes target code in-process. Its timeout limits how long Cognis waits but does not safely terminate arbitrary Python code or sandbox a hostile agent. Do not run untrusted agents in this process. A future isolated worker should use process/container boundaries, resource limits, restricted network and filesystem access, and controlled credentials.

## Production readiness

This is an engineering foundation, **not yet a production-ready multi-tenant SaaS**. Persistent run storage, authentication/authorization, tenant isolation, quotas/rate limiting, durable workers, cancellation, real model-provider adapters, robust secret redaction, and a frontend are not yet implemented. Do not expose it as a public multi-user service until these controls, security tests, and load tests are implemented and reviewed.

## Roadmap

1. Expand correctness, robustness, and security scenario packs.
2. Add real agent/framework adapters and model-provider adapters (starting with OpenRouter).
3. Add adversarial prompt and tool-use evaluation with trace capture and policy assertions.
4. Implement isolated workers before running untrusted agents.
5. Add persistent evaluation history, authentication, quotas, regression comparisons, richer tracing, and load tests.
