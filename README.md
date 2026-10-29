# Cognis

**Cognis is an agent evaluation and reliability-testing platform.** It runs a defined set of inputs against an agent, checks its outputs against explicit assertions, records per-case latency, and produces a report that can be inspected and reproduced.

This repository includes a **no-API-key recruiter demo**: a deterministic sample support agent, six committed test cases, and Markdown/JSON reports. It is designed to demonstrate the evaluation workflow clearly; it is not presented as a production security certification or an LLM benchmark.

## See the demo first

### Requirements
- Python 3.12 (the CI version)
- Git

No OpenRouter key, Docker daemon, PostgreSQL server, or network access is needed for the standalone demo.

### Windows PowerShell

```powershell
git clone https://github.com/Xatreus/cognis.git
cd cognis
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m scripts.run_demo
```

The command prints a report and writes:
- `reports/demo-report.md` — human-readable summary, latency metrics, per-case outcomes, and failure details.
- `reports/demo-report.json` — complete machine-readable evaluation result, including assertions and case metadata.

Exit code is `0` when every case passes and `1` when the evaluation fails. To choose another output path:

```powershell
python -m examples.run_demo --output reports/my-report.md --json-output reports/my-report.json
```

### What the six cases check

| Case | Category | Expected behavior |
|---|---|---|
| Cancelled order refund | Correctness | Routes to `refund_eligible` |
| Delivered order refund | Correctness | Routes to `review_required` |
| Invoice question | Correctness | Routes to `human_review` |
| Empty input | Robustness | Returns an evaluation result of `error` |
| Prompt-injection override | Security regression | Preserves the trusted task's expected `SAFE` output |
| Synthetic canary | Security regression | Does not echo the synthetic canary value |

The sample agent and scenario live in `examples/sample_agent.py` and `scripts/run_demo.py`. The tests are ordinary Python tests and can be inspected or extended.

## Example report

A successful run should report **6/6 passed**, **0 failures**, and **2/2 security-tagged cases passed**. Latency is measured at runtime, so exact values vary by machine. Each report includes:

- Overall status and pass rate
- Failure count and per-case expected/actual output
- Mean, p50, p95, and maximum latency
- Security-tagged case results
- Assertion failures and diagnostic messages
- An explicit limitations section

The report is generated from the actual evaluation response, not a hard-coded example. CI runs the same demo and uploads the Markdown and JSON outputs as the `cognis-demo-report` artifact.

## Run the tests

```powershell
python -m pytest -q
```

The test suite covers the deterministic demo/report, API behavior, storage, and tenant-scoped history. GitHub Actions also builds the API and worker Docker images and smoke-tests the worker protocol. Check the pull request's Actions checks for the authoritative result; a local run is not claimed unless it was actually executed.

## Architecture at a glance

```text
Test scenario (cases, expectations, tags)
                  |
                  v
       Agent execution adapter
                  |
                  v
       Output normalization
                  |
                  v
       Deterministic assertions
       - expected output
       - required / forbidden text
       - latency budget
       - obvious secret-like output
                  |
                  v
       Per-case results + metrics
                  |
          +-------+-------+
          |               |
          v               v
      JSON result     Markdown report
          |
          v
   Optional API persistence
   SQLite (local) / PostgreSQL
   Tenant-scoped evaluation history
```

Key code paths:
- `app/engine/scenarios.py` — reusable scenario and case definitions.
- `app/engine/runner.py` — sync/async invocation adapter and timeout handling.
- `app/engine/assertions.py` — deterministic output assertions.
- `app/engine/evaluator.py` — runs cases and computes evaluation metrics.
- `app/observability/telemetry.py` — latency and reliability aggregates.
- `examples/sample_agent.py` — sample agent; `scripts/run_demo.py` — recruiter scenario and report generator.
- `app/main.py` — FastAPI endpoints and authentication.
- `app/storage/evaluations.py` — SQLite/PostgreSQL persistence and tenant-scoped history queries.

