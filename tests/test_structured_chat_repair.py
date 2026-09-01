import json
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIStatusError, AsyncOpenAI
from pydantic import BaseModel, ValidationError, field_validator
from structlog.testing import capture_logs

from app.core.config import Settings
from app.llm.structured_chat import StructuredChatClient, llm_error_summary
from app.llm.validation import MAX_VALIDATION_DETAILS, validation_details
from app.schemas.requirement import RequirementExtractionBatch


def requirement_batch(**overrides):
    return {
        "requirements": [
            {
                "category": "security",
                "requirement_text": "PRIVATE-SOURCE must support SAML.",
                "normalized_text": "Support SAML.",
                "mandatory": True,
                "confidence": 0.9,
                "source_page_start": None,
                **overrides,
            }
        ]
    }


def completion(content):
    return httpx.Response(
        200,
        headers={"x-request-id": "req-schema-test"},
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "glm-5.3-flash",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "usage": {"prompt_tokens": 50, "completion_tokens": 80, "total_tokens": 130},
        },
    )


async def complete(chat):
    return await chat.complete(
        instructions="PRIVATE-INSTRUCTIONS: extract all requirements.",
        user_input="PRIVATE-DOCUMENT: must support SAML.",
        output_model=RequirementExtractionBatch,
        max_tokens=12000,
        operation="extract_requirements",
        correlation_id="rfp-schema-test",
    )


