"""Subprocess boundary for registered Cognis agent adapters.

This gives process-level fault containment and hard timeouts, not a hostile-code
sandbox. It does not block network access or guarantee filesystem isolation.
Untrusted third-party code requires a disposable container/VM with restricted
network, read-only filesystem, non-root UID, seccomp/AppArmor, and cgroup limits.
"""
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from app.engine.worker_protocol import WorkerRequest, WorkerResponse

@dataclass(frozen=True)
class IsolationPolicy:
    timeout_seconds: float = 30.0
    memory_limit_mb: int = 512
    network_enabled: bool = False
    filesystem_read_only: bool = True
    max_output_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        if not 0 < self.timeout_seconds <= 300:
            raise ValueError("timeout_seconds must be in (0, 300]")
        if self.memory_limit_mb < 64:
            raise ValueError("memory_limit_mb must be at least 64")
        if self.max_output_bytes < 1024:
            raise ValueError("max_output_bytes must be at least 1024")

class IsolatedWorkerError(RuntimeError):
    """A worker failed, timed out, or violated the worker protocol."""

def _worker_environment() -> dict[str, str]:
    # Explicit allowlist; unrelated parent-process secrets are not inherited.
    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR",
               "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "OPENROUTER_BASE_URL",
               "PYTHONPATH")
    return {key: os.environ[key] for key in allowed if key in os.environ}

def _posix_resource_limits(memory_limit_mb: int):
    def apply_limits():
        import resource
        limit = memory_limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    return apply_limits

def run_isolated_agent(agent_id: str, input_data: Any,
                       policy: IsolationPolicy | None = None) -> tuple[str, float]:
    """Run a registered adapter in a child process; return normalized output and ms.

    network_enabled/filesystem_read_only are documented policy intent only for this
    backend; the operating system does not enforce those settings here.
    """
    policy = policy or IsolationPolicy()
    request = WorkerRequest(agent_id=agent_id, input=input_data)
    root = Path(__file__).resolve().parents[2]
    kwargs: dict[str, Any] = {
        "args": [sys.executable, "-m", "app.engine.worker_entry"],
        "input": request.model_dump_json(),
        "text": True,
        "capture_output": True,
        "cwd": str(root),
        "env": _worker_environment(),
        "timeout": policy.timeout_seconds,
        "check": False,
    }
    if os.name == "posix":
        kwargs["preexec_fn"] = _posix_resource_limits(policy.memory_limit_mb)
        kwargs["start_new_session"] = True
    elif os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    started = time.perf_counter()
    try:
        completed = subprocess.run(**kwargs)
    except subprocess.TimeoutExpired as exc:
        raise IsolatedWorkerError(
            f"Worker exceeded {policy.timeout_seconds:.3f}s timeout and was terminated"
        ) from exc
    except OSError as exc:
        raise IsolatedWorkerError(f"Could not start worker: {type(exc).__name__}") from exc

    elapsed_ms = (time.perf_counter() - started) * 1000
    stdout = completed.stdout or ""
    if len(stdout.encode("utf-8", errors="replace")) > policy.max_output_bytes:
        raise IsolatedWorkerError("Worker output exceeded configured size limit")
    try:
        response = WorkerResponse.model_validate_json(stdout)
    except Exception as exc:
        raise IsolatedWorkerError(
            f"Worker protocol failed (exit code {completed.returncode})"
        ) from exc
    if not response.ok:
        raise IsolatedWorkerError(
            f"Agent failed in worker ({response.error_code}): {response.error_message}"
        )
    return str(response.output or ""), elapsed_ms
