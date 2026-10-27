"""Versioned JSON protocol shared by Cognis and isolated worker processes."""
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

class WorkerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: int = 1
    agent_id: str = Field(min_length=1, max_length=100)
    input: Any

class WorkerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: int = 1
    ok: bool
    output: Any = None
    error_code: str | None = None
    error_message: str | None = None