@pytest.mark.parametrize(
    "invalid_content",
    [
        json.dumps(requirement_batch(confidence=95, source_page_start=0)),
        '```json\n{"requirements": "PRIVATE-INVALID-JSON"}\n```',
        json.dumps(requirement_batch(source_page_start=4, source_page_end=2)),
    ],
)
async def test_schema_repair_preserves_context_and_returns_validated_output(invalid_content):
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return completion(
            invalid_content if len(requests) == 1 else json.dumps(requirement_batch())
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http_client:
        sdk = AsyncOpenAI(api_key="PRIVATE-KEY", http_client=http_client)
        chat = StructuredChatClient(Settings(_env_file=None, llm_max_retries=0), sdk)
        with capture_logs() as logs:
            result = await complete(chat)
    assert result == RequirementExtractionBatch.model_validate(requirement_batch())
    assert len(requests) == 2  # Schema correction also works with HTTP retries disabled.
    original, repaired = requests
    assert repaired["model"] == original["model"] == "glm-5.3-flash"
    assert repaired["messages"][:2] == original["messages"]
    assert repaired["messages"][2] == {"role": "assistant", "content": invalid_content}
    assert "COMPLETE corrected JSON" in repaired["messages"][3]["content"]
    assert "do not drop items or invent facts" in repaired["messages"][3]["content"]
    assert repaired["response_format"] == original["response_format"] == {"type": "json_object"}
    assert repaired["max_tokens"] == original["max_tokens"] == 12000
    assert [log["event"] for log in logs] == [
        "llm_request_started",
        "llm_schema_repair_requested",
        "llm_request_started",
        "llm_request_completed",
    ]
    assert logs[1]["validation_error_count"] >= 1
    assert logs[1]["finish_reason"] == "stop"
    assert logs[1]["total_tokens"] == 130
    assert logs[1]["provider_request_id"] == "req-schema-test"
    assert logs[-1]["schema_repair_attempt"] == 1
    assert "PRIVATE" not in json.dumps(logs)


async def test_two_validation_errors_are_logged_and_second_failure_is_final():
    calls = 0

    def handle(request):
        nonlocal calls
        calls += 1
        return completion(json.dumps(requirement_batch(confidence=95, source_page_start=0)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http_client:
        chat = StructuredChatClient(
            Settings(_env_file=None, llm_max_retries=10),
            AsyncOpenAI(api_key="test", http_client=http_client),
        )
        with capture_logs() as logs, pytest.raises(ValidationError) as error:
            await complete(chat)
    assert calls == 2  # Transport retry budget must not become schema-repair budget.
    failure = logs[-1]
    assert failure["event"] == "llm_request_failed"
    assert failure["rfp_id"] == "rfp-schema-test"
    assert failure["retryable"] is False
    assert failure["schema_repair_attempt"] == 1
    assert failure["validation_error_count"] == 2
    assert failure["validation_errors_truncated"] is False
    assert {(tuple(item["loc"]), item["type"]) for item in failure["validation_errors"]} == {
        (("requirements", 0, "confidence"), "less_than_equal"),
        (("requirements", 0, "source_page_start"), "greater_than_equal"),
    }
    assert "PRIVATE" not in json.dumps(logs)
    assert "PRIVATE" not in llm_error_summary(error.value)


@pytest.mark.parametrize(
    "responses,retries,expected_calls,success",
    [
        ([429, "invalid", 503, "valid"], 2, 4, True),
        ([429, 503, "invalid", "valid"], 2, 4, True),
        (["invalid", 429, 503, "valid"], 2, 4, True),
        ([429, "invalid", 503, "valid"], 1, 3, False),
        (["invalid", 401, "valid"], 2, 2, False),
    ],
)
async def test_transport_retries_share_budget_with_one_repair(
    monkeypatch, responses, retries, expected_calls, success
):
    requests = []

    def handle(request):
        response = responses[len(requests)]
        requests.append(json.loads(request.content))
        if isinstance(response, int):
            return httpx.Response(response, json={"error": {"message": "PRIVATE-ERROR"}})
        return completion(
            json.dumps(requirement_batch(confidence=95 if response == "invalid" else 0.9))
        )

    monkeypatch.setattr("app.llm.structured_chat.asyncio.sleep", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http_client:
        chat = StructuredChatClient(
            Settings(_env_file=None, llm_max_retries=retries),
            AsyncOpenAI(api_key="test", http_client=http_client, max_retries=9),
        )
        with capture_logs() as logs:
            if success:
                await complete(chat)
            else:
                with pytest.raises(APIStatusError):
                    await complete(chat)
    assert len(requests) == expected_calls
    assert sum(log["event"] == "llm_schema_repair_requested" for log in logs) == 1
    assert all(len(request["messages"]) in {2, 4} for request in requests)
    assert "PRIVATE" not in json.dumps(logs)


async def test_validation_diagnostics_are_bounded_and_unknown_keys_are_redacted():
    content = json.dumps({f"PRIVATE-KEY-{index}": "PRIVATE-VALUE" for index in range(40)})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: completion(content))
    ) as http_client:
        chat = StructuredChatClient(
            Settings(_env_file=None), AsyncOpenAI(api_key="test", http_client=http_client)
        )
        with capture_logs() as logs, pytest.raises(ValidationError):
            await complete(chat)
    failure = logs[-1]
    assert failure["validation_error_count"] == 41
    assert len(failure["validation_errors"]) == MAX_VALIDATION_DETAILS
    assert failure["validation_errors_truncated"] is True
    assert any(item["loc"] == ["<unknown_field>"] for item in failure["validation_errors"])
    assert all(
        item["loc"] in (["requirements"], ["<unknown_field>"])
        for item in failure["validation_errors"]
    )
    assert "PRIVATE" not in json.dumps(logs)


def test_missing_field_diagnostic_retains_schema_field_name():
    with pytest.raises(ValidationError) as error:
        RequirementExtractionBatch.model_validate({})
    assert validation_details(error.value, RequirementExtractionBatch) == [
        {"loc": ["requirements"], "type": "missing", "msg": "Required field is missing."}
    ]


def test_custom_validator_cannot_leak_its_input_through_message():
    class Output(BaseModel):
        answer: str

        @field_validator("answer")
        @classmethod
        def reject(cls, value):
            raise ValueError(f"PRIVATE-CUSTOM-MESSAGE: {value}")

    with pytest.raises(ValidationError) as error:
        Output.model_validate({"answer": "PRIVATE-OUTPUT"})
    details = validation_details(error.value, Output)
    assert details[0]["loc"] == ["answer"]
    assert details[0]["type"] == "value_error"
    assert "PRIVATE" not in json.dumps(details)


async def test_schema_repair_budget_is_per_completion_not_per_client():
    calls = 0

    def handle(request):
        nonlocal calls
        calls += 1
        return completion(json.dumps(requirement_batch(confidence=95 if calls % 2 else 0.9)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http_client:
        chat = StructuredChatClient(
            Settings(_env_file=None), AsyncOpenAI(api_key="test", http_client=http_client)
        )
        await complete(chat)
        await complete(chat)
    assert calls == 4


async def test_empty_completion_is_not_retried_as_schema_error():
    calls = 0

    def handle(request):
        nonlocal calls
        calls += 1
        return completion("")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http_client:
        chat = StructuredChatClient(
            Settings(_env_file=None), AsyncOpenAI(api_key="test", http_client=http_client)
        )
        with pytest.raises(ValueError, match="empty completion"):
            await complete(chat)
    assert calls == 1
