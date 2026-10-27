"""Docker Engine-backed worker isolation for registered Cognis adapters.

Security defaults: no network, read-only root filesystem, non-root UID, no
capabilities, no-new-privileges, bounded memory/CPU/PIDs, ephemeral /tmp, and
no host mounts. This is a meaningful container boundary, but not a complete
multi-tenant security guarantee. Use a dedicated Docker worker host/daemon and
keep its socket inaccessible to public clients.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from app.engine.worker_protocol import WorkerRequest, WorkerResponse

logger = logging.getLogger(__name__)


class ContainerWorkerError(RuntimeError):
    """Container startup, execution, timeout, or protocol failure."""


@dataclass(frozen=True)
class ContainerPolicy:
    timeout_seconds: float = 30.0
    memory_limit_mb: int = 512
    cpu_limit: float = 1.0
    pids_limit: int = 64
    network_enabled: bool = False
    max_output_bytes: int = 1_000_000
    image: str = "cognis-agent-worker:latest"

    def __post_init__(self) -> None:
        if not 0 < self.timeout_seconds <= 300:
            raise ValueError("timeout_seconds must be in (0, 300]")
        if not 64 <= self.memory_limit_mb <= 4096:
            raise ValueError("memory_limit_mb must be between 64 and 4096")
        if not 0 < self.cpu_limit <= 4:
            raise ValueError("cpu_limit must be in (0, 4]")
        if not 16 <= self.pids_limit <= 512:
            raise ValueError("pids_limit must be between 16 and 512")
        if self.max_output_bytes < 1024:
            raise ValueError("max_output_bytes must be at least 1024")
        if not self.image or len(self.image) > 255:
            raise ValueError("image must be a non-empty image reference")


def _provider_environment(agent_id: str) -> dict[str, str]:
    """Only pass the explicitly needed provider variables to provider workers."""
    if agent_id != "openrouter":
        return {}
    allowed = ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "OPENROUTER_BASE_URL")
    return {name: os.environ[name] for name in allowed if os.environ.get(name)}


def run_container_agent(
    agent_id: str,
    input_data: Any,
    policy: ContainerPolicy | None = None,
) -> tuple[str, float]:
    """Run one registered agent in a disposable container and return output + ms."""
    policy = policy or ContainerPolicy()
    if agent_id not in {"demo", "openrouter"}:
        raise ContainerWorkerError("Unknown agent_id; only registered adapters can execute")
    if policy is not None and policy.network_enabled and agent_id != "openrouter":
        raise ContainerWorkerError("Network access is allowed only for the registered OpenRouter adapter")

    try:
        import docker
        from docker.errors import APIError, DockerException, ImageNotFound
    except ImportError as exc:
        raise ContainerWorkerError(
            "Docker SDK is not installed; install requirements and rebuild the API image"
        ) from exc

    request = WorkerRequest(agent_id=agent_id, input=input_data)
    payload = request.model_dump_json().encode("utf-8")
    if len(payload) > policy.max_output_bytes:
        raise ContainerWorkerError("Worker request exceeded configured size limit")
    client = None
    container = None
    started = time.perf_counter()
    try:
        client = docker.from_env(timeout=max(5, int(policy.timeout_seconds) + 10))
        try:
            client.images.get(policy.image)
        except ImageNotFound as exc:
            raise ContainerWorkerError(
                f"Worker image '{policy.image}' is missing; build it with Dockerfile.worker first"
            ) from exc

        # No bind mounts or request files are needed: send the JSON over the
        # container's stdin. This works with a read-only root filesystem because
        # Docker's archive API rejects writes when the rootfs is read-only.
        container = client.containers.create(
            image=policy.image,
            command=["python", "-m", "app.engine.worker_entry"],
            stdin_open=True,
            tty=False,
            detach=True,
            network_mode="bridge" if policy.network_enabled else "none",
            read_only=True,
            user="65532:65532",
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            mem_limit=f"{policy.memory_limit_mb}m",
            nano_cpus=int(policy.cpu_limit * 1_000_000_000),
            pids_limit=policy.pids_limit,
            ipc_mode="private",
            tmpfs={"/tmp": f"rw,noexec,nosuid,nodev,size={min(policy.max_output_bytes * 2, 8_000_000)}"},
            environment=_provider_environment(agent_id),
            labels={"com.cognis.managed-worker": "true"},
        )
        operation = "start container"
        container.start()
        operation = "send request over worker stdin"
        stdin_socket = container.attach_socket(params={"stdin": 1, "stream": 1})
        try:
            stdin_socket._sock.sendall(payload + b"\\n")
        finally:
            stdin_socket.close()
        operation = "wait for worker"
        result = container.wait(timeout=policy.timeout_seconds)
        status_code = result.get("StatusCode", 1)
        logs = container.logs(stdout=True, stderr=False)
        if len(logs) > policy.max_output_bytes:
            raise ContainerWorkerError("Worker output exceeded configured size limit")
        try:
            response = WorkerResponse.model_validate_json(logs.decode("utf-8").strip())
        except Exception as exc:
            raise ContainerWorkerError(
                f"Worker protocol failed (container exit code {status_code})"
            ) from exc
        if status_code != 0 or not response.ok:
            # Avoid including full provider exception payloads in the public API.
            code = response.error_code or "ContainerExit"
            message = (response.error_message or "Worker exited unsuccessfully")[:300]
            raise ContainerWorkerError(f"Agent failed in container ({code}): {message}")
        return str(response.output or ""), (time.perf_counter() - started) * 1000
    except ContainerWorkerError:
        raise
    except Exception as exc:
        # Detailed diagnostics stay in server logs, not in the public response.
        logger.exception(
            "Container worker operation failed: operation=%s exception=%s docker_status=%s",
            locals().get("operation", "initialize Docker client"),
            type(exc).__name__,
            getattr(exc, "status_code", None),
        )
        raise ContainerWorkerError(f"Container worker failed ({type(exc).__name__})") from exc
    finally:
        if container is not None:
            try:
                container.remove(force=True, v=True)
            except Exception:
                pass
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
