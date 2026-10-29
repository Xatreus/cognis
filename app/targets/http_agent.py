"""Adapter for an existing JSON-over-HTTP agent endpoint."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse
from typing import Any

import httpx


class AgentEndpointError(ValueError):
    pass


def validate_agent_url(url: str, *, allow_private: bool = False) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ({"http", "https"} if allow_private else {"https"}):
        raise AgentEndpointError("Agent URL must use HTTPS (HTTP is allowed only for explicitly enabled local development).")
    if not parsed.hostname or parsed.username or parsed.password:
        raise AgentEndpointError("Agent URL must include a hostname and must not embed credentials.")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".localhost"):
        if not allow_private:
            raise AgentEndpointError("Local/private agent URLs are disabled by server policy.")
        return url.rstrip("/")
    try:
        addresses = {ipaddress.ip_address(host)} if _is_ip(host) else {
            ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        }
    except (OSError, ValueError) as exc:
        raise AgentEndpointError("Could not resolve agent hostname safely.") from exc
    if not addresses:
        raise AgentEndpointError("Agent hostname did not resolve.")
    if not allow_private and any(not address.is_global for address in addresses):
        raise AgentEndpointError("Agent URL resolves to a non-public IP address; private targets are blocked.")
    return url.rstrip("/")


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


class HTTPAgentTarget:
    """POSTs {input, metadata} and reads a string output from JSON response."""
    def __init__(self, *, endpoint_url: str, auth_token: str | None = None,
                 timeout_seconds: float = 15.0, allow_private: bool = False,
                 input_field: str = "input", output_field: str = "output",
                 auth_header: str = "authorization",
                 client: httpx.AsyncClient | None = None) -> None:
        if input_field not in {"input", "question"}:
            raise AgentEndpointError("input_field must be 'input' or 'question'.")
        if output_field not in {"output", "response", "answer"}:
            raise AgentEndpointError("output_field must be 'output', 'response', or 'answer'.")
        if auth_header not in {"authorization", "x-api-key"}:
            raise AgentEndpointError("auth_header must be 'authorization' or 'x-api-key'.")
        self.endpoint_url = validate_agent_url(endpoint_url, allow_private=allow_private)
        self.auth_token = auth_token
        self.timeout_seconds = timeout_seconds
        self.input_field = input_field
        self.output_field = output_field
        self.auth_header = auth_header
        self.client = client

    async def ainvoke(self, input_data: Any) -> str:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["X-API-Key" if self.auth_header == "x-api-key" else "Authorization"] = (
                self.auth_token if self.auth_header == "x-api-key" else f"Bearer {self.auth_token}"
            )
        payload = {self.input_field: input_data}
        if self.input_field == "input":
            payload["metadata"] = {"source": "cognis"}
        try:
            if self.client:
                response = await self.client.post(self.endpoint_url, json=payload, headers=headers,
                                                  timeout=self.timeout_seconds, follow_redirects=False)
                response.raise_for_status()
                data = response.json()
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False) as client:
                    response = await client.post(self.endpoint_url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
            output = data.get(self.output_field) if isinstance(data, dict) else None
            if not isinstance(output, str):
                raise RuntimeError("Agent response must be JSON with a string 'output' or 'response' field.")
            return output
        except httpx.TimeoutException as exc:
            raise RuntimeError("Agent endpoint timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Agent endpoint returned HTTP {exc.response.status_code}.") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("Agent endpoint request failed.") from exc
        except (ValueError, TypeError) as exc:
            raise RuntimeError("Agent endpoint returned invalid JSON.") from exc
