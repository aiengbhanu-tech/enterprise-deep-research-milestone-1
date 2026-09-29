from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import get_settings


@dataclass(frozen=True)
class LLMResponse:
    content: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0,
    ) -> LLMResponse: ...


class MockLLMProvider:
    name = "mock"

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0,
    ) -> LLMResponse:
        return LLMResponse(
            content="Mock LLM response",
            provider=self.name,
            model=model or "mock-v1",
        )


class OpenAILLMProvider:
    name = "openai"

    def __init__(self, api_key: str, timeout_seconds: float = 90) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0,
    ) -> LLMResponse:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": model or settings.openai_model,
                    "messages": messages,
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
        payload = response.json()
        usage = payload.get("usage", {})
        return LLMResponse(
            content=payload["choices"][0]["message"]["content"],
            provider=self.name,
            model=payload.get("model", model or settings.openai_model),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            cached_tokens=int(usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)),
            trace_id=response.headers.get("x-request-id"),
        )


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return OpenAILLMProvider(settings.openai_api_key)
    return MockLLMProvider()
