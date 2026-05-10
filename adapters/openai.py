from __future__ import annotations

import json
import os
from typing import Any

from harness.types import AdapterResponse, Message, RunConfig, ToolCall, ToolSpec


def _tool_schema(spec: ToolSpec) -> dict[str, Any]:
    return {"type": "function", "name": spec.name, "description": spec.description, "parameters": spec.schema}


def _input(messages: list[Message]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool":
            items.append({"type": "function_call_output", "call_id": message.tool_call_id, "output": message.content})
        elif message.role == "assistant" and message.tool_calls:
            for call in message.tool_calls:
                items.append(
                    {
                        "type": "function_call",
                        "call_id": call.id,
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    }
                )
            if message.content:
                items.append({"role": "assistant", "content": message.content})
        else:
            items.append({"role": message.role, "content": message.content})
    return items


class OpenAIResponsesAdapter:
    def complete(self, messages: list[Message], tools: list[ToolSpec], config: RunConfig) -> AdapterResponse:
        from openai import OpenAI

        client = OpenAI(api_key=os.environ[config.api_key_env], base_url=config.base_url)
        response = client.responses.create(
            model=config.model,
            input=_input(messages),
            tools=[_tool_schema(spec) for spec in tools],
            temperature=config.temperature,
            max_output_tokens=config.max_output_tokens,
        )
        text = getattr(response, "output_text", "") or ""
        calls: list[ToolCall] = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) == "function_call":
                args = json.loads(getattr(item, "arguments", "") or "{}")
                calls.append(ToolCall(id=getattr(item, "call_id", getattr(item, "id", "")), name=item.name, arguments=args))
        usage = response.usage.model_dump() if getattr(response, "usage", None) else {}
        return AdapterResponse(text=text, tool_calls=calls, usage=usage, raw={"id": response.id})
