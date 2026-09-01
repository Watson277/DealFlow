import json
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError
from structlog.testing import capture_logs

from app.core.config import Settings
from app.llm.structured_chat import StructuredChatClient


class StructuredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str


async def test_timeout_is_retried_and_logged_without_sensitive_details(monkeypatch):
    def handle(request):
        raise httpx.ReadTimeout("PRIVATE-NETWORK-CONTEXT", request=request)

    monkeypatch.setattr("app.llm.structured_chat.asyncio.sleep", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http_client:
        sdk = AsyncOpenAI(api_key="test", http_client=http_client)
        chat = StructuredChatClient(Settings(_env_file=None, llm_max_retries=1), sdk)
        with capture_logs() as logs, pytest.raises(APITimeoutError):
            await chat.complete(
                instructions="", user_input="", output_model=StructuredOutput, max_tokens=10
            )
    assert [log["event"] for log in logs] == [
        "llm_request_started",
        "llm_request_retrying",
        "llm_request_started",
        "llm_request_failed",
    ]
    assert logs[-1]["cause_type"] == "ReadTimeout"
    assert "PRIVATE" not in json.dumps(logs)


@pytest.mark.asyncio
async def test_structured_chat_uses_chat_completions_and_validates_json() -> None:
    captured: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "glm-5.3-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"answer":"ok"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    openai_client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://example.test/v4/",
        http_client=http_client,
    )
    client = StructuredChatClient(
        Settings(llm_api_key=SecretStr("test-key"), llm_reasoning_effort="max"),
        client=openai_client,
    )

    result = await client.complete(
        instructions="Answer the question.",
        user_input="test",
        output_model=StructuredOutput,
        max_tokens=100,
    )
    await http_client.aclose()
    assert result == StructuredOutput(answer="ok")
    assert captured["path"] == "/v4/chat/completions"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "glm-5.3-flash"
    assert body["response_format"] == {"type": "json_object"}
    assert body["thinking"] == {"type": "enabled", "clear_thinking": False}
    assert body["reasoning_effort"] == "max"
    assert "JSON Schema" in body["messages"][0]["content"]


@pytest.mark.parametrize("status_code,attempts", [(429, 3), (503, 3), (401, 1)])
async def test_explicit_retry_limit_and_safe_failure_logs(monkeypatch, status_code, attempts):
    calls = 0

    def handle(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            status_code,
            headers={"x-request-id": "req-retry"},
            json={"error": {"message": "PRIVATE-PROVIDER-BODY", "type": "provider_error"}},
        )

    monkeypatch.setattr("app.llm.structured_chat.asyncio.sleep", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http_client:
        sdk = AsyncOpenAI(api_key="private-key", http_client=http_client)
        chat = StructuredChatClient(Settings(_env_file=None, llm_max_retries=2), sdk)
        with capture_logs() as logs, pytest.raises(APIStatusError):
            await chat.complete(
                instructions="PRIVATE-INSTRUCTIONS",
                user_input="PRIVATE-DOCUMENT",
                output_model=StructuredOutput,
                max_tokens=100,
                operation="generate_proposal",
                correlation_id="rfp-log-test",
            )
    assert calls == attempts
    assert logs[-1]["event"] == "llm_request_failed"
    assert logs[-1]["status_code"] == status_code
    assert logs[-1]["provider_request_id"] == "req-retry"
    assert logs[-1]["rfp_id"] == "rfp-log-test"
    assert "PRIVATE" not in json.dumps(logs)
    assert "private-key" not in json.dumps(logs)


async def test_validation_logs_do_not_include_model_output():
    def handle(request):
        return httpx.Response(
            200,
            headers={"x-request-id": "req-invalid"},
            json={
                "id": "completion",
                "object": "chat.completion",
                "created": 0,
                "model": "glm",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"wrong":"PRIVATE-MODEL-OUTPUT"}',
                        },
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http_client:
        sdk = AsyncOpenAI(api_key="test", http_client=http_client)
        chat = StructuredChatClient(Settings(_env_file=None), sdk)
        with capture_logs() as logs, pytest.raises(ValidationError):
            await chat.complete(
                instructions="", user_input="", output_model=StructuredOutput, max_tokens=10
            )
    assert "PRIVATE" not in json.dumps(logs)
    assert logs[-1]["status_code"] == 200
    assert logs[-1]["provider_request_id"] == "req-invalid"


@pytest.mark.asyncio
async def test_structured_chat_rejects_schema_mismatch() -> None:
    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "glm-5.3-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"wrong":"value"}'},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    openai_client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://example.test/v4/",
        http_client=http_client,
    )
    client = StructuredChatClient(
        Settings(llm_api_key=SecretStr("test-key"), llm_reasoning_effort="max"),
        client=openai_client,
    )

    with pytest.raises(ValidationError):
        await client.complete(
            instructions="Answer the question.",
            user_input="test",
            output_model=StructuredOutput,
            max_tokens=100,
        )
    await http_client.aclose()
