from typing import Any, Literal
from pydantic import BaseModel, Field


class EvaluationRequest(BaseModel):
    suite: Literal["demo"] = "demo"
    include_traces: bool = True


class AssertionResultSchema(BaseModel):
    name: str
    passed: bool
    message: str


class CaseResult(BaseModel):
    case_id: str
    passed: bool
    expected: str
    actual: str
    duration_ms: float = Field(ge=0)
    error: str | None = None
    assertions: list[AssertionResultSchema] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class EvaluationMetrics(BaseModel):
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    latency_mean_ms: float | None = None
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    latency_max_ms: float | None = None


class EvaluationResponse(BaseModel):
    evaluation_id: str
    suite: str
    status: Literal["passed", "failed"]
    total: int
    passed: int
    failed: int
    pass_rate: float
    results: list[CaseResult]
    metrics: EvaluationMetrics | None = None
