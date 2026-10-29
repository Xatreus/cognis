# Cognis

**Cognis is an evaluation and security-regression platform for AI agents.** Connect an agent or model endpoint, run quality and security cases, inspect individual failures, and compare measurable results.

Cognis is an actively developed portfolio project. It provides reproducible regression signals—not a guarantee that an agent is secure, and not a production security certification.

## Start here: run the demo

The deterministic demo needs no provider API key, Docker daemon, PostgreSQL server, or paid inference.

### Requirements

- Python **3.12–3.15** (Python 3.15 is a stable release).
- Git.

### Windows PowerShell

```powershell
git clone https://github.com/Xatreus/cognis.git
cd cognis
py -3.15 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m scripts.run_demo
```

If Python 3.15 is not installed, use `py -3.14`, `py -3.13`, or `py -3.12` instead.

The demo writes:
- `reports/demo-report.md` — human-readable results and failure details.
- `reports/demo-report.json` — machine-readable results, assertions, case metadata, and metrics.

A successful run currently expects **6/6 cases to pass**, including two response-level security regression cases. Runtime latency varies by machine. The report is generated from the real run, not a hard-coded example.

### Run the tests

```powershell
python -m pytest -q
```

GitHub Actions tests Python 3.12, 3.13, 3.14, and 3.15, builds the API and worker images, and smoke-tests the isolated worker protocol. See [CI runs](https://github.com/Xatreus/cognis/actions).

## Try the dashboard

Start Cognis locally:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:
- Dashboard: http://127.0.0.1:8000/dashboard
- Interactive API docs: http://127.0.0.1:8000/docs
- Readiness check: http://127.0.0.1:8000/health/ready

Local development is permissive when no API token is configured. Keep it bound to loopback and do not expose this development configuration to an untrusted network.

The dashboard supports running the deterministic demo, connecting a target, reviewing case-level assertions and latency, and browsing persisted evaluation history.

## Connect an agent

Cognis currently supports two target styles:

1. **Model API (BYOK):** OpenAI, Google Gemini through its OpenAI-compatible endpoint, OpenRouter, or another OpenAI-compatible HTTPS endpoint. Supply your own provider key and model.
2. **Existing HTTP agent:** expose a JSON-over-HTTP endpoint that accepts an input and returns a text output. If your agent uses a framework-specific runtime or protocol, put a small adapter endpoint in front of it.

Cognis does not require a centrally hosted model key. Provider credentials are request-scoped and are not intentionally persisted in evaluation history; still use limited-scope keys and synthetic test data.

### HTTP agent contract

Cognis sends a JSON POST similar to:

```json
{
  "input": "Classify this request",
  "metadata": {"source": "cognis"}
}
```

Your endpoint returns JSON with a string `output`, `response`, or `answer`, depending on the output-field setting:

```json
{"output": "SAFE"}
```

For tool-use policy checks, an instrumented endpoint can also return a complete `tool_calls` array and optional `trace` object. See [tool-call policy evaluation](docs/tool-call-policy-evaluation.md). Cognis can evaluate only the events an adapter reports; it cannot independently prove a remote agent's trace is complete.

### Run a connected evaluation through the API

For a remote agent, use its HTTPS endpoint and send a request such as:

```json
{
  "target_type": "http_agent",
  "suite": "quality",
  "endpoint_url": "https://your-agent.example/run",
  "agent_input_field": "input",
  "agent_output_field": "output",
  "timeout_seconds": 20,
  "include_traces": true,
  "cases": [
    {
      "case_id": "basic-classification",
      "input": "Classify this request as SAFE.",
      "expected_output": "SAFE",
      "tags": ["quality"]
    }
  ]
}
```

Send it to `POST /evaluations/connected`. If you configured a bearer token, include `Authorization: Bearer <your-token>`. The API documentation at `/docs` shows the request schema and available endpoints.

The built-in security suite is a small regression baseline, not a comprehensive adversarial campaign. Use cases appropriate to your agent's tools, permissions, data, and business risks.

### Local HTTP fixture

To test the HTTP integration without a hosted model key, start the API in one terminal and the sample fixture in another:

```powershell
# Terminal 1: local development API
$env:COGNIS_ALLOW_PRIVATE_AGENT_URLS = "true"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2: deterministic sample agent
python -m uvicorn examples.sample_http_agent:app --reload --host 127.0.0.1 --port 8001
```

In the dashboard, choose **Connect target** → **Existing HTTP agent**, set the endpoint to `http://127.0.0.1:8001/run`, select **Quality + security baseline**, and explicitly enable the local/private endpoint option.

This private-target opt-in is for local development only. Never enable it on a publicly reachable deployment. The fixture verifies the adapter workflow; it is not an LLM and does not demonstrate that arbitrary agents are secure.

## What Cognis evaluates

| Capability | Current behavior |
|---|---|
| Quality regression | Expected output, required/forbidden text, and case-level latency budgets |
| Security regression | Small prompt-injection, synthetic-canary, and system-prompt-disclosure probes |
| Tool-call policy | Can flag declared forbidden tool names when a target reports complete tool-call evidence |
| Metrics | Pass/fail counts, pass rate, and latency summaries |
| Reports | JSON and Markdown output with per-case assertions and diagnostic details |
| Dashboard/API | Run demo or connected evaluations and inspect tenant-scoped history |
| Persistence | SQLite for local use; optional PostgreSQL configuration |
| Execution workers | Separate disposable Docker worker path for registered adapters, with resource and container restrictions |

## Architecture

```text
Dashboard / API client
        |
        v
FastAPI + request validation + bearer authentication
        |
        v
Target adapter (registered agent / HTTP endpoint / compatible model API)
        |
        v
Evaluation runner
        |
        +--> deterministic assertions
        +--> security regression checks
        +--> adapter-provided tool-call policy checks
        |
        v
Case results + latency/pass-rate metrics
        |
        +--> JSON / Markdown reports
        +--> SQLite or PostgreSQL history
```

Useful entry points:
- `app/main.py` — API routes, request validation, authentication, and orchestration.
- `app/engine/scenarios.py` — scenario and case contracts.
- `app/engine/evaluator.py` — evaluation execution and result aggregation.
- `app/engine/assertions.py` — deterministic assertions.
- `app/engine/security_suite.py` — built-in security regression cases.
- `app/targets/http_agent.py` — HTTP-agent adapter.
- `app/targets/openai_compatible.py` — compatible model API adapter.
- `app/engine/container_worker.py` — isolated container execution for registered adapters.
- `app/storage/evaluations.py` — persistence and tenant-scoped history.
- `scripts/run_demo.py` — deterministic demo and report generation.

## Python and dependency policy

- The supported baseline is Python 3.12–3.15, exercised by the CI matrix.
- `requirements.txt` contains runtime dependencies. `requirements-dev.txt` adds test and lint tooling.
- Dependency ranges are bounded by major versions and define minimum versions; CI validates the currently resolved set. These are not a fully pinned lockfile.
- Docker images use Python 3.15; CI tests the application on 3.12, 3.13, 3.14, and 3.15.

See `pyproject.toml`, the requirements files, and [Dependabot configuration](.github/dependabot.yml) for details.

## Security, deployment, and limitations

Cognis is an evaluation tool—not a sandbox that can safely execute arbitrary user-supplied code, and not a security certification service.

- **Do not expose development mode publicly.** Configure strong bearer tokens, TLS, rate limits, quotas, logging controls, and an operator-managed secret policy before deployment.
- **Production connected evaluations require an egress proxy.** The proxy and network firewall must enforce destination-IP policy at connection time and prevent direct egress bypass. Setting the proxy URL alone does not make an arbitrary proxy safe.
- **Never expose the Docker socket to untrusted clients.** Container execution should use a dedicated worker host/daemon with restrictive network and resource policy.
- **Subprocess execution is not a hostile-code sandbox.** The Docker worker path has stronger isolation controls but still requires deployment-specific review.
- **Security probes are intentionally small.** Passing them is not evidence of broad prompt-injection resistance, data protection, authorization correctness, or safe tool behavior.
- **Trace checks depend on the adapter.** Cognis cannot independently verify that a remote agent reports every tool call or side effect.
- **Outputs and traces may contain sensitive information.** Use synthetic data, review retention/access policies, and avoid sending secrets or real customer data to test endpoints.
- **Production readiness remains a work in progress.** Background job orchestration, complete observability/cost metrics, deployment-specific security review, and broader adversarial coverage remain areas for further engineering.

For design and trust boundaries, see [architecture](docs/architecture.md) and [tool-call policy evaluation](docs/tool-call-policy-evaluation.md).

## Development workflow

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m scripts.run_demo --output-dir reports
```

Please report bugs or propose improvements through [GitHub Issues](https://github.com/Xatreus/cognis/issues).
