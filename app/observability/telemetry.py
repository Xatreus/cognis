"""Dependency-free aggregate metrics for evaluation runs."""
from math import ceil
from statistics import mean
from typing import Iterable


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 3)


def summarize_run(durations_ms: Iterable[float], passed: int, total: int) -> dict[str, float | int | None]:
    """Return stable latency and reliability metrics for one evaluation run."""
    durations = [max(0.0, float(value)) for value in durations_ms]
    failed = max(0, total - passed)
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "latency_mean_ms": round(mean(durations), 3) if durations else None,
        "latency_p50_ms": _percentile(durations, 0.50),
        "latency_p95_ms": _percentile(durations, 0.95),
        "latency_max_ms": round(max(durations), 3) if durations else None,
    }
