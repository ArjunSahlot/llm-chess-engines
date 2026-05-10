from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


Role = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True)
class Message:
    role: Role
    content: str
    tool_call_id: str | None = None
    tool_calls: list["ToolCall"] = field(default_factory=list)


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ToolResult:
    call_id: str
    name: str
    ok: bool
    content: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    schema: dict[str, Any]


@dataclass(slots=True)
class AdapterResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunConfig:
    provider: str
    model: str
    run_id: str
    api_key_env: str
    base_url: str | None = None
    temperature: float = 0.2
    max_turns: int = 16
    timeout_seconds: int = 60
    root: Path = Path("generations")


@dataclass(slots=True)
class RunManifest:
    provider: str
    model: str
    run_id: str
    run_dir: str
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    status: str = "running"
    turns: int = 0
    compile_ok: bool = False
    final_text: str = ""
    error: str | None = None

    def finish(self, *, status: str, turns: int, compile_ok: bool, final_text: str = "", error: str | None = None) -> None:
        self.status = status
        self.turns = turns
        self.compile_ok = compile_ok
        self.final_text = final_text
        self.error = error
        self.finished_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
