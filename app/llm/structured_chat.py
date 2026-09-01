import asyncio
import json
from time import monotonic
from typing import TypeVar

import structlog
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.core.exceptions import LLMConfigurationError
from app.llm.validation import validation_details

StructuredModelT = TypeVar("StructuredModelT", bound=BaseModel)
logger = structlog.get_logger(__name__)


def llm_error_summary(exc: Exception) -> str:
    """Keep provider bodies, prompts, and validation input out of logs and status."""
    if isinstance(exc, APITimeoutError):
        return "LLM request timed out"
    if isinstance(exc, APIConnectionError):
        return "LLM connection failed"
    if isinstance(exc, APIStatusError):
        return f"LLM provider returned HTTP {exc.status_code}"
    if isinstance(exc, ValidationError):
        return f"LLM output did not match the schema ({exc.error_count()} errors)"
    return f"LLM completion failed ({type(exc).__name__})"


class StructuredChatClient:
    """OpenAI-compatible Chat Completions client with strict local validation."""

    def __init__(self, settings: Settings, client: AsyncOpenAI | None = None) -> None:
        self.settings = settings
        self.client = client.with_options(max_retries=0) if client else self._build_client()

    async def complete(
        self,
        *,
        instructions: str,
        user_input: str,
        output_model: type[StructuredModelT],
        max_tokens: int,
        operation: str = "structured_completion",
        correlation_id: str | None = None,
    ) -> StructuredModelT:
        schema = json.dumps(output_model.model_json_schema(), ensure_ascii=False)
        messages: list[ChatCompletionMessageParam] = [
            {
                "role": "system",
                "content": (
                    f"{instructions}\n\n"
                    "Return only one valid JSON object. Do not use Markdown fences or "
                    "add commentary. The object must match this JSON Schema:\n"
                    f"{schema}"
                ),
            },
            {"role": "user", "content": user_input},
        ]
        # One generation, at most one schema correction, and a SHARED budget for
        # transport retries. SDK retries stay disabled to avoid multiplying calls.
        max_attempts = self.settings.llm_max_retries + 2
        transport_retries = 0
        schema_repair_attempt = 0
        request_started = monotonic()
        for attempt in range(1, max_attempts + 1):
            attempt_started = monotonic()
            response = None
            content = ""
            logger.info(
                "llm_request_started",
                operation=operation,
                correlation_id=correlation_id,
                rfp_id=correlation_id,
                model=self.settings.llm_model,
                attempt=attempt,
                max_attempts=max_attempts,
                schema_repair_attempt=schema_repair_attempt,
                input_chars=len(user_input),
                max_tokens=max_tokens,
            )
            try:
                response = await self.client.chat.completions.create(
                    model=self.settings.llm_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    max_tokens=max_tokens,
                    temperature=self.settings.llm_temperature,
                    top_p=self.settings.llm_top_p,
                    extra_body={
                        "thinking": {"type": "enabled", "clear_thinking": False},
                        "reasoning_effort": self.settings.llm_reasoning_effort,
                    },
                )
                if not response.choices:
                    raise ValueError("LLM returned no completion choices")
                content = response.choices[0].message.content or ""
                if not content:
                    raise ValueError("LLM returned an empty completion")
                result = output_model.model_validate_json(content)
            except Exception as exc:
                can_repair = (
                    isinstance(exc, ValidationError)
                    and bool(content)
                    and schema_repair_attempt == 0
                )
                can_retry_transport = (
                    self._is_retryable(exc) and transport_retries < self.settings.llm_max_retries
                )
                status_code = (
                    exc.status_code
                    if isinstance(exc, APIStatusError)
                    else 200
                    if response is not None
                    else None
                )
                request_id = getattr(exc, "request_id", None) or getattr(
                    response, "_request_id", None
                )
                cause = exc.__cause__
                fields: dict[str, object] = {
                    "operation": operation,
                    "correlation_id": correlation_id,
                    "rfp_id": correlation_id,
                    "model": self.settings.llm_model,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "attempt_duration_ms": round((monotonic() - attempt_started) * 1000),
                    "total_duration_ms": round((monotonic() - request_started) * 1000),
                    "retryable": can_repair or can_retry_transport,
                    "schema_repair_attempt": schema_repair_attempt,
                    "transport_retries": transport_retries,
                    "status_code": status_code,
                    "provider_request_id": request_id,
                    "error_type": type(exc).__name__,
                    "error_message": llm_error_summary(exc),
                    "cause_type": type(cause).__name__ if cause else None,
                    "finish_reason": (
                        response.choices[0].finish_reason
                        if response is not None and response.choices
                        else None
                    ),
                    "prompt_tokens": getattr(
                        getattr(response, "usage", None), "prompt_tokens", None
                    ),
                    "completion_tokens": getattr(
                        getattr(response, "usage", None), "completion_tokens", None
                    ),
                    "total_tokens": getattr(getattr(response, "usage", None), "total_tokens", None),
                }
                if isinstance(exc, ValidationError):
                    details = validation_details(exc, output_model)
                    fields.update(
                        validation_errors=details,
                        validation_error_count=exc.error_count(),
                        validation_errors_truncated=exc.error_count() > len(details),
                    )
                    if can_repair:
                        logger.warning("llm_schema_repair_requested", **fields)
                        messages.extend(
                            [
                                {"role": "assistant", "content": content},
                                {
                                    "role": "user",
                                    "content": (
                                        "Your previous JSON failed local validation. Correct it "
                                        "using the original task, source text, and JSON Schema. "
                                        "Return the COMPLETE corrected JSON object, not a patch. "
                                        "Preserve all source-supported items and their meaning; "
                                        "do not drop items or invent facts to satisfy validation. "
                                        "Include all required fields, remove undefined fields, "
                                        "and respect types, ranges, and cross-field rules. "
                                        "Unknown field paths are redacted as <unknown_field>. "
                                        "There is only one correction round. "
                                        f"Validation error count: {exc.error_count()}. "
                                        "Validation details (at most 20):\n"
                                        + json.dumps(details, ensure_ascii=False)
                                    ),
                                },
                            ]
                        )
                        schema_repair_attempt = 1
                        continue
                if can_retry_transport:
                    delay_seconds = min(2**transport_retries, 8)
                    transport_retries += 1
                    logger.warning(
                        "llm_request_retrying",
                        **fields,
                        retry_delay_seconds=delay_seconds,
                    )
                    await asyncio.sleep(delay_seconds)
                    continue
                logger.error("llm_request_failed", **fields)
                raise

            usage = response.usage
            logger.info(
                "llm_request_completed",
                operation=operation,
                correlation_id=correlation_id,
                rfp_id=correlation_id,
                model=self.settings.llm_model,
                status_code=200,
                attempt=attempt,
                schema_repair_attempt=schema_repair_attempt,
                attempt_duration_ms=round((monotonic() - attempt_started) * 1000),
                total_duration_ms=round((monotonic() - request_started) * 1000),
                provider_request_id=getattr(response, "_request_id", None),
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
            )
            return result
        raise RuntimeError("LLM request loop ended unexpectedly")

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, (APIConnectionError, APITimeoutError)):
            return True
        return isinstance(exc, APIStatusError) and (
            exc.status_code in {408, 409, 429} or exc.status_code >= 500
        )

    def _build_client(self) -> AsyncOpenAI:
        if self.settings.llm_api_key is None:
            raise LLMConfigurationError("LLM_API_KEY (or ZAI_API_KEY) is required for LLM requests")
        api_key = self.settings.llm_api_key.get_secret_value().strip()
        if not api_key:
            raise LLMConfigurationError("LLM_API_KEY (or ZAI_API_KEY) is required for LLM requests")
        return AsyncOpenAI(
            api_key=api_key,
            base_url=self.settings.llm_base_url,
            timeout=self.settings.llm_timeout_seconds,
            max_retries=0,
        )
