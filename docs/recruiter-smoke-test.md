# Recruiter smoke test: connect an HTTP agent

Cognis includes a deterministic HTTP fixture so a reviewer can verify the connected-target path without a provider key.

1. Use Python 3.12 and install dependencies as described in the README.
2. In terminal 1, run the API with `COGNIS_ALLOW_PRIVATE_AGENT_URLS=true` and `python -m uvicorn app.main:app --reload --port 8000`.
3. In terminal 2, run `python -m uvicorn examples.sample_http_agent:app --reload --port 8001`.
4. Open `http://127.0.0.1:8000/dashboard`.
5. Choose **Connect target → Existing HTTP agent** and use `http://127.0.0.1:8001/run`, input field `input`, output field `output`, and the **Quality + security baseline** suite. Enable the local/private endpoint option.
6. Inspect the combined report. The fixture is intended to pass four quality cases and three response-level security cases.

The fixture is a deterministic contract test. It does not use an LLM, validate security of a real agent, or represent an internet-facing deployment. Private/loopback targets must remain disabled in public deployments. For real targets, prefer HTTPS and use a provider key with minimal permissions and usage limits.

The connected security baseline tests response-level assertions only. It cannot inspect hidden system prompts, observe tool calls unless an adapter explicitly supplies them, or prove that a target has no vulnerabilities.
