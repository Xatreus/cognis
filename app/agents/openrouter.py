"""Minimal OpenRouter chat-completions adapter for smoke-testing Cognis.

API credentials are read from the environment. Never log request headers or
provider response bodies because they may contain sensitive user content.
"""
import os
from typing import Any

import httpx


OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterConfigurationError(RuntimeError):
    """Raised when the provider cannot be configured safely."""


class OpenRouterAgent:
    """Small async agent adapter using OpenRouter's OpenAI-compatible endpoint."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model or os.getenv("OPENROUTER_MODEL")
        if not self.api_key:
            raise OpenRouterConfigurationError("OPENROUTER_API_KEY is not configured.")
        if not self.model:
            raise OpenRouterConfigurationError("OPENROUTER_MODEL is not configured.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def ainvoke(self, input_data: Any) -> str:
        prompt = input_data if isinstance(input_data, str) else str(input_data)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "Cognis Agent Evaluation",
        }

        try:
            if self._client is not None:
                response = await self._client.post(
                    OPENROUTER_ENDPOINT, headers=headers, json=payload,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        OPENROUTER_ENDPOINT, headers=headers, json=payload
                    )
                    response.raise_for_status()
                    data = response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError("OpenRouter request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            # Avoid returning provider response bodies, which may contain sensitive data.
            raise RuntimeError(
                f"OpenRouter returned HTTP {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("OpenRouter request failed.") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("OpenRouter returned an invalid chat-completions response.") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("OpenRouter response did not contain a message.") from exc
        if not isinstance(content, str):
            raise RuntimeError("OpenRouter returned non-text message content.")
        return content.strip()
