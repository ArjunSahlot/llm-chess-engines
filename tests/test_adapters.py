from __future__ import annotations

import sys
from types import SimpleNamespace

from adapters.anthropic import AnthropicAdapter
from adapters.gemini import GeminiAdapter
from adapters.openai import OpenAIResponsesAdapter
from adapters.openai_compatible import OpenAICompatibleAdapter
from harness.types import Message, RunConfig, ToolCall, ToolSpec


TOOL = ToolSpec("write_file", "write a file", {"type": "object", "properties": {}, "additionalProperties": False})
CONFIG = RunConfig("test", "model", "run", "TEST_API_KEY")


def test_openai_compatible_adapter_parses_tool_calls(monkeypatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "x")

    class Chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                assert kwargs["tools"][0]["function"]["name"] == "write_file"
                call = SimpleNamespace(id="c1", function=SimpleNamespace(name="write_file", arguments='{"path":"a"}'))
                msg = SimpleNamespace(content="", tool_calls=[call])
                return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None, id="r1")

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda **kwargs: SimpleNamespace(chat=Chat)))
    response = OpenAICompatibleAdapter().complete([Message("user", "go")], [TOOL], CONFIG)
    assert response.tool_calls == [ToolCall("c1", "write_file", {"path": "a"})]


def test_openai_responses_adapter_parses_tool_calls(monkeypatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "x")

    class Responses:
        @staticmethod
        def create(**kwargs):
            assert kwargs["tools"][0]["type"] == "function"
            item = SimpleNamespace(type="function_call", call_id="c1", name="write_file", arguments='{"path":"a"}')
            return SimpleNamespace(output_text="", output=[item], usage=None, id="r1")

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda **kwargs: SimpleNamespace(responses=Responses)))
    response = OpenAIResponsesAdapter().complete([Message("user", "go")], [TOOL], CONFIG)
    assert response.tool_calls[0].name == "write_file"
    assert response.tool_calls[0].arguments == {"path": "a"}


def test_anthropic_adapter_parses_tool_use(monkeypatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "x")

    class Messages:
        @staticmethod
        def create(**kwargs):
            assert kwargs["tools"][0]["input_schema"]["type"] == "object"
            assert kwargs["max_tokens"] == CONFIG.max_output_tokens
            block = SimpleNamespace(type="tool_use", id="c1", name="write_file", input={"path": "a"})
            return SimpleNamespace(content=[block], usage=None, id="r1", stop_reason="tool_use")

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=lambda **kwargs: SimpleNamespace(messages=Messages)))
    response = AnthropicAdapter().complete([Message("system", "s"), Message("user", "go")], [TOOL], CONFIG)
    assert response.tool_calls == [ToolCall("c1", "write_file", {"path": "a"})]


def test_gemini_adapter_parses_function_call(monkeypatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "x")

    class Client:
        def __init__(self, **kwargs):
            pass

        class models:
            @staticmethod
            def generate_content(**kwargs):
                assert kwargs["config"].tools[0].function_declarations[0]["name"] == "write_file"
                call = SimpleNamespace(id="c1", name="write_file", args={"path": "a"})
                part = SimpleNamespace(text=None, function_call=call)
                content = SimpleNamespace(parts=[part])
                return SimpleNamespace(candidates=[SimpleNamespace(content=content)], usage_metadata=None)

    class Tool:
        def __init__(self, function_declarations):
            self.function_declarations = function_declarations

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    genai = SimpleNamespace(Client=Client, types=SimpleNamespace(Tool=Tool, GenerateContentConfig=GenerateContentConfig))
    monkeypatch.setitem(sys.modules, "google", SimpleNamespace(genai=genai))
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", genai.types)

    response = GeminiAdapter().complete([Message("user", "go")], [TOOL], CONFIG)
    assert response.tool_calls == [ToolCall("c1", "write_file", {"path": "a"})]
