from __future__ import annotations

from typing import Protocol

from harness.types import AdapterResponse, Message, RunConfig, ToolSpec


class ProviderAdapter(Protocol):
    def complete(self, messages: list[Message], tools: list[ToolSpec], config: RunConfig) -> AdapterResponse:
        ...


def make_adapter(config: RunConfig) -> ProviderAdapter:
    provider = config.provider.lower()
    if provider == "openai":
        from adapters.openai import OpenAIResponsesAdapter

        return OpenAIResponsesAdapter()
    if provider == "anthropic":
        from adapters.anthropic import AnthropicAdapter

        return AnthropicAdapter()
    if provider == "gemini":
        from adapters.gemini import GeminiAdapter

        return GeminiAdapter()

    from adapters.openai_compatible import OpenAICompatibleAdapter

    return OpenAICompatibleAdapter()
