"""Typed, provider-neutral test-case and scenario definitions."""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvaluationCase:
    """One input/output contract for an agent under test."""

    case_id: str
    input: Any
    expected_output: Any | None = None
    contains: tuple[str, ...] = ()
    not_contains: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be empty")


@dataclass(frozen=True)
class EvaluationScenario:
    """A named, repeatable collection of agent evaluation cases."""

    name: str
    cases: tuple[EvaluationCase, ...]
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("scenario name must not be empty")
        if not self.cases:
            raise ValueError("scenario must contain at least one case")
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case_id values must be unique within a scenario")
