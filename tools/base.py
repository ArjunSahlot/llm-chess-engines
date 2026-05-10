from __future__ import annotations

from typing import Any, Protocol

from harness.types import ToolResult, ToolSpec
from harness.workspace import GenerationWorkspace


class Tool(Protocol):
    spec: ToolSpec

    def __call__(self, workspace: GenerationWorkspace, arguments: dict[str, Any]) -> ToolResult:
        ...
