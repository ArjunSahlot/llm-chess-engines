from __future__ import annotations

from harness.types import ToolCall
from harness.workspace import GenerationWorkspace, safe_slug
from tools import compile_engine, read_file, write_file


def test_safe_slug_rejects_empty() -> None:
    assert safe_slug("OpenAI/GPT 5") == "openai-gpt-5"


def test_workspace_blocks_path_escape(tmp_path) -> None:
    workspace = GenerationWorkspace(tmp_path, "openai", "gpt", "run")
    workspace.create()

    assert workspace.resolve_inside("src/main.cpp").is_relative_to(workspace.path)

    try:
        workspace.resolve_inside("../escape.cpp")
    except ValueError as exc:
        assert "escapes" in str(exc)
    else:
        raise AssertionError("path escape was allowed")


def test_file_tools_are_confined(tmp_path) -> None:
    workspace = GenerationWorkspace(tmp_path, "openai", "gpt", "run")
    workspace.create()

    result = write_file.__call__(workspace, {"path": "src/main.cpp", "content": "int main() {}\n"})
    assert result.ok
    assert read_file.__call__(workspace, {"path": "src/main.cpp"}).content == "int main() {}\n"

    bad = write_file.__call__(workspace, {"path": "../oops", "content": ""})
    assert not bad.ok


def test_compile_engine_success_and_failure(tmp_path) -> None:
    workspace = GenerationWorkspace(tmp_path, "openai", "gpt", "run")
    workspace.create()
    write_file.__call__(workspace, {"path": "main.cpp", "content": "int main() { return 0; }\n"})
    write_file.__call__(workspace, {"path": "Makefile", "content": "engine: main.cpp\n\tg++ -std=c++17 -O2 main.cpp -o engine\n"})

    ok = compile_engine.__call__(workspace, {})
    assert ok.ok
    assert ok.data["returncode"] == 0

    write_file.__call__(workspace, {"path": "main.cpp", "content": "int main( { return 0; }\n"})
    failed = compile_engine.__call__(workspace, {})
    assert not failed.ok
    assert failed.data["returncode"] != 0


def test_unknown_tool_call_is_reported(tmp_path) -> None:
    from harness.tools import execute_tool

    workspace = GenerationWorkspace(tmp_path, "openai", "gpt", "run")
    workspace.create()
    result = execute_tool(workspace, ToolCall("1", "missing", {}))
    assert not result.ok
    assert result.call_id == "1"
