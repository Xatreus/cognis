# Cognis threat model

## Status

This is an implementation-oriented threat model for the current Cognis MVP. It records implemented controls and remaining gaps; it is not a certification or a claim that the deployment has been independently penetration-tested.

## Assets

- Operator API bearer tokens and tenant mappings.
- User-supplied provider keys and HTTP-agent authentication tokens.
- Evaluation inputs, outputs, traces, reports, and persisted history.
- Host and cloud credentials available to the API or worker environment.
- Docker daemon access and worker-host integrity.
- Availability of the API, database, and worker capacity.

## Trust boundaries and threat actors

| Boundary / actor | Example threat | Main control or status |
|---|---|---|
| Unauthenticated client -> API | Unauthorized evaluation or history access | Protected routes require bearer authentication; production startup validates token configuration. |
| Tenant A -> Tenant B data | Guess or retrieve another tenant's evaluation ID | History queries scope both list and detail reads by authenticated tenant; API regression tests cover cross-tenant detail access. |
| Caller -> connected target URL | SSRF to internal services or cloud metadata | HTTPS/public-address validation, redirects disabled, and production connected-target requests require an operator egress proxy. Proxy-side connection-time IP enforcement and firewall policy remain deployment responsibilities. |
| Caller -> provider endpoint | Redirect a preset provider key to an attacker host | Preset providers reject caller-supplied base URLs. Custom hosts require explicit OpenAI-compatible provider selection. |
| Malicious or faulty target -> API | Return huge bodies or malformed JSON | Streaming JSON response bodies are capped at 1,000,000 bytes; request timeouts are bounded. |
| Untrusted agent code -> host | Read files, access network, exhaust CPU/memory, or escape | Arbitrary uploaded code is not supported. Container execution is limited to registered adapters and uses a restrictive container policy. Docker daemon compromise remains a high-impact risk. |
| Evaluation output -> logs/reports | Expose provider keys or sensitive user content | Provider keys are request-scoped and not intentionally persisted; error logs avoid request models and raw provider credentials. Output data itself may contain user-sensitive information and requires retention/access controls. |
| Client -> service availability | Submit excessive cases or slow targets | Case/input/time limits and per-request timeouts exist. Durable quotas, distributed rate limiting, and global concurrency limits remain gaps. |

## Implemented safeguards

- Bearer authentication with server-configured tenant identity.
- Production startup rejection of missing, malformed, or short API tokens.
- Tenant-scoped evaluation history reads.
- Fixed endpoint URLs for preset model providers.
- HTTPS and non-public-IP checks for connected endpoints, with redirects disabled.
- Production egress-proxy requirement for connected targets.
- Bounded streaming response-body parsing.
- Request case-count, input-length, and timeout limits.
- Docker worker defaults: no network, read-only root filesystem, non-root user, dropped capabilities, no-new-privileges, CPU/memory/PID limits, and disposable containers.
- CI tests, deterministic demo reports, and worker protocol smoke tests.

## Important residual risks

1. **Egress policy is external.** Setting `COGNIS_EGRESS_PROXY_URL` is not enough by itself. The deployed proxy must resolve and validate all IPv4/IPv6 destinations at connection time, connect only to approved public addresses, block metadata/private/link-local/reserved networks, and be protected by a firewall preventing direct egress. Test the actual deployment.
2. **Docker daemon access is privileged.** Do not mount the host Docker socket into an internet-facing API container. Prefer a separate, dedicated worker host or service with narrow job submission permissions.
3. **No durable queue or complete quotas.** Long runs can occupy request workers. Do not advertise high-concurrency multi-tenant service guarantees until queueing, cancellation, tenant budgets, and load tests exist.
4. **Limited agent visibility.** Current adapters mostly return text. Cognis cannot reliably detect forbidden tool calls, unauthorized side effects, or data exfiltration that does not appear in the final output without instrumentation/traces.
5. **Small security corpus.** Hand-written prompts have limited coverage and can produce false positives/negatives. Use versioned attack suites, independent detectors, repeated trials, and known vulnerable/safe fixtures.
6. **Operational controls remain.** Hosted deployments need TLS termination, secret rotation/revocation, audit logging, data-retention/deletion controls, backups, monitoring, dependency/image scanning, and incident-response procedures.

## Safe deployment guidance

- Keep local development bound to loopback.
- Use strong randomly generated bearer tokens and store them in a secret manager.
- Use PostgreSQL for shared deployments and validate migrations, backup/restore, and tenant boundaries.
- Run a policy-enforcing egress proxy with network firewall controls before enabling connected-target evaluation in production.
- Run Docker workers on a dedicated host/daemon; never give external clients direct Docker API access.
- Use synthetic data and isolated test agents. Avoid testing destructive actions against production systems.
- Treat every report as evidence about the tested cases only, not as a general security guarantee.
