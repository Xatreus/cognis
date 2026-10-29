"""Cognis HTTP API.

Do not expose this service publicly without authentication, durable storage,
tenant isolation, quotas, and isolated workers for untrusted target agents.
"""
import logging
import os
import secrets
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

load_dotenv()

from app.agents.openrouter import OpenRouterAgent, OpenRouterConfigurationError
from app.engine.evaluator import run_demo_evaluation, run_evaluation
from app.engine.provider_scenarios import OPENROUTER_SMOKE_SCENARIO
from app.engine.isolation import IsolatedWorkerError, IsolationPolicy, run_isolated_agent
from app.engine.container_worker import ContainerPolicy, ContainerWorkerError, run_container_agent
from app.engine.runner import AgentExecutionError
from app.engine.scenarios import EvaluationCase, EvaluationScenario
from app.observability.logging import configure_logging
from app.schemas.evaluations import EvaluationRequest, EvaluationResponse
from app.services.task_service import create_task as create_task_service
from app.storage.evaluations import check_store, get_evaluation, initialize_store, list_evaluations, save_evaluation

configure_logging()
logger = logging.getLogger(__name__)

MAX_CASES_PER_REQUEST = int(os.getenv("COGNIS_MAX_CASES_PER_REQUEST", "50"))
MAX_INPUT_CHARS = int(os.getenv("COGNIS_MAX_INPUT_CHARS", "12000"))
MAX_TIMEOUT_SECONDS = float(os.getenv("COGNIS_MAX_TIMEOUT_SECONDS", "60"))
API_KEY = os.getenv("COGNIS_API_KEY", "").strip()
COGNIS_ENV = os.getenv("COGNIS_ENV", "development").strip().lower()

