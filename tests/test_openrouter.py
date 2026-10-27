import asyncio
import json

import httpx
import pytest

from app.agents.openrouter import (
    OPENROUTER_ENDPOINT,
    OpenRouterAgent,
    OpenRouterConfigurationError,
)


def test_openrouter_adapter_sends_expected_request_and_parses_response():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": " COGNIS_OK\n"}}]},
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            agent = OpenRouterAgent(
                api_key="test-key",
                model="test/provider-model",
                client=client,
            )
            return await agent.ainvoke("Reply COGNIS_OK")

    assert asyncio.run(run()) == "COGNIS_OK"
    assert captured["url"] == OPENROUTER_ENDPOINT
    assert captured["authorization"] == "Bearer test-key"
    assert captured["payload"]["model"] == "test/provider-model"
    assert captured["payload"]["messages"][0]["content"] == "Reply COGNIS_OK"


def test_openrouter_requires_key_and_model(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    with pytest.raises(OpenRouterConfigurationError, match="OPENROUTER_API_KEY"):
        OpenRouterAgent()


def test_openrouter_rejects_provider_http_error_without_exposing_body():
    def handler(_request):
        return httpx.Response(401, json={"error": {"message": "sensitive provider detail"}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            agent = OpenRouterAgent(api_key="test-key", model="test/model", client=client)
            return await agent.ainvoke("hello")

    with pytest.raises(RuntimeError, match="HTTP 401") as error:
        asyncio.run(run())
    assert "sensitive provider detail" not in str(error.value)
