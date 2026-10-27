"""Isolation policy boundary.

The current in-process runner is intended for trusted agents only. Python threads
and asyncio timeouts are not a security sandbox. Untrusted user-supplied agents
must eventually run in disposable, resource-limited worker processes/containers
with restricted filesystem, network, credentials, and execution time.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IsolationPolicy:
    """Configuration contract for a future isolated worker implementation."""

    timeout_seconds: float = 30.0
    memory_limit_mb: int = 512
    network_enabled: bool = False
    filesystem_read_only: bool = True

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if self.memory_limit_mb < 64:
            raise ValueError("memory_limit_mb must be at least 64")
