from __future__ import annotations

from typing import Any

from harness.types import ToolCall, ToolResult, ToolSpec
from harness.workspace import GenerationWorkspace
from tools import compile_engine, read_file, write_file


TOOLS = {
    read_file.spec.name: read_file,
    write_file.spec.name: write_file,
    compile_engine.spec.name: compile_engine,
}


def tool_specs() -> list[ToolSpec]:
    return [tool.spec for tool in TOOLS.values()]


def execute_tool(workspace: GenerationWorkspace, call: ToolCall) -> ToolResult:
    tool = TOOLS.get(call.name)
    if tool is None:
        return ToolResult(call.id, call.name, False, f"unknown tool: {call.name}")
    missing = [name for name in tool.spec.schema.get("required", []) if name not in call.arguments]
    if missing:
        fields = ", ".join(missing)
        return ToolResult(
            call.id,
            call.name,
            False,
            f"invalid tool call: missing required field(s): {fields}. If this happened while writing a large file, "
            "the provider response likely hit its output limit; retry with smaller chunks using write_file then append_file.",
        )
    try:
        result = tool.__call__(workspace, call.arguments)
    except (KeyError, TypeError, ValueError) as exc:
        result = ToolResult("", call.name, False, f"invalid tool call: {exc}")
    return ToolResult(call.id, result.name, result.ok, result.content, result.data)


def specs_as_json_schema() -> list[dict[str, Any]]:
    return [{"name": spec.name, "description": spec.description, "schema": spec.schema} for spec in tool_specs()]
