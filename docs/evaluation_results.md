# Cognis evaluation reports

## Reproduce the baseline

The committed recruiter demo uses a deterministic rule-based support agent and six hand-written cases. It requires Python 3.12 and does not call a hosted model or require an API key.

From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m scripts.run_demo --output-dir reports
python -m pytest -q
```

The demo writes `reports/demo-report.md` and `reports/demo-report.json`. CI runs the same demo and uploads the report artifacts. The generated output is the source of truth for a particular run; latency values vary with host load.

## What is measured today

- Total cases, passed/failed cases, and pass rate.
- Per-case expected and actual output.
- Assertion failures and optional error details.
- Per-case latency and run-level mean, p50, p95, and maximum latency.
- Security-tagged case results.

The connected security baseline currently consists of three narrow hand-written cases: prompt-injection resistance, synthetic canary non-disclosure, and system-prompt disclosure resistance. The recruiter demo also includes deterministic correctness, input-robustness, and output non-disclosure fixtures.

## Interpreting results

A case passes only when its declared deterministic assertions pass and execution itself succeeds. An execution error is not converted into a pass just because the case expects an error-shaped output.

A passing run means only that the target met the assertions in that run. It does not establish that the target is generally correct, secure, reliable, or production-ready. Security cases are not a statistically representative benchmark, and final-text checks cannot observe hidden tool calls or side effects.

Latency measurements are local run observations, not service-level objectives. For model-backed runs, results can vary by model version, provider, prompt, randomness, provider load, and rate limits.

## Recommended next benchmark additions

1. Version the scenario corpus and record its exact version/hash in every run.
2. Add known-safe and known-vulnerable agent fixtures to measure detector false positives and false negatives.
3. Add multi-turn and indirect prompt-injection cases.
4. Instrument tool calls, arguments, results, authorization decisions, and side effects.
5. Record model/provider identifier, run configuration, token usage, and estimated cost where the provider exposes them.
6. Repeat stochastic tests and report trial count and variation rather than relying on one run.
7. Separate task quality, security, and operational reliability scores; do not let strong quality offset a severe security failure.
