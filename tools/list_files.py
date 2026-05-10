from __future__ import annotations

from typing import Any

from harness.types import ToolResult, ToolSpec
from harness.workspace import GenerationWorkspace


spec = ToolSpec(
    name="list_files",
    description="List files under the current run directory.",
    schema={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Optional relative directory to list.", "default": "."}},
        "additionalProperties": False,
    },
)


def __call__(workspace: GenerationWorkspace, arguments: dict[str, Any]) -> ToolResult:
    root = workspace.resolve_inside(str(arguments.get("path") or "."))
    if not root.exists():
        return ToolResult("", spec.name, False, f"path does not exist: {root.relative_to(workspace.path)}")
    if not root.is_dir():
        return ToolResult("", spec.name, False, f"path is not a directory: {root.relative_to(workspace.path)}")

    files = sorted(str(path.relative_to(workspace.path)) for path in root.rglob("*") if path.is_file())
    return ToolResult("", spec.name, True, "\n".join(files) or "(no files)", {"files": files})
