from __future__ import annotations

import os
from typing import Any

from harness.types import AdapterResponse, Message, RunConfig, ToolCall, ToolSpec


def _function_declaration(spec: ToolSpec) -> dict[str, Any]:
    return {"name": spec.name, "description": spec.description, "parameters": spec.schema}


def _contents(messages: list[Message]) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "system":
            continue
        if message.role == "tool":
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "function_response": {
                                "name": message.tool_name or "tool_result",
                                "response": {"result": message.content},
                            }
                        }
                    ],
                }
            )
        elif message.role == "assistant" and message.tool_calls:
            contents.append(
                {
                    "role": "model",
                    "parts": [
                        {"function_call": {"name": call.name, "args": call.arguments, "id": call.id}} for call in message.tool_calls
                    ],
                }
            )
        else:
            role = "model" if message.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message.content}]})
    return contents


class GeminiAdapter:
    def complete(self, messages: list[Message], tools: list[ToolSpec], config: RunConfig) -> AdapterResponse:
        from google import genai
        from google.genai import types

        system = "\n".join(message.content for message in messages if message.role == "system") or None
        client = genai.Client(api_key=os.environ[config.api_key_env])
        request = {
            "model": config.model,
            "contents": _contents(messages),
            "config": types.GenerateContentConfig(
                system_instruction=system,
                temperature=config.temperature,
                max_output_tokens=config.max_output_tokens,
                tools=[types.Tool(function_declarations=[_function_declaration(spec) for spec in tools])],
            ),
        }
        if config.stream:
            text_parts: list[str] = []
            calls: list[ToolCall] = []
            usage: dict[str, Any] = {}
            for chunk in client.models.generate_content_stream(**request):
                chunk_text, chunk_calls, chunk_usage = _parse_response(chunk)
                text_parts.append(chunk_text)
                calls.extend(chunk_calls)
                usage.update(chunk_usage)
            return AdapterResponse(text="".join(text_parts), tool_calls=calls, usage=usage, raw={})

        response = client.models.generate_content(
            **request,
        )
        text, calls, usage = _parse_response(response)
        return AdapterResponse(text=text, tool_calls=calls, usage=usage, raw={})


def _parse_response(response: Any) -> tuple[str, list[ToolCall], dict[str, Any]]:
    text_parts: list[str] = []
    calls: list[ToolCall] = []
    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            if getattr(part, "text", None):
                text_parts.append(part.text)
            function_call = getattr(part, "function_call", None)
            if function_call:
                calls.append(
                    ToolCall(
                        id=getattr(function_call, "id", "") or function_call.name,
                        name=function_call.name,
                        arguments=dict(function_call.args or {}),
                    )
                )
    usage = response.usage_metadata.model_dump() if getattr(response, "usage_metadata", None) else {}
    return "\n".join(text_parts), calls, usage
