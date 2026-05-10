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

    @classmethod
    def parse(cls, value: str, move_overhead_ms: int = 20) -> "TimeControl":
        text = value.strip().lower()
        if text.startswith("movetime:"):
            return cls(movetime_ms=int(text.split(":", 1)[1]), move_overhead_ms=move_overhead_ms)
        if text.startswith("clock:"):
            clock = text.split(":", 1)[1]
            base, _, inc = clock.partition("+")
            return cls(init_ms=int(base), increment_ms=int(inc or 0), move_overhead_ms=move_overhead_ms)
        if "+" in text:
            base, inc = text.split("+", 1)
            return cls(init_ms=int(base), increment_ms=int(inc), move_overhead_ms=move_overhead_ms)
        return cls(movetime_ms=int(text), move_overhead_ms=move_overhead_ms)

    def label(self) -> str:
        if self.init_ms is None:
            return f"movetime:{self.movetime_ms}"
        return f"clock:{self.init_ms}+{self.increment_ms}"


@dataclass(frozen=True, slots=True)
class CompetitionConfig:
    generations_root: Path = Path("generations")
    results_db: Path = Path("results/competition.sqlite3")
    time_controls: tuple[TimeControl, ...] = (TimeControl(),)
    openings_file: Path | None = Path("competition/openings.txt")
    max_plies: int = 240
    poll_seconds: float = 5.0
    handshake_timeout_seconds: float = 5.0
    move_timeout_seconds: float = 10.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["generations_root"] = str(self.generations_root)
        data["results_db"] = str(self.results_db)
        data["openings_file"] = str(self.openings_file) if self.openings_file is not None else None
        return data

    @property
    def time_control(self) -> TimeControl:
        return self.time_controls[0]


@dataclass(frozen=True, slots=True)
class Opening:
    moves: tuple[str, ...]
    source: str

    @property
    def label(self) -> str:
        return " ".join(self.moves)


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
