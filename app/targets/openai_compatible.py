"""BYOK adapter for OpenAI-compatible chat-completions APIs.

Supports OpenAI-compatible providers, including Gemini's compatibility endpoint,
OpenRouter, and many self-hosted gateways. Credentials are request-scoped and are
never persisted by this module.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse
from typing import Any

import httpx

from app.targets.http_utils import post_json_bounded
from app.security.egress import EgressProxyConfigurationError, validate_egress_proxy_url


class TargetConfigurationError(ValueError):
    pass


def validate_provider_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise TargetConfigurationError("Provider base_url must be an HTTPS URL without embedded credentials.")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise TargetConfigurationError("Provider base_url must not point to localhost.")
    try:
        try:
            addresses = {ipaddress.ip_address(host)}
        except ValueError:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
            }
    except (OSError, ValueError) as exc:
        raise TargetConfigurationError("Provider hostname could not be resolved safely.") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise TargetConfigurationError("Provider base_url must resolve only to public IP addresses.")
    return value.rstrip("/")


class OpenAICompatibleTarget:
    """Minimal async target returning the assistant's text content."""

    def __init__(self, *, api_key: str, model: str, base_url: str, timeout_seconds: float = 30.0,
                 client: httpx.AsyncClient | None = None, proxy_url: str | None = None) -> None:
        if not api_key or len(api_key) > 4096:
            raise TargetConfigurationError("A valid provider API key is required.")
        if not model or len(model) > 200:
            raise TargetConfigurationError("A valid model identifier is required.")
        self.base_url = validate_provider_base_url(base_url)
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        try:
            self.proxy_url = validate_egress_proxy_url(proxy_url) if proxy_url else None
        except EgressProxyConfigurationError as exc:
            raise TargetConfigurationError(str(exc)) from exc
        self.client = client

    async def ainvoke(self, input_data: Any) -> str:
        prompt = input_data if isinstance(input_data, str) else str(input_data)
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            endpoint = self.base_url + "/chat/completions"
            if self.client:
                data = await post_json_bounded(
                    self.client, endpoint, json_body=payload, headers=headers,
                    timeout_seconds=self.timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False, proxy=self.proxy_url) as client:
                    data = await post_json_bounded(
                        client, endpoint, json_body=payload, headers=headers,
                        timeout_seconds=self.timeout_seconds,
                    )
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("Provider response content was not text.")
            return content.strip()
        except httpx.TimeoutException as exc:
            raise RuntimeError("Provider request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Provider returned HTTP {exc.response.status_code}.") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("Provider request failed.") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("Provider returned an invalid chat-completions response.") from exc


PROVIDER_PRESETS = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "openrouter": "https://openrouter.ai/api/v1",
}