## Evaluation dashboard

Start the API locally and open the browser dashboard:

```powershell
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/dashboard`. The dashboard uses the real Cognis API and tenant-scoped persisted history. From it you can run the deterministic demo suite, inspect each case's expected and actual output, review assertion failures and latency metrics, and browse previous runs. It does not require a hosted model key. If the API has bearer-token authentication configured, the dashboard prompts for a token when the API returns an authentication error; the token stays in the current browser session.

Dashboard assets are served by FastAPI from `app/static/`; no separate frontend build or Node installation is needed. The dashboard is an operator/developer console, not a complete multi-user SaaS frontend.

## API and optional integrations

Run the API locally:

```powershell
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`. The deterministic API demo is `POST /evaluations` with:

```json
{"suite":"demo","include_traces":true}
```

Completed runs can be listed with `GET /evaluations/history` and retrieved with `GET /evaluations/history/{evaluation_id}`. Protected endpoints accept a bearer token. In local development, authentication is permissive when no key configuration is set; do not expose that configuration to an untrusted network.

For multiple demo tenants, set `COGNIS_API_KEYS_JSON` to a JSON mapping of distinct high-entropy bearer tokens to tenant IDs, for example:

```json
{"replace-with-random-key-for-a":"customer-a","replace-with-random-key-for-b":"customer-b"}
```

Keep real keys in environment configuration or a secret manager, never in Git. The API derives tenant identity from the configured token mapping; callers cannot select their own tenant through a request field. The current mapping is an operator-managed environment configuration, **not** a complete tenant onboarding or API-key lifecycle system.

### PostgreSQL

The API accepts `COGNIS_DATABASE_URL`, for example `postgresql://cognis:password@localhost:5432/cognis`. The Compose file contains an opt-in PostgreSQL service; set `POSTGRES_PASSWORD` and configure `COGNIS_DATABASE_URL` to point to the Compose hostname `postgres` when running the API and database together. SQLite remains the zero-setup local default. Review the Compose profiles and environment values before deployment.

### Live model provider

The OpenRouter adapter can run a live smoke test using `OPENROUTER_API_KEY` and `OPENROUTER_MODEL`. Provider tests may incur charges and depend on network/provider availability. The recruiter demo does not call a hosted model.

## Security and limitations

Cognis provides useful **regression signals**, not proof of correctness or security:

- The included sample agent is deterministic Python logic, not an LLM; its tests prove the evaluation pipeline works on known examples, not that a general-purpose model is safe.
- The six demo cases are small and hand-written. They are not a statistically representative benchmark.
- Prompt-injection and synthetic-canary tests cover only their stated fixtures. Passing them does not establish resistance to broader prompt injection or data exfiltration.
- The obvious-secret check is heuristic and can miss leaks or flag harmless text.
- Latency values are local measurements, not production capacity guarantees.
- The in-process execution runner's timeout is not a sandbox. Use the isolated worker path for supported untrusted-agent execution and review its threat model before deployment.
- Tenant scoping in application queries is not a substitute for a full SaaS identity lifecycle, key rotation/revocation, database-level row security, audit logging, rate limiting, and a production security review.
- PostgreSQL support and tenant isolation should be validated by CI and tested in the target deployment configuration before relying on them operationally.

## Project status

This is an actively developed portfolio project focused on agent evaluation, reproducible testing, observability, worker isolation, and tenant-aware persistence. See the code, tests, CI results, and generated report to verify the implemented behavior rather than relying on claims in this document.


## Connect your own model or agent (BYOK)

Start the API and open `http://127.0.0.1:8000/dashboard`:

```powershell
uvicorn app.main:app --reload
```

Choose **Connect target**. Cognis currently supports:

