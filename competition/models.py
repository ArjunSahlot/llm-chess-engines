from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class TimeControl:
    movetime_ms: int = 100
    init_ms: int | None = None
    increment_ms: int = 0
    move_overhead_ms: int = 20

    def go_command(self, white_ms: int | None, black_ms: int | None) -> str:
        if self.init_ms is None:
            return f"go movetime {self.movetime_ms}"
        wtime = max(1, (white_ms or self.init_ms) - self.move_overhead_ms)
        btime = max(1, (black_ms or self.init_ms) - self.move_overhead_ms)
        return f"go wtime {wtime} btime {btime} winc {self.increment_ms} binc {self.increment_ms}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CompetitionConfig:
    generations_root: Path = Path("generations")
    results_db: Path = Path("results/competition.sqlite3")
    time_control: TimeControl = TimeControl()
    max_plies: int = 240
    poll_seconds: float = 5.0
    handshake_timeout_seconds: float = 5.0
    move_timeout_seconds: float = 10.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["generations_root"] = str(self.generations_root)
        data["results_db"] = str(self.results_db)
        return data


@dataclass(frozen=True, slots=True)
class Engine:
    engine_id: str
    name: str
    provider_model: str
    run_id: str
    root: Path
    command: list[str]
    manifest_path: Path | None = None
    manifest: dict[str, Any] | None = None

    @property
    def executable(self) -> Path:
        return Path(self.command[0])
