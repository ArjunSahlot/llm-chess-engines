from __future__ import annotations

import subprocess
from typing import Any

from harness.types import ToolResult, ToolSpec
from harness.workspace import GenerationWorkspace


spec = ToolSpec(
    name="compile_engine",
    description="Run `make` in the current run directory and return compiler output.",
    schema={
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "Optional make target.", "default": ""},
        },
        "additionalProperties": False,
    },
)


def __call__(workspace: GenerationWorkspace, arguments: dict[str, Any]) -> ToolResult:
    target = str(arguments.get("target") or "").strip()
    command = ["make", "-B"] + ([target] if target else [])
    try:
        proc = subprocess.run(
            command,
            cwd=workspace.path,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolResult("", spec.name, False, str(exc), {"command": command})

    output = "\n".join(part for part in [proc.stdout.strip(), proc.stderr.strip()] if part)
    ok = proc.returncode == 0
    content = output or ("compile succeeded" if ok else "compile failed with no output")
    return ToolResult("", spec.name, ok, content, {"command": command, "returncode": proc.returncode})