- **OpenAI** — provide your API key and model ID.
- **Google Gemini** — use a Gemini API key and an OpenAI-compatible model ID. Cognis uses Google's documented OpenAI-compatible endpoint.
- **OpenRouter** — provide your own OpenRouter key and model ID.
- **Other OpenAI-compatible APIs** — provide an HTTPS base URL, key, and model ID.
- **Existing HTTP agent** — provide an HTTPS endpoint and optional bearer token.

For a model provider, the key is sent only with the evaluation request and is not stored in evaluation history. Cognis does not need your OpenRouter key or any centrally hosted provider key for user-supplied runs. Use a provider key with limited permissions and usage limits.

### HTTP agent contract

Cognis sends a JSON POST request to the endpoint you configure:

```json
{
  "input": "Classify this request",
  "metadata": {"source": "cognis"}
}
```

Your endpoint should return JSON containing a string `output` or `response`:

```json
{"output": "SAFE"}
```

This is a minimal interoperability contract. Agents that require a different protocol can expose a small adapter endpoint or later use a dedicated Cognis SDK.

### Test suites

- **Quality** — provide a custom input and optional exact expected output / required phrase.
- **Security baseline** — deterministic prompt-injection, synthetic-canary disclosure, and system-prompt disclosure probes.
- **Quality + security baseline** — runs the demo quality cases plus the security baseline unless you supply custom quality cases.

Security baseline results are signals, not proof of security or a certification. Exact-output probes can produce false positives for models that answer in a different but safe wording. Review evidence and tailor cases to your application's policy.

### Local agent development and SSRF protection

For security, Cognis requires HTTPS for remote agent endpoints and blocks non-public IP destinations by default. Private/loopback targets are allowed only when both the server enables `COGNIS_ALLOW_PRIVATE_AGENT_URLS=true` and the request explicitly opts in. **Do not enable this on a publicly accessible deployment.** This opt-in is intended for local development only.

This first connector release uses request-scoped credentials; it does not save reusable connections. Do not expose the API publicly without authentication, rate limits, request quotas, and isolated workers. Avoid sending production secrets or enabling agents that can perform destructive actions while testing.


## Connect Invoice Buddy from the dashboard

Cognis can call Invoice Buddy's existing `POST /ask` API without changing Invoice Buddy's code. Run both APIs locally on your machine.

1. Start Invoice Buddy in its repository with its configured LLM key and API key:
   ```powershell
   $env:OPENROUTER_API_KEY = "your-own-provider-key"
   $env:INVOICE_BUDDY_API_KEY = "your-invoice-buddy-api-key"
   python -m uvicorn invoice_buddy.api:app --app-dir src --reload --port 8001
   ```
2. In a second terminal, start Cognis with its local agent connector enabled:
   ```powershell
   $env:COGNIS_ALLOW_PRIVATE_AGENT_URLS = "true"
   python -m uvicorn app.main:app --reload --port 8000
   ```
   The private URL opt-in is for local development only. Do not enable it on a public deployment.
3. Open `http://127.0.0.1:8000/dashboard`, click **Connect target**, and choose **Existing HTTP agent**.
4. Set the endpoint to `http://127.0.0.1:8001/ask`, choose **Invoice Buddy API (question → answer)**, choose **X-API-Key**, enter the same Invoice Buddy API key, and enable **Allow local/private endpoint**.
5. Choose **Custom quality cases** and test one question at a time, such as `What is the total spend by vendor?`. Add an expected phrase only if you know it should appear based on the invoices currently in your local database.

Invoice Buddy accepts `{"question":"..."}` and returns `{"answer":"..."}`; Cognis maps that contract to its target interface. The custom quality form currently accepts one case per run. Use a question that is appropriate for your own seeded invoice data; an empty database cannot produce meaningful financial-answer checks.

**Important:** these are real LLM calls through Invoice Buddy and may consume your configured provider quota. Do not upload real financial documents or expose either local API publicly while testing. Cognis records evaluation outputs, so test with synthetic invoice data and avoid asking questions that would return sensitive information.
