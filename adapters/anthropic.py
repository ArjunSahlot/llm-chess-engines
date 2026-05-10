from __future__ import annotations

import os
from typing import Any

from harness.types import AdapterResponse, Message, RunConfig, ToolCall, ToolSpec


def _tool_schema(spec: ToolSpec) -> dict[str, Any]:
    return {"name": spec.name, "description": spec.description, "input_schema": spec.schema}


def _messages(messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
    system: str | None = None
    out: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "system":
            system = message.content
        elif message.role == "tool":
            out.append(
                {
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": message.tool_call_id, "content": message.content}],
                }
            )
        elif message.role == "assistant" and message.tool_calls:
            content: list[dict[str, Any]] = []
            if message.content:
                content.append({"type": "text", "text": message.content})
            content.extend({"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments} for call in message.tool_calls)
            out.append({"role": "assistant", "content": content})
        else:
            out.append({"role": message.role, "content": message.content})
    return system, out


class AnthropicAdapter:
    def complete(self, messages: list[Message], tools: list[ToolSpec], config: RunConfig) -> AdapterResponse:
        from anthropic import Anthropic

        system, api_messages = _messages(messages)
        client = Anthropic(api_key=os.environ[config.api_key_env])
        params = {
            "model": config.model,
            "max_tokens": config.max_output_tokens,
            "system": system,
            "messages": api_messages,
            "tools": [_tool_schema(spec) for spec in tools],
            "temperature": config.temperature,
        }
        if config.stream:
            with client.messages.stream(**params) as stream:
                response = stream.get_final_message()
            return _response_to_adapter(response)

        return _response_to_adapter(client.messages.create(**params))


def _response_to_adapter(response: Any) -> AdapterResponse:
    text_parts: list[str] = []
    calls: list[ToolCall] = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input)))
    usage = response.usage.model_dump() if getattr(response, "usage", None) else {}
    return AdapterResponse(
        text="\n".join(text_parts),
        tool_calls=calls,
        usage=usage,
        raw={"id": response.id, "stop_reason": getattr(response, "stop_reason", None)},
    )
