from __future__ import annotations

from typing import Any

from harness.types import ToolResult, ToolSpec
from harness.workspace import GenerationWorkspace


spec = ToolSpec(
    name="read_file",
    description="Read a UTF-8 text file from the current run directory.",
    schema={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Relative file path to read."}},
        "required": ["path"],
        "additionalProperties": False,
    },
)


def __call__(workspace: GenerationWorkspace, arguments: dict[str, Any]) -> ToolResult:
    path = workspace.resolve_inside(str(arguments["path"]))
    try:
        content = path.read_text(encoding="utf-8")
        return ToolResult("", spec.name, True, content, {"path": str(path.relative_to(workspace.path))})
    except OSError as exc:
        return ToolResult("", spec.name, False, str(exc))
