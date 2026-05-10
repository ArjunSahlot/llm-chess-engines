from __future__ import annotations

from typing import Any

from harness.types import ToolResult, ToolSpec
from harness.workspace import GenerationWorkspace


spec = ToolSpec(
    name="write_file",
    description="Write a UTF-8 text file inside the current run directory, creating parent directories as needed.",
    schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative file path to write."},
            "content": {"type": "string", "description": "Complete file contents."},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    },
)


def __call__(workspace: GenerationWorkspace, arguments: dict[str, Any]) -> ToolResult:
    try:
        path = workspace.resolve_inside(str(arguments["path"]))
        content = str(arguments["content"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        rel = str(path.relative_to(workspace.path))
        return ToolResult("", spec.name, True, f"wrote {rel} ({len(content)} bytes)", {"path": rel, "bytes": len(content)})
    except (OSError, ValueError) as exc:
        return ToolResult("", spec.name, False, str(exc))
