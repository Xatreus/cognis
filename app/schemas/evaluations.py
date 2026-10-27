from typing import Literal
from pydantic import BaseModel

class EvaluationRequest(BaseModel):
    suite: Literal['demo'] = 'demo'
    include_traces: bool = True

class CaseResult(BaseModel):
    case_id: str
    passed: bool
    expected: str
    actual: str
    duration_ms: float
    error: str | None = None

class EvaluationResponse(BaseModel):
    evaluation_id: str
    suite: str
    status: Literal['passed', 'failed']
    total: int
    passed: int
    failed: int
    pass_rate: float
    results: list[CaseResult]
