import json
from unittest.mock import AsyncMock

import pytest

from app.agents.proposal_generator import OpenAIProposalGenerator, ProposalContext
from app.core.config import Settings
from app.core.exceptions import ProposalGenerationError
from app.llm.structured_chat import LLMOutputTruncatedError
from app.schemas.proposal import ProposalBatch, ProposalSections


def context(count=42):
    return ProposalContext(
        rfp={"id": "test", "review_feedback": "keep gaps"},
        customer={},
        capabilities=[
            {
                "requirement_key": f"REQ-{i:04}",
                "requirement": f"需求{i}",
                "capability_status": "UNSUPPORTED",
                "evidence": [],
            }
            for i in range(count)
        ],
    )


def batch(items):
    return ProposalBatch(
        requirement_responses=[
            {
                "requirement_key": item["requirement_key"],
                "response": "Not supported",
                "evidence_summary": "No evidence",
                "risk_or_gap": "Requires review",
            }
            for item in reversed(items)
        ]
    )


def sections():
    return ProposalSections(**{name: "Review required" for name in ProposalSections.model_fields})


def generator(monkeypatch, complete):
    client = AsyncMock()
    client.complete.side_effect = complete
    monkeypatch.setattr("app.agents.proposal_generator.StructuredChatClient", lambda _: client)
    return OpenAIProposalGenerator(Settings(_env_file=None)), client


async def test_42_requirements_merged_in_source_order_without_resending_evidence(monkeypatch):
    async def complete(**kwargs):
        payload = json.loads(kwargs["user_input"])
        assert "Simplified Chinese" in kwargs["instructions"]
        assert "Keep JSON field names, requirement_key identifiers" in kwargs["instructions"]
        assert payload["rfp"]["review_feedback"] == "keep gaps"
        if kwargs["output_model"] is ProposalBatch:
            assert len(payload["capabilities"]) <= 8
            return batch(payload["capabilities"])
        assert len(payload["responses"]) == 42
        assert all("evidence" not in item for item in payload["responses"])
        return sections()

    agent, client = generator(monkeypatch, complete)
    source = context()
    draft = await agent.generate(source)
    assert len(draft.requirement_responses) == 42
    assert [item.requirement_key for item in draft.requirement_responses] == [
        item["requirement_key"] for item in source.capabilities
    ]
    assert all(item.capability_status == "UNSUPPORTED" for item in draft.requirement_responses)
    assert client.complete.await_count == 7


async def test_truncated_batch_is_split(monkeypatch):
    async def complete(**kwargs):
        if kwargs["output_model"] is ProposalSections:
            return sections()
        items = json.loads(kwargs["user_input"])["capabilities"]
        if len(items) > 2:
            raise LLMOutputTruncatedError()
        return batch(items)

    agent, _ = generator(monkeypatch, complete)
    assert len((await agent.generate(context(5))).requirement_responses) == 5


@pytest.mark.parametrize("mode", ["missing", "duplicate", "unknown"])
async def test_invalid_batch_never_generates_sections(monkeypatch, mode):
    async def complete(**kwargs):
        result = batch(json.loads(kwargs["user_input"])["capabilities"])
        if mode == "missing":
            result.requirement_responses.pop()
        elif mode == "duplicate":
            result.requirement_responses.append(result.requirement_responses[0])
        else:
            result.requirement_responses[0].requirement_key = "UNKNOWN"
        return result

    agent, client = generator(monkeypatch, complete)
    with pytest.raises(ProposalGenerationError, match="exactly once"):
        await agent.generate(context(3))
    assert client.complete.await_count == 4
    assert all(
        call.kwargs["output_model"] is ProposalBatch for call in client.complete.await_args_list
    )


@pytest.mark.parametrize("mode", ["missing", "duplicate", "unknown"])
async def test_coverage_correction_recovers_without_splitting(monkeypatch, mode):
    attempts = 0

    async def complete(**kwargs):
        nonlocal attempts
        assert "Simplified Chinese" in kwargs["instructions"]
        if kwargs["output_model"] is ProposalSections:
            return sections()
        items = json.loads(kwargs["user_input"])["capabilities"]
        result = batch(items)
        attempts += 1
        for item in items:
            assert item["requirement_key"] in kwargs["instructions"]
        if attempts == 1:
            if mode == "missing":
                result.requirement_responses.pop()
            elif mode == "duplicate":
                result.requirement_responses.append(result.requirement_responses[0])
            else:
                result.requirement_responses[0].requirement_key = "UNKNOWN"
        else:
            assert "previous attempt had invalid requirement coverage" in kwargs["instructions"]
        return result

    agent, client = generator(monkeypatch, complete)
    source = context(3)
    draft = await agent.generate(source)
    assert [item.requirement_key for item in draft.requirement_responses] == [
        item["requirement_key"] for item in source.capabilities
    ]
    assert client.complete.await_count == 3


async def test_persistent_multi_item_mismatch_splits_to_singletons(monkeypatch):
    async def complete(**kwargs):
        if kwargs["output_model"] is ProposalSections:
            return sections()
        items = json.loads(kwargs["user_input"])["capabilities"]
        result = batch(items)
        if len(items) > 1:
            result.requirement_responses.pop()
        return result

    agent, client = generator(monkeypatch, complete)
    source = context(3)
    draft = await agent.generate(source)
    assert [item.requirement_key for item in draft.requirement_responses] == [
        item["requirement_key"] for item in source.capabilities
    ]
    assert all(item.capability_status == "UNSUPPORTED" for item in draft.requirement_responses)
    assert client.complete.await_count == 8


async def test_single_item_mismatch_has_bounded_failure(monkeypatch):
    async def complete(**kwargs):
        return ProposalBatch(requirement_responses=[])

    agent, client = generator(monkeypatch, complete)
    with pytest.raises(ProposalGenerationError, match="repair exhausted for REQ-0000"):
        await agent.generate(context(1))
    assert client.complete.await_count == 2


async def test_single_item_truncation_stops_with_clear_error(monkeypatch):
    async def complete(**kwargs):
        raise LLMOutputTruncatedError()

    agent, client = generator(monkeypatch, complete)
    with pytest.raises(ProposalGenerationError, match="truncated"):
        await agent.generate(context(1))
    assert client.complete.await_count == 1
