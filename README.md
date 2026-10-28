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

If `COGNIS_API_KEY` is configured, protected endpoints require `Authorization: Bearer <your-key>`. Health endpoints remain unauthenticated for liveness/readiness probes. Do not paste secrets into issues, source code, test fixtures, or logs. For deployed environments, set `COGNIS_ENV=production` and configure a randomly generated `COGNIS_API_KEY` of at least 32 characters. In production mode the API refuses to start if that key is missing or too short, rather than silently disabling authentication. Keep `COGNIS_ENV=development` for local work.

## Endpoints

### Persisted evaluation history

Completed demo, custom, isolated, container, and OpenRouter evaluation runs are stored in SQLite before the API returns a successful response. The default local database is `data/cognis.db` (ignored by Git); Docker uses `/data/cognis.db` on the named `cognis-data` volume. Configure `COGNIS_DATABASE_PATH` to choose another path.

- `GET /evaluations/history?limit=20&offset=0` — paginated run summaries.
- `GET /evaluations/history/{evaluation_id}` — full stored response and creation timestamp.

History endpoints use the same bearer-token gate as evaluation endpoints. SQLite is suitable for local development and a single API instance; use PostgreSQL with migrations and tenant-scoped queries before horizontal scaling or multi-tenant production.

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


### Container-isolated worker (experimental)

`POST /evaluations/container` runs each case in a disposable Docker container. The separate `Dockerfile.worker` image runs as UID 65532 with a read-only root filesystem, all Linux capabilities dropped, `no-new-privileges`, no host mounts, private IPC, an ephemeral `/tmp`, and bounded memory, CPU, PIDs, wall-clock time, and output. Network is disabled by default. Only the built-in `demo` and `openrouter` adapters are accepted; requests cannot select arbitrary imports or upload code.

Build the worker image first:

```powershell
docker build -f Dockerfile.worker -t cognis-agent-worker:latest .
```

The API process needs access to a Docker Engine to create disposable workers. For local Linux development, configure Docker SDK access to a dedicated development daemon. The optional Compose service below mounts the host Docker socket; **the Docker socket is effectively host-root access**. Do not expose that API service publicly or use the same daemon that hosts sensitive workloads. For real production, use a separate worker host/daemon or a narrowly scoped remote worker service and protect its credentials.

```powershell
docker compose --profile docker-workers build cognis-worker-image cognis-api-with-docker-workers
docker compose --profile docker-workers up cognis-api-with-docker-workers
```

The default API service does not mount the Docker socket. Docker Desktop on Windows may not support mounting a host socket the same way as Linux; use a reachable Docker Engine endpoint or run the worker backend on a dedicated Linux host. Do not expose an unauthenticated remote Docker TCP endpoint.

Example request:

```json
{
  "agent_id": "demo",
  "suite": "container-refund-check",
  "timeout_seconds": 15,
  "memory_limit_mb": 512,
  "cpu_limit": 1.0,
  "pids_limit": 64,
  "network_enabled": false,
  "cases": [
    {
      "case_id": "cancelled-refund",
      "input": "Order cancelled; customer requests refund",
      "expected_output": "refund_eligible",
      "tags": ["correctness"]
    }
  ]
}
```

The Docker backend materially improves isolation, but **a container alone is not a complete security guarantee for arbitrary hostile code**. Use a dedicated host/daemon, patch the host kernel and Docker Engine, enforce host-level resource quotas, keep network disabled unless required, and use synthetic secrets only in security tests. OpenRouter workers need outbound network access, so setting `network_enabled: true` weakens network isolation and should be allowed only for trusted provider adapters. Worker containers receive only the OpenRouter environment variables needed by that adapter.


```json
{
  "agent_id": "demo",
  "suite": "isolated-refund-check",
  "timeout_seconds": 10,
  "memory_limit_mb": 512,
  "cases": [
    {
      "case_id": "cancelled-refund",
      "input": "Order cancelled; customer requests refund",
      "expected_output": "refund_eligible",
      "tags": ["correctness"]
    }
  ]
}
```

The worker uses a JSON request/response protocol, a bounded wall-clock timeout, a restricted inherited environment, output-size checks, and POSIX address-space/file-descriptor/core-dump limits where supported. These measures improve crash and timeout containment. **This subprocess backend does not enforce network isolation or filesystem read-only mode and is not a security sandbox for hostile code.** The `network_enabled` and `filesystem_read_only` policy fields are intent only here. Do not run untrusted agent code. A real multi-user production worker needs container/VM isolation with OS-enforced network policy, read-only mounts, non-root identity, seccomp/AppArmor, cgroup limits, ephemeral credentials, and cleanup.

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

**Do not treat this repository as a finished, publicly deployable multi-tenant production SaaS.** This hardening pass adds bounded custom evaluation, optional API authentication, and SQLite-backed history for a single instance, but it does not provide all controls required for a public service.

- The runner executes trusted agent code in-process. Async/thread timeouts do not safely terminate hostile code. Never submit untrusted code; use disposable, resource-limited isolated workers before adding that capability.
- The optional bearer token is a single shared service credential, not user identity, tenant isolation, or per-user authorization. Configure it before exposing the API; a secret-free deployment is intended only for local development or a tightly restricted trusted network.
- SQLite evaluation history is persisted for a single instance. There are no durable worker queues, distributed rate limits/quotas, cancellation, tenant-aware storage, or regression dashboard. SQLite is not a substitute for PostgreSQL in a horizontally scaled multi-tenant deployment.
- The secret-pattern check is heuristic, and the prompt-injection/canary scenarios are baseline regressions, not comprehensive security assessments. Use synthetic canaries only, and design tests for the agent's actual threat model.
- The current OpenRouter adapter supports single-turn text chat. Tool calls, agent traces, multimodal inputs, provider cost/token telemetry, and framework-specific execution are not fully implemented.
- Before public production use, add isolated workers, identity and tenant boundaries, durable storage/queueing, rate limits, audit logging and secret redaction, robust telemetry, dependency/security scanning, load tests, deployment secrets management, and a security review.

## Tests

```powershell
python -m pytest -q
```

CI uses mocked provider calls and does not require an OpenRouter key. Live smoke/custom evaluations do require valid provider configuration.
