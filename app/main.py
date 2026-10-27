"""Cognis HTTP API.

Do not expose this service publicly without authentication, durable storage,
tenant isolation, quotas, and isolated workers for untrusted target agents.
"""
import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

load_dotenv()

from app.agents.openrouter import OpenRouterAgent, OpenRouterConfigurationError
from app.engine.evaluator import run_demo_evaluation, run_evaluation
from app.engine.provider_scenarios import OPENROUTER_SMOKE_SCENARIO
from app.engine.isolation import IsolatedWorkerError, IsolationPolicy, run_isolated_agent
from app.engine.scenarios import EvaluationCase, EvaluationScenario
from app.observability.logging import configure_logging
from app.schemas.evaluations import EvaluationRequest, EvaluationResponse
from app.services.task_service import create_task as create_task_service

configure_logging()
logger = logging.getLogger(__name__)

MAX_CASES_PER_REQUEST = int(os.getenv("COGNIS_MAX_CASES_PER_REQUEST", "50"))
MAX_INPUT_CHARS = int(os.getenv("COGNIS_MAX_INPUT_CHARS", "12000"))
MAX_TIMEOUT_SECONDS = float(os.getenv("COGNIS_MAX_TIMEOUT_SECONDS", "60"))
API_KEY = os.getenv("COGNIS_API_KEY", "").strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Cognis API starting")
    yield
    logger.info("Cognis API stopping")


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


async def require_api_key(authorization: str | None = Header(default=None)):
    """Optional bearer-token gate. Configure COGNIS_API_KEY for deployments."""
    if not API_KEY:
        return
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(supplied, API_KEY):
        raise HTTPException(status_code=401, detail="Valid bearer token required")


@app.get("/health/live", tags=["health"])
def liveness():
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
def readiness():
    return {"status": "ready"}


@app.get("/health", tags=["health"], include_in_schema=False)
def health_check():
    return {"status": "ok"}


@app.post("/tasks", tags=["tasks"], dependencies=[Depends(require_api_key)])
def create_task(request: TaskRequest):
    return create_task_service(request.task)


@app.post("/evaluations", response_model=EvaluationResponse, tags=["evaluations"], dependencies=[Depends(require_api_key)])
def create_evaluation(request: EvaluationRequest):
    try:
        return run_demo_evaluation(include_traces=request.include_traces)
    except Exception as exc:
        logger.exception("Demo evaluation execution failed")
        raise HTTPException(status_code=500, detail="Evaluation execution failed") from exc


@app.post("/evaluations/custom", response_model=EvaluationResponse, tags=["evaluations"], dependencies=[Depends(require_api_key)])
async def create_custom_evaluation(request: CustomEvaluationRequest):
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
        return await run_evaluation_async(
            agent, scenario, include_traces=request.include_traces,
            timeout_seconds=request.timeout_seconds,
        )
    except Exception as exc:
        logger.exception("Custom evaluation failed")
        raise HTTPException(status_code=500, detail="Custom evaluation failed") from exc


@app.post(
    "/evaluations/openrouter",
    response_model=EvaluationResponse,
    tags=["evaluations"],
    summary="Run a live OpenRouter connectivity smoke test",
    dependencies=[Depends(require_api_key)],
)
def create_openrouter_evaluation(request: OpenRouterEvaluationRequest):
    try:
        agent = OpenRouterAgent()
    except OpenRouterConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        return run_evaluation(agent, OPENROUTER_SMOKE_SCENARIO, include_traces=request.include_traces)
    except Exception as exc:
        logger.exception("OpenRouter evaluation failed")
        raise HTTPException(status_code=502, detail="OpenRouter evaluation failed") from exc


@app.get("/", include_in_schema=False)
def root():
    return JSONResponse({"service": "Cognis", "docs": "/docs", "health": "/health/ready"})
