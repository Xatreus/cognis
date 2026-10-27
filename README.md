# Cognis

Cognis is an agent evaluation and reliability testing platform. This repository now contains a deployable API foundation and a deterministic demo target that exercises the evaluation pipeline.

## Current capabilities
- FastAPI API with liveness/readiness endpoints.
- Typed evaluation request/response schemas.
- A deterministic demo agent and independent expected outcomes.
- Per-case pass/fail, latency measurement, and optional error details.
- Docker image, Docker Compose configuration, and GitHub Actions CI.

## Run locally
Use Python 3.12.

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs.

## Tests
```bash
python -m pytest -q
```

## Docker
```bash
docker compose up --build
```

Submit `POST /evaluations` with `{"suite":"demo","include_traces":true}`. Health endpoints are `/health/live` and `/health/ready`.

## Architecture
HTTP API (FastAPI) -> Pydantic schemas -> evaluation engine -> demo agent adapter. Scenario expected outcomes are declared independently from agent logic, avoiding the most basic form of self-grading.

## Production readiness status
This is a deployable engineering foundation, **not yet a complete production SaaS**. It does not yet provide persistent run storage, authentication/authorization, tenant isolation, rate limiting, durable background workers, real model-provider adapters, secret management, or a frontend. Do not expose it as a public multi-user service until these are implemented and security/load tests are passed.

Recommended next milestones: persistence and migrations; auth/tenant isolation/quotas; durable workers, cancellation and timeouts; provider adapters with retries and redaction; metrics/tracing/alerts; dependency and security scanning; deployment-specific integration and load tests.
