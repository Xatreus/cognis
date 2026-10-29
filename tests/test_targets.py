import asyncio

import httpx
import pytest

from app.targets.http_agent import AgentEndpointError, HTTPAgentTarget, validate_agent_url
from app.targets.openai_compatible import OpenAICompatibleTarget, TargetConfigurationError


@pytest.mark.parametrize("url", ["http://example.com/agent", "https://127.0.0.1/agent", "https://localhost/agent"])
def test_provider_requires_https_and_public_provider_host(url):
    with pytest.raises(TargetConfigurationError):
        OpenAICompatibleTarget(api_key="fake", model="test", base_url=url)


def test_http_agent_blocks_plain_http_and_private_addresses_by_default():
    with pytest.raises(AgentEndpointError):
        validate_agent_url("http://example.com/agent")
    with pytest.raises(AgentEndpointError):
        validate_agent_url("https://127.0.0.1/agent")


def test_http_agent_allows_localhost_only_when_explicitly_enabled():
    assert validate_agent_url("http://127.0.0.1:9000/agent", allow_private=True) == "http://127.0.0.1:9000/agent"


def test_openai_compatible_adapter_sends_byok_key_and_parses_output():
    async def scenario():
        seen = {}
        async def handler(request):
            seen["authorization"] = request.headers["authorization"]
            seen["body"] = await request.aread()
            return httpx.Response(200, json={"choices":[{"message":{"content":"  hello  "}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            target = OpenAICompatibleTarget(api_key="test-secret", model="test-model",
                base_url="https://api.example.com/v1", client=client)
            assert await target.ainvoke("hi") == "hello"
        assert seen["authorization"] == "Bearer test-secret"
        assert b"test-secret" not in seen["body"]
    asyncio.run(scenario())


def test_http_agent_contract_and_auth_header():
    async def scenario():
        seen = {}
        async def handler(request):
            seen["authorization"] = request.headers["authorization"]
            seen["payload"] = await request.aread()
            return httpx.Response(200, json={"output":"hello"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            target = HTTPAgentTarget(endpoint_url="https://agent.example.com/run", auth_token="agent-secret", client=client)
            assert await target.ainvoke("hi") == "hello"
        assert seen["authorization"] == "Bearer agent-secret"
        assert b"agent-secret" not in seen["payload"]
    asyncio.run(scenario())
