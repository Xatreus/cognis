# Cognis

Cognis is an extensible evaluation and reliability-testing platform for AI agents. It provides a provider-neutral Python evaluation core and a FastAPI service for evaluating a configured OpenRouter model against caller-defined cases.

## What is implemented

- Typed, reusable test cases and named evaluation scenarios.
- Python adapters for trusted callable agents and common `run`, `invoke`, `arun`, and `ainvoke` interfaces.
- Async-aware execution with per-invocation timeouts (not a security sandbox).
- Deterministic output assertions, required/forbidden text checks, per-case latency budgets, and a heuristic for obvious credential-like output.
- Baseline prompt-injection and synthetic-canary non-disclosure scenario builders.
- Per-case results plus pass-rate and latency metrics (mean, p50, p95, max).
- OpenRouter chat-completions adapter, with credentials loaded from environment variables.
- Custom evaluation API with bounded case counts, input lengths, and timeouts.
- Optional bearer-token API authentication using `COGNIS_API_KEY`.
- Docker image, Compose configuration, health endpoints, and CI.

## Run locally (Windows PowerShell)

Use Python 3.12.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in `.env`. Leave `COGNIS_API_KEY` empty for local development only; set a long random value before exposing the API beyond localhost. Then run:

```powershell
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

If `COGNIS_API_KEY` is configured, protected endpoints require `Authorization: Bearer <your-key>`. Health endpoints remain unauthenticated for liveness/readiness probes. Do not paste secrets into issues, source code, test fixtures, or logs.

## Endpoints

### Health

- `GET /health/live`
- `GET /health/ready`

### Deterministic demo

`POST /evaluations`

```json
{"suite":"demo","include_traces":true}
```

### Live OpenRouter smoke test

`POST /evaluations/openrouter`

```json
{"include_traces":true,"timeout_seconds":30}
```

This makes a real provider request and may incur charges. It asks the configured model to return `COGNIS_OK`. A passing result establishes only basic connectivity and instruction-following for that run, not general quality or security.

### Custom evaluation against the configured OpenRouter model

`POST /evaluations/custom`

```json
{
  "suite": "refund-policy-regression",
  "include_traces": true,
  "timeout_seconds": 20,
  "cases": [
    {
      "case_id": "cancelled_refund",
      "input": "Order cancelled; customer requests refund. Reply exactly refund_eligible.",
      "expected_output": "refund_eligible",
      "not_contains": ["COMPROMISED"],
      "max_latency_ms": 5000,
      "tags": ["correctness", "refund"]
    },
    {
      "case_id": "invoice_question",
      "input": "Where can I find my invoice? Reply exactly billing_support.",
      "expected_output": "billing_support",
      "tags": ["correctness"]
    }
  ]
}
```

The API bounds cases per request, input length, and timeout using `COGNIS_MAX_CASES_PER_REQUEST`, `COGNIS_MAX_INPUT_CHARS`, and `COGNIS_MAX_TIMEOUT_SECONDS`. Calls can consume provider credits. The case inputs and expected outcomes are supplied by you; meaningful evaluation depends on well-designed test data and outcome oracles.

## Use the engine from Python

Trusted agents can be tested without going through the HTTP endpoint:

```python
from app.engine.evaluator import run_evaluation
from app.engine.scenarios import EvaluationCase, EvaluationScenario

scenario = EvaluationScenario(
    name="example",
    cases=(
        EvaluationCase(
            case_id="basic-response",
            input="Say exactly READY",
            expected_output="READY",
            tags=("correctness",),
        ),
    ),
)

# result = run_evaluation(your_trusted_agent, scenario)
```

Adapters should normalize the target framework's output and preserve relevant tool-call metadata where available. The current HTTP custom-evaluation endpoint targets the configured OpenRouter model; it does not accept arbitrary uploaded Python code or automatically connect to every agent framework.

## Security model and production limitations

**Do not treat this repository as a finished, publicly deployable multi-tenant production SaaS.** This hardening pass adds bounded custom evaluation and optional API authentication, but it does not provide all controls required for a public service.

- The runner executes trusted agent code in-process. Async/thread timeouts do not safely terminate hostile code. Never submit untrusted code; use disposable, resource-limited isolated workers before adding that capability.
- The optional bearer token is a single shared service credential, not user identity, tenant isolation, or per-user authorization. Configure it before exposing the API; a secret-free deployment is intended only for local development or a tightly restricted trusted network.
- Evaluation history is not persisted. There are no durable queues, distributed rate limits/quotas, cancellation, tenant-aware storage, or regression dashboard.
- The secret-pattern check is heuristic, and the prompt-injection/canary scenarios are baseline regressions, not comprehensive security assessments. Use synthetic canaries only, and design tests for the agent's actual threat model.
- The current OpenRouter adapter supports single-turn text chat. Tool calls, agent traces, multimodal inputs, provider cost/token telemetry, and framework-specific execution are not fully implemented.
- Before public production use, add isolated workers, identity and tenant boundaries, durable storage/queueing, rate limits, audit logging and secret redaction, robust telemetry, dependency/security scanning, load tests, deployment secrets management, and a security review.

## Tests

```powershell
python -m pytest -q
```

CI uses mocked provider calls and does not require an OpenRouter key. Live smoke/custom evaluations do require valid provider configuration.
