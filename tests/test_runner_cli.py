from __future__ import annotations

import json

from harness.runner import GenerationRunner
from harness.types import AdapterResponse, Message, RunConfig, ToolCall, ToolSpec
from main import build_parser


class FakeAdapter:
    def complete(self, messages: list[Message], tools: list[ToolSpec], config: RunConfig) -> AdapterResponse:
        assert {tool.name for tool in tools} >= {"write_file", "compile_engine"}
        return AdapterResponse(
            tool_calls=[
                ToolCall("1", "write_file", {"path": "main.cpp", "content": "int main() { return 0; }\n"}),
                ToolCall("2", "write_file", {"path": "Makefile", "content": "engine: main.cpp\n\tg++ -std=c++17 main.cpp -o engine\n"}),
                ToolCall("3", "compile_engine", {}),
            ]
        )


def test_generation_runner_writes_manifest_and_transcript(tmp_path) -> None:
    config = RunConfig("fake", "model", "run-1", "NO_KEY", root=tmp_path)
    manifest = GenerationRunner(config, adapter=FakeAdapter()).run()

    assert manifest.status == "compiled"
    assert manifest.compile_ok

    run_dir = tmp_path / "fake-model" / "run-1"
    assert (run_dir / "engine").exists()
    data = json.loads((run_dir / "manifest.json").read_text())
    assert data["compile_ok"] is True
    assert "compile_engine" in (run_dir / "transcript.jsonl").read_text()


def test_generate_cli_parses_provider_defaults() -> None:
    args = build_parser().parse_args(["generate", "--provider", "deepseek", "--model", "deepseek-chat", "--run-id", "r1"])
    assert args.provider == "deepseek"
    assert args.model == "deepseek-chat"
