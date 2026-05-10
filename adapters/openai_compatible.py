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
            reasoning_content = next(
                (
                    call.metadata["reasoning_content"]
                    for call in message.tool_calls
                    if call.metadata.get("reasoning_content")
                ),
                None,
            )
            out.append(
                {
                    "role": "assistant",
                    "content": message.content or None,
                    **({"reasoning_content": reasoning_content} if reasoning_content else {}),
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
        if config.stream:
            return self._complete_streaming(client, messages, tools, config)

        response = client.chat.completions.create(
            model=config.model,
            messages=_messages(messages),
            tools=[_tool_schema(spec) for spec in tools],
            tool_choice="auto",
            max_tokens=config.max_output_tokens,
        )
        choice = response.choices[0].message
        calls = []
        reasoning_content = getattr(choice, "reasoning_content", None)
        for call in choice.tool_calls or []:
            args = json.loads(call.function.arguments or "{}")
            metadata = {"reasoning_content": reasoning_content} if reasoning_content else {}
            calls.append(ToolCall(id=call.id, name=call.function.name, arguments=args, metadata=metadata))
        usage = response.usage.model_dump() if getattr(response, "usage", None) else {}
        return AdapterResponse(text=choice.content or "", tool_calls=calls, usage=usage, raw={"id": response.id})

    def _complete_streaming(self, client: Any, messages: list[Message], tools: list[ToolSpec], config: RunConfig) -> AdapterResponse:
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_parts: dict[int, dict[str, str]] = {}
        usage: dict[str, Any] = {}
        response_id: str | None = None
        stream = client.chat.completions.create(
            model=config.model,
            messages=_messages(messages),
            tools=[_tool_schema(spec) for spec in tools],
            tool_choice="auto",
            max_tokens=config.max_output_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        for chunk in stream:
            response_id = getattr(chunk, "id", response_id)
            if getattr(chunk, "usage", None):
                usage = chunk.usage.model_dump()
            for choice in getattr(chunk, "choices", []) or []:
                delta = getattr(choice, "delta", None)
                if getattr(delta, "content", None):
                    text_parts.append(delta.content)
                if getattr(delta, "reasoning_content", None):
                    reasoning_parts.append(delta.reasoning_content)
                for call in getattr(delta, "tool_calls", []) or []:
                    index = getattr(call, "index", 0)
                    part = tool_parts.setdefault(index, {"id": "", "name": "", "arguments": ""})
                    if getattr(call, "id", None):
                        part["id"] = call.id
                    function = getattr(call, "function", None)
                    if getattr(function, "name", None):
                        part["name"] = function.name
                    if getattr(function, "arguments", None):
                        part["arguments"] += function.arguments

        reasoning_content = "".join(reasoning_parts)
        calls = []
        for _, part in sorted(tool_parts.items()):
            if not part["name"]:
                continue
            metadata = {"reasoning_content": reasoning_content} if reasoning_content else {}
            calls.append(ToolCall(id=part["id"], name=part["name"], arguments=json.loads(part["arguments"] or "{}"), metadata=metadata))
        return AdapterResponse(text="".join(text_parts), tool_calls=calls, usage=usage, raw={"id": response_id})
