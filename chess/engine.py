from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EngineBuild:
    name: str
    root: Path
    command: list[str]
    protocol: str = "uci"


@dataclass(frozen=True, slots=True)
class EngineResult:
    engine: EngineBuild
    build_ok: bool
    log_path: Path | None = None
