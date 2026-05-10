from __future__ import annotations

import json
import os
from typing import Any

from harness.types import AdapterResponse, Message, RunConfig, ToolCall, ToolSpec


def _tool_schema(spec: ToolSpec) -> dict[str, Any]:
    return {"type": "function", "function": {"name": spec.name, "description": spec.description, "parameters": spec.schema}}


def _messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool":
            out.append({"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content})
        elif message.role == "assistant" and message.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": message.content or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                        }
                        for call in message.tool_calls
                    ],
                }
            )
        else:
            out.append({"role": message.role, "content": message.content})
    return out


class OpenAICompatibleAdapter:
    def complete(self, messages: list[Message], tools: list[ToolSpec], config: RunConfig) -> AdapterResponse:
        from openai import OpenAI

        client = OpenAI(api_key=os.environ[config.api_key_env], base_url=config.base_url)
        response = client.chat.completions.create(
            model=config.model,
            messages=_messages(messages),
            tools=[_tool_schema(spec) for spec in tools],
            tool_choice="auto",
            temperature=config.temperature,
        )
        choice = response.choices[0].message
        calls = []
        for call in choice.tool_calls or []:
            args = json.loads(call.function.arguments or "{}")
            calls.append(ToolCall(id=call.id, name=call.function.name, arguments=args))
        usage = response.usage.model_dump() if getattr(response, "usage", None) else {}
        return AdapterResponse(text=choice.content or "", tool_calls=calls, usage=usage, raw={"id": response.id})
