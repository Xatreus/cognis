"""Adapter for an existing JSON-over-HTTP agent endpoint."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse
from typing import Any

import httpx

from app.agents.protocol import AgentExecution

from app.targets.http_utils import post_json_bounded
from app.security.egress import EgressProxyConfigurationError, validate_egress_proxy_url


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
                 client: httpx.AsyncClient | None = None,
                 proxy_url: str | None = None) -> None:
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
        try:
            self.proxy_url = validate_egress_proxy_url(proxy_url) if proxy_url else None
        except EgressProxyConfigurationError as exc:
            raise AgentEndpointError(str(exc)) from exc
        self.client = client

    async def ainvoke(self, input_data: Any) -> str | AgentExecution:
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
                data = await post_json_bounded(
                    self.client, self.endpoint_url, json_body=payload, headers=headers,
                    timeout_seconds=self.timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False, proxy=self.proxy_url) as client:
                    data = await post_json_bounded(
                        client, self.endpoint_url, json_body=payload, headers=headers,
                        timeout_seconds=self.timeout_seconds,
                    )
            output = data.get(self.output_field) if isinstance(data, dict) else None
            if not isinstance(output, str):
                raise RuntimeError("Agent response must be JSON with a string 'output' or 'response' field.")
            has_tool_calls = isinstance(data, dict) and "tool_calls" in data
            has_trace = isinstance(data, dict) and "trace" in data
            if not has_tool_calls and not has_trace:
                return output
            raw_calls = data.get("tool_calls", [])
            if not isinstance(raw_calls, list) or any(not isinstance(call, dict) for call in raw_calls):
                raise RuntimeError("Agent tool_calls must be a JSON array of objects.")
            if len(raw_calls) > 100:
                raise RuntimeError("Agent returned more than 100 tool calls; refusing to truncate policy evidence.")
            raw_trace = data.get("trace", {})
            if not isinstance(raw_trace, dict):
                raise RuntimeError("Agent trace must be a JSON object.")
            return AgentExecution(
                output=output,
                tool_calls=tuple(raw_calls),
                trace=raw_trace,
                tool_call_evidence_available=has_tool_calls,
            )
        except httpx.TimeoutException as exc:
            raise RuntimeError("Agent endpoint timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Agent endpoint returned HTTP {exc.response.status_code}.") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("Agent endpoint request failed.") from exc
        except (ValueError, TypeError) as exc:
            raise RuntimeError("Agent endpoint returned invalid JSON.") from exc
