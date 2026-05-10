from __future__ import annotations

from typing import Any

from harness.types import ToolCall, ToolResult, ToolSpec
from harness.workspace import GenerationWorkspace
from tools import list_files, read_file, run_shell, write_file


TOOLS = {
    read_file.spec.name: read_file,
    write_file.spec.name: write_file,
    list_files.spec.name: list_files,
    run_shell.spec.name: run_shell,
}


def tool_specs() -> list[ToolSpec]:
    return [tool.spec for tool in TOOLS.values()]


def execute_tool(workspace: GenerationWorkspace, call: ToolCall) -> ToolResult:
    tool = TOOLS.get(call.name)
    if tool is None:
        return ToolResult(call.id, call.name, False, f"unknown tool: {call.name}")
    try:
        result = tool.__call__(workspace, call.arguments)
    except (KeyError, TypeError, ValueError) as exc:
        result = ToolResult("", call.name, False, f"invalid tool call: {exc}")
    return ToolResult(call.id, result.name, result.ok, result.content, result.data)


def specs_as_json_schema() -> list[dict[str, Any]]:
    return [{"name": spec.name, "description": spec.description, "schema": spec.schema} for spec in tool_specs()]