# Fail closed in production rather than silently running protected endpoints
# without authentication when a deployment secret was omitted.
if COGNIS_ENV == "production" and len(API_KEY) < 32 and not os.getenv("COGNIS_API_KEYS_JSON", "").strip():
    raise RuntimeError(
        "Production requires COGNIS_API_KEY with at least 32 characters."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_store()
    logger.info("Cognis API starting")
    yield
    logger.info("Cognis API stopping")


def persist_evaluation(result: EvaluationResponse, tenant_id: str) -> EvaluationResponse:
    """Persist a completed result before returning it to the caller."""
    try:
        save_evaluation(result, tenant_id=tenant_id)
    except Exception as exc:
        logger.exception("Could not persist evaluation result")
        raise HTTPException(status_code=503, detail="Evaluation completed but could not be stored") from exc
    return result


app = FastAPI(
    title="Cognis Agent Evaluation API",
    description=(
        "Evaluate trusted callable/run/invoke-style agents against correctness, "
        "robustness, basic output-safety, and latency assertions. In-process execution "
        "is not a sandbox; do not submit untrusted code."
    ),
    version="0.3.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def security_headers(request, call_next):
    """Set conservative browser-facing headers for API and Swagger responses."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
    return response


class TaskRequest(BaseModel):
    task: str = Field(min_length=1, max_length=1000)


class OpenRouterEvaluationRequest(BaseModel):
    include_traces: bool = True
    timeout_seconds: float = Field(default=30, gt=0, le=60)


class CaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(min_length=1, max_length=100)
    input: Any
    expected_output: Any | None = None
    contains: list[str] = Field(default_factory=list, max_length=20)
    not_contains: list[str] = Field(default_factory=list, max_length=20)
    max_latency_ms: float | None = Field(default=None, gt=0)
    tags: list[str] = Field(default_factory=list, max_length=20)


class IsolatedEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: Literal["demo", "openrouter"] = "demo"
    suite: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    cases: list[CaseRequest] = Field(min_length=1, max_length=MAX_CASES_PER_REQUEST)
    include_traces: bool = True
    timeout_seconds: float = Field(default=10, gt=0, le=min(MAX_TIMEOUT_SECONDS, 60))
    memory_limit_mb: int = Field(default=512, ge=64, le=2048)

    @model_validator(mode="after")
    def validate_case_ids(self):
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case_id values must be unique within a suite")
        for case in self.cases:
            if len(str(case.input)) > MAX_INPUT_CHARS:
                raise ValueError(f"input for case {case.case_id!r} exceeds {MAX_INPUT_CHARS} characters")
        return self


class ContainerEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: Literal["demo", "openrouter"] = "demo"
    suite: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    cases: list[CaseRequest] = Field(min_length=1, max_length=MAX_CASES_PER_REQUEST)
    include_traces: bool = True
    timeout_seconds: float = Field(default=15, gt=0, le=min(MAX_TIMEOUT_SECONDS, 120))
    memory_limit_mb: int = Field(default=512, ge=64, le=4096)
    cpu_limit: float = Field(default=1.0, gt=0, le=4)
    pids_limit: int = Field(default=64, ge=16, le=512)
    network_enabled: bool = False

    @model_validator(mode="after")
    def validate_case_ids_and_inputs(self):
        if self.network_enabled and self.agent_id != "openrouter":
            raise ValueError("network_enabled is permitted only for the registered OpenRouter adapter")
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case_id values must be unique within a suite")
        for case in self.cases:
            if len(str(case.input)) > MAX_INPUT_CHARS:
                raise ValueError(f"input for case {case.case_id!r} exceeds {MAX_INPUT_CHARS} characters")
        return self


class CustomEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suite: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    cases: list[CaseRequest] = Field(min_length=1, max_length=MAX_CASES_PER_REQUEST)
    include_traces: bool = True
    timeout_seconds: float = Field(default=30, gt=0, le=MAX_TIMEOUT_SECONDS)

    @model_validator(mode="after")
    def validate_case_ids(self):
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case_id values must be unique within a suite")
        for case in self.cases:
            text = str(case.input)
            if len(text) > MAX_INPUT_CHARS:
                raise ValueError(f"input for case {case.case_id!r} exceeds {MAX_INPUT_CHARS} characters")
        return self


class ConnectedEvaluationRequest(BaseModel):
    """Request-scoped BYOK or HTTP-agent evaluation; credentials are never stored."""
    model_config = ConfigDict(extra="forbid")
    target_type: Literal["model", "http_agent"]
    suite: Literal["quality", "security", "both"] = "both"
    provider: Literal["openai", "gemini", "openrouter", "openai_compatible"] = "openai"
    api_key: str | None = Field(default=None, max_length=4096)
    model: str | None = Field(default=None, max_length=200)
    base_url: str | None = Field(default=None, max_length=500)
    endpoint_url: str | None = Field(default=None, max_length=2000)
    auth_token: str | None = Field(default=None, max_length=4096)
    allow_private_agent_url: bool = False
    agent_input_field: Literal["input", "question"] = "input"
    agent_output_field: Literal["output", "response", "answer"] = "output"
    agent_auth_header: Literal["authorization", "x-api-key"] = "authorization"
    timeout_seconds: float = Field(default=20, gt=0, le=60)
    include_traces: bool = True
    cases: list[CaseRequest] = Field(default_factory=list, max_length=MAX_CASES_PER_REQUEST)

    @model_validator(mode="after")
    def validate_target(self):
        if self.target_type == "model":
            if not self.api_key or not self.model:
                raise ValueError("model targets require api_key and model")
            if self.provider == "openai_compatible" and not self.base_url:
                raise ValueError("openai_compatible targets require base_url")
        elif not self.endpoint_url:
            raise ValueError("http_agent targets require endpoint_url")
        if self.suite == "quality" and not self.cases:
            raise ValueError("quality suite requires caller-defined cases")
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("case_id values must be unique")
        for case in self.cases:
            if len(str(case.input)) > MAX_INPUT_CHARS:
                raise ValueError(f"input for case {case.case_id!r} exceeds {MAX_INPUT_CHARS} characters")
        return self


async def require_api_key(authorization: str | None = Header(default=None)) -> str:
    """Authenticate a bearer token and return its server-configured tenant identity."""
    import json
    configured: dict[str, str] = {}
    raw_map = os.getenv("COGNIS_API_KEYS_JSON", "").strip()
    if raw_map:
        try:
            parsed = json.loads(raw_map)
            if not isinstance(parsed, dict) or not all(
                isinstance(k, str) and k and isinstance(v, str) and v.strip()
                for k, v in parsed.items()
            ):
                raise ValueError("Expected a JSON object mapping API keys to tenant IDs")
            configured.update({k: v.strip() for k, v in parsed.items()})
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="API key tenant mapping is invalid") from exc
    legacy_key = os.getenv("COGNIS_API_KEY", "").strip()
    if legacy_key:
        configured.setdefault(legacy_key, os.getenv("COGNIS_TENANT_ID", "default").strip() or "default")
    if not configured:
        if COGNIS_ENV == "production":
            raise HTTPException(status_code=503, detail="API authentication is not configured")
        return "local"
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not supplied:
        raise HTTPException(status_code=401, detail="Valid bearer token required")
    matched_tenant = None
    for token, candidate_tenant in configured.items():
        if secrets.compare_digest(supplied, token):
            matched_tenant = candidate_tenant
    if matched_tenant is None:
        raise HTTPException(status_code=401, detail="Valid bearer token required")
    return matched_tenant

@app.get("/health/live", tags=["health"])
def liveness():
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
def readiness():
    """Report ready only when the configured persistence backend responds."""
    try:
        check_store()
    except Exception as exc:
        logger.warning("Readiness check failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Persistence backend is not ready") from exc
    return {"status": "ready"}


@app.get("/health", tags=["health"], include_in_schema=False)
def health_check():
    return {"status": "ok"}


@app.post("/tasks", tags=["tasks"])
def create_task(request: TaskRequest, tenant_id: str = Depends(require_api_key)):
    return create_task_service(request.task)


@app.post("/evaluations", response_model=EvaluationResponse, tags=["evaluations"])
def create_evaluation(request: EvaluationRequest, tenant_id: str = Depends(require_api_key)):
    try:
        return persist_evaluation(run_demo_evaluation(include_traces=request.include_traces), tenant_id)
    except Exception as exc:
        logger.exception("Demo evaluation execution failed")
        raise HTTPException(status_code=500, detail="Evaluation execution failed") from exc


@app.post("/evaluations/custom", response_model=EvaluationResponse, tags=["evaluations"])
async def create_custom_evaluation(request: CustomEvaluationRequest, tenant_id: str = Depends(require_api_key)):
    """Evaluate a configured agent against caller-defined test cases.

    The current HTTP endpoint evaluates the configured OpenRouter model. Arbitrary
    Python objects and external agent frameworks must be integrated as trusted
    adapters in-process; this endpoint does not execute uploaded code.
    """
    try:
        agent = OpenRouterAgent()
    except OpenRouterConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    scenario = EvaluationScenario(
        name=request.suite,
        description="Caller-defined evaluation suite",
        cases=tuple(EvaluationCase(
            case_id=case.case_id,
            input=case.input,
            expected_output=case.expected_output,
            contains=tuple(case.contains),
            not_contains=tuple(case.not_contains),
            max_latency_ms=case.max_latency_ms,
            tags=tuple(case.tags),
        ) for case in request.cases),
    )
    try:
        # Each invocation has its own timeout; case count and input size are bounded.
        from app.engine.evaluator import run_evaluation_async
        result = await run_evaluation_async(
            agent, scenario, include_traces=request.include_traces,
            timeout_seconds=request.timeout_seconds,
        )
        return persist_evaluation(result, tenant_id)
    except Exception as exc:
        logger.exception("Custom evaluation failed")
        raise HTTPException(status_code=500, detail="Custom evaluation failed") from exc


@app.post(
    "/evaluations/isolated",
    response_model=EvaluationResponse,
    tags=["evaluations"],
    summary="Evaluate a registered agent in a child process",
)
async def create_isolated_evaluation(request: IsolatedEvaluationRequest, tenant_id: str = Depends(require_api_key)):
    """Run only a built-in registered adapter in a fresh subprocess per case.

    This is stronger fault containment than in-process invocation, but is not a
    hostile-code sandbox: OS network/filesystem restrictions are not enforced.
    """
    from app.engine.evaluator import run_evaluation_async

    scenario = EvaluationScenario(
        name=request.suite,
        description="Evaluation via a registered subprocess worker",
        cases=tuple(EvaluationCase(
            case_id=case.case_id,
            input=case.input,
            expected_output=case.expected_output,
            contains=tuple(case.contains),
            not_contains=tuple(case.not_contains),
            max_latency_ms=case.max_latency_ms,
            tags=tuple(case.tags),
        ) for case in request.cases),
    )

    class RegisteredWorker:
        def run(self, input_data):
            try:
                output, _worker_duration_ms = run_isolated_agent(
                    request.agent_id,
                    input_data,
                    IsolationPolicy(
                        timeout_seconds=request.timeout_seconds,
                        memory_limit_mb=request.memory_limit_mb,
                    ),
                )
                return output
            except IsolatedWorkerError as exc:
                raise AgentExecutionError(str(exc)) from exc

    try:
        result = await run_evaluation_async(
            RegisteredWorker(), scenario,
            include_traces=request.include_traces,
            timeout_seconds=request.timeout_seconds + 3,
        )
        return persist_evaluation(result, tenant_id)
    except Exception as exc:
        logger.exception("Isolated evaluation failed")
        raise HTTPException(status_code=502, detail="Isolated evaluation failed") from exc


@app.post(
    "/evaluations/container",
    response_model=EvaluationResponse,
    tags=["evaluations"],
    summary="Evaluate a registered agent in a disposable Docker container",
)
async def create_container_evaluation(request: ContainerEvaluationRequest, tenant_id: str = Depends(require_api_key)):
    """Run each case in a disposable, resource-limited Docker container.

    Docker daemon access is highly privileged. Keep this API private and connect
    it only to a dedicated worker daemon/host for production deployments.
    """
    from app.engine.evaluator import run_evaluation_async

    scenario = EvaluationScenario(
        name=request.suite,
        description="Evaluation via a disposable Docker worker",
        cases=tuple(EvaluationCase(
            case_id=case.case_id,
            input=case.input,
            expected_output=case.expected_output,
            contains=tuple(case.contains),
            not_contains=tuple(case.not_contains),
            max_latency_ms=case.max_latency_ms,
            tags=tuple(case.tags),
        ) for case in request.cases),
    )

    class ContainerRegisteredWorker:
        def run(self, input_data):
            try:
                output, _worker_duration_ms = run_container_agent(
                    request.agent_id,
                    input_data,
                    ContainerPolicy(
                        timeout_seconds=request.timeout_seconds,
                        memory_limit_mb=request.memory_limit_mb,
                        cpu_limit=request.cpu_limit,
                        pids_limit=request.pids_limit,
                        network_enabled=request.network_enabled,
                        image=os.getenv("COGNIS_CONTAINER_WORKER_IMAGE", "cognis-agent-worker:latest"),
                    ),
                )
                return output
            except ContainerWorkerError as exc:
                raise AgentExecutionError(str(exc)) from exc

    try:
        result = await run_evaluation_async(
            ContainerRegisteredWorker(),
            scenario,
            include_traces=request.include_traces,
            timeout_seconds=request.timeout_seconds + 10,
        )
        return persist_evaluation(result, tenant_id)
    except Exception as exc:
        logger.exception("Container evaluation failed")
        raise HTTPException(status_code=502, detail="Container evaluation failed") from exc


@app.post(
    "/evaluations/openrouter",
    response_model=EvaluationResponse,
    tags=["evaluations"],
    summary="Run a live OpenRouter connectivity smoke test",
)
def create_openrouter_evaluation(request: OpenRouterEvaluationRequest, tenant_id: str = Depends(require_api_key)):
    try:
        agent = OpenRouterAgent()
    except OpenRouterConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        return persist_evaluation(run_evaluation(agent, OPENROUTER_SMOKE_SCENARIO, include_traces=request.include_traces), tenant_id)
    except Exception as exc:
        logger.exception("OpenRouter evaluation failed")
        raise HTTPException(status_code=502, detail="OpenRouter evaluation failed") from exc



@app.get(
    "/evaluations/history",
    tags=["evaluations"],
    summary="List persisted evaluation runs",
)
def evaluation_history(limit: int = 20, offset: int = 0, tenant_id: str = Depends(require_api_key)):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=422, detail="limit must be 1..100 and offset must be non-negative")
    return list_evaluations(limit=limit, offset=offset, tenant_id=tenant_id)


@app.get(
    "/evaluations/history/{evaluation_id}",
    tags=["evaluations"],
    summary="Retrieve a persisted evaluation run",
)
def evaluation_history_detail(evaluation_id: str, tenant_id: str = Depends(require_api_key)):
    record = get_evaluation(evaluation_id, tenant_id=tenant_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return record


@app.post("/evaluations/connected", response_model=EvaluationResponse, tags=["evaluations"],
          summary="Evaluate a user-supplied model API or existing HTTP agent")
async def create_connected_evaluation(request: ConnectedEvaluationRequest, tenant_id: str = Depends(require_api_key)):
    """Run request-scoped BYOK/HTTP targets. Provider credentials are not persisted."""
    from app.engine.evaluator import DEMO_SCENARIO, run_evaluation_async
    from app.engine.security_suite import security_scenario
    from app.targets.http_agent import AgentEndpointError, HTTPAgentTarget
    from app.targets.openai_compatible import OpenAICompatibleTarget, PROVIDER_PRESETS, TargetConfigurationError

    try:
        if request.target_type == "model":
            base_url = request.base_url or PROVIDER_PRESETS[request.provider]
            target = OpenAICompatibleTarget(
                api_key=request.api_key or "", model=request.model or "", base_url=base_url,
                timeout_seconds=request.timeout_seconds,
            )
        else:
            # Private/loopback access is disabled unless explicitly enabled by the server.
            server_allows_private = os.getenv("COGNIS_ALLOW_PRIVATE_AGENT_URLS", "false").lower() == "true"
            if request.allow_private_agent_url and not server_allows_private:
                raise HTTPException(status_code=403, detail="Server policy does not allow private agent URLs.")
            target = HTTPAgentTarget(
                endpoint_url=request.endpoint_url or "", auth_token=request.auth_token,
                timeout_seconds=request.timeout_seconds,
                allow_private=server_allows_private and request.allow_private_agent_url,
                input_field=request.agent_input_field,
                output_field=request.agent_output_field,
                auth_header=request.agent_auth_header,
            )
    except (TargetConfigurationError, AgentEndpointError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    scenarios = []
    if request.suite in ("quality", "both"):
        if request.cases:
            scenarios.append(EvaluationScenario(
                name="connected_quality",
                description="User-defined quality checks",
                cases=tuple(EvaluationCase(
                    case_id=case.case_id, input=case.input, expected_output=case.expected_output,
                    contains=tuple(case.contains), not_contains=tuple(case.not_contains),
                    max_latency_ms=case.max_latency_ms, tags=tuple(case.tags) or ("quality",),
                ) for case in request.cases),
            ))
        elif request.suite == "both":
            scenarios.append(DEMO_SCENARIO)
        else:
            raise HTTPException(status_code=422, detail="Provide at least one custom case for quality evaluation.")
    if request.suite in ("security", "both"):
        scenarios.append(security_scenario())

    # One report contains every selected case, so the caller gets a single run ID.
    combined = EvaluationScenario(
        name=f"connected_{request.suite}",
        description="Combined connected-target evaluation",
        cases=tuple(case for scenario in scenarios for case in scenario.cases),
    )
    try:
        result = await run_evaluation_async(
            target, combined, include_traces=request.include_traces,
            timeout_seconds=request.timeout_seconds,
        )
        return persist_evaluation(result, tenant_id)
    except HTTPException:
        raise
    except Exception as exc:
        # Do not log request models or provider credentials.
        logger.warning("Connected evaluation failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Connected evaluation failed; verify target configuration and retry.") from exc


_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    """Serve the browser-based evaluation console."""
    return HTMLResponse((_STATIC_DIR / "dashboard.html").read_text(encoding="utf-8"))


@app.get("/", include_in_schema=False)
def root():
    return JSONResponse({"service": "Cognis", "docs": "/docs", "health": "/health/ready"})
