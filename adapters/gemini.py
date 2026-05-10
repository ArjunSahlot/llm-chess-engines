from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from harness.types import AdapterResponse, Message, RunConfig, ToolCall, ToolSpec


def _gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    converted = deepcopy(schema)

    def sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            value.pop("additionalProperties", None)
            value.pop("additional_properties", None)
            for nested in value.values():
                sanitize(nested)
        elif isinstance(value, list):
            for nested in value:
                sanitize(nested)
        return value

    return sanitize(converted)


def _function_declaration(spec: ToolSpec) -> dict[str, Any]:
    return {"name": spec.name, "description": spec.description, "parameters": _gemini_schema(spec.schema)}


def _contents(messages: list[Message]) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    tool_parts: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "system":
            continue
        if message.role == "tool":
            tool_parts.append(
                {
                    "function_response": {
                        "name": message.tool_name or "tool_result",
                        "response": {"result": message.content},
                    }
                }
            )
            continue
        if tool_parts:
            contents.append({"role": "user", "parts": tool_parts})
            tool_parts = []
        if message.role == "assistant" and message.tool_calls:
            parts = []
            for call in message.tool_calls:
                part: dict[str, Any] = {"function_call": {"name": call.name, "args": call.arguments, "id": call.id}}
                signature = call.metadata.get("gemini_thought_signature")
                if signature is not None:
                    part["thought_signature"] = signature
                parts.append(part)
            contents.append(
                {
                    "role": "model",
                    "parts": parts,
                }
            )
        else:
            role = "model" if message.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message.content}]})
    if tool_parts:
        contents.append({"role": "user", "parts": tool_parts})
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
                thought_signature = getattr(part, "thought_signature", None)
                metadata = {"gemini_thought_signature": thought_signature} if thought_signature is not None else {}
                calls.append(
                    ToolCall(
                        id=getattr(function_call, "id", "") or function_call.name,
                        name=function_call.name,
                        arguments=dict(function_call.args or {}),
                        metadata=metadata,
                    )
                )
    usage = response.usage_metadata.model_dump() if getattr(response, "usage_metadata", None) else {}
    return "\n".join(text_parts), calls, usage
