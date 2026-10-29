# Cognis architecture

## Product scope

Cognis evaluates a declared set of cases against an agent or model endpoint. A case supplies an input, optional expected output, required/forbidden phrases, latency budget, and tags. Cognis runs the case, normalizes the output, evaluates assertions, aggregates metrics, and emits a machine-readable result that can be persisted and inspected.

The repository currently implements a practical evaluation MVP. It is not a general-purpose hostile-code execution service or an agent-security certification system.

## Runtime flow

```text
Client / dashboard
       |
       v
FastAPI API + bearer authentication
       |
       +--> Validate request size, cases, target configuration
       |
       v
Target adapter
  |                 |
  | built-in        | connected target (BYOK / HTTP)
  | agent            | production requires operator egress proxy
  v                 v
Evaluation runner -> Agent output
       |
       v
Deterministic assertions
  - expected output
  - required / forbidden content
  - latency budget
  - execution-error handling
       |
       v
Case results + run metrics
       |
       +--> SQLite / PostgreSQL persistence (tenant-scoped)
       |
       +--> JSON / Markdown reports
```

## Main components

- `app/main.py`: FastAPI routes, request validation, authentication, connected-target orchestration, health checks, and persistence calls.
- `app/engine/scenarios.py`: evaluation case and scenario contracts.
- `app/engine/runner.py`: invokes trusted adapter interfaces and normalizes outputs.
- `app/engine/evaluator.py`: executes cases sequentially, applies assertions, captures optional adapter-provided tool-call/trace metadata, and constructs the evaluation result.
- `app/observability/trace_sanitizer.py`: applies best-effort credential redaction and size/depth bounds to adapter-provided trace metadata before returning it.
- `app/engine/assertions.py`: deterministic assertions for correctness and output constraints.
- `app/engine/security_suite.py`: a small, hand-written security regression suite.
- `app/targets/http_agent.py`: JSON-over-HTTP agent adapter.
- `app/targets/openai_compatible.py`: BYOK adapter for OpenAI-compatible model endpoints.
- `app/targets/http_utils.py`: bounded streaming response parsing for remote targets.
- `app/security/auth_config.py`: startup validation of production bearer-token configuration.
- `app/security/egress.py`: production connected-target proxy configuration policy.
- `app/engine/container_worker.py`: disposable, resource-limited Docker workers for registered adapters.
- `app/storage/evaluations.py`: SQLite/PostgreSQL persistence and tenant-scoped history queries.
- `app/observability/telemetry.py`: latency and pass-rate aggregation.
- `scripts/run_demo.py`: no-API-key deterministic recruiter demo and report generation.
- `app/static/dashboard.html`: lightweight browser dashboard served by the API.

## Execution and trust boundaries

### In-process evaluation

The deterministic demo and trusted adapter path execute inside the API process. Timeouts limit how long Cognis waits, but they do not turn arbitrary code into a sandbox. Do not expose an endpoint that executes user-uploaded Python or arbitrary plugins in this process.

### Subprocess isolation

The subprocess path improves fault containment for registered adapters. It does not enforce operating-system network or filesystem isolation and must not be described as a hostile-code sandbox.

### Docker worker isolation

The container worker runs only registered adapters and applies a read-only root filesystem, non-root UID, dropped Linux capabilities, no-new-privileges, resource limits, and a network-disabled default. Docker daemon access is highly privileged; production should use a dedicated worker host/daemon and must not expose its socket to untrusted clients.

### Connected remote targets

In development, connected targets can make direct HTTPS requests after URL validation. In production, `POST /evaluations/connected` requires `COGNIS_EGRESS_PROXY_URL`. That proxy must enforce destination-IP policy at connection time and be paired with network controls that prevent bypass. The application setting alone does not implement or prove the proxy's filtering policy.

## Persistence and tenant identity

Protected API requests derive tenant identity from an operator-managed bearer-token mapping. The tenant ID is not accepted from a caller-controlled request field. Evaluation history queries filter by that authenticated identity. This is a useful baseline, not a complete SaaS identity and key-lifecycle system.

SQLite is convenient for local use. PostgreSQL is the better starting point for multi-user deployments, but production still needs migrations, backup/restore procedures, connection-pool tuning, retention policy, and operational monitoring.

## Deliberate limitations

- Evaluations execute cases sequentially; there is no durable background-job queue yet.
- Metrics include pass/fail counts, pass rate, and latency summaries; token/cost, repeated-trial confidence, and benchmark-calibrated scores are not yet comprehensive.
- Connected adapters primarily evaluate final text output. Tool-call traces, authorization decisions, side effects, and multi-step agent state are not comprehensively captured.
- The security suite is small and deterministic. It is a regression signal, not proof that an agent is secure.


## Adapter traces and privacy

Framework adapters may return `AgentExecution(output=..., tool_calls=..., trace=...)`. When `include_traces=true`, Cognis includes the adapter-provided tool-call records and trace metadata in each case result after best-effort redaction and bounds. When `include_traces=false`, these metadata fields are omitted from the result.

The sanitizer is not a data-loss-prevention guarantee: arbitrary secrets, personal data, or provider-specific formats may not be recognized. Treat traces and outputs as sensitive customer data. Before offering a hosted multi-tenant service, define retention/deletion controls and access policy, and add provider-specific redaction and tests. The built-in HTTP and OpenAI-compatible adapters currently return text and do not automatically reconstruct hidden tool traces.


## Tool-call policy assertions

A case may declare `forbidden_tools`. If an adapter provides a complete tool-call event list, the evaluator fails the case when a recorded tool name matches that list—even if the final response passes its text assertions. If evidence is unavailable or malformed, the policy assertion fails closed.

An HTTP agent can return its normal output plus a complete `tool_calls` array, for example:

```json
{
  "output": "I only looked up the order.",
  "tool_calls": [{"name": "issue_refund", "arguments": {"order_id": "demo-123"}}],
  "trace": {"event": "tool_call"}
}
```

To assert that no tool calls occurred, include `"tool_calls": []`. Cognis can evaluate only events the adapter reports; it cannot independently verify that an arbitrary remote agent reports every action truthfully. This is instrumented policy evaluation, not runtime enforcement or a security certification.
