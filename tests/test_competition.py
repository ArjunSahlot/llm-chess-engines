from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from competition.discovery import discover_engines
from competition.models import TimeControl
from competition.runner import CompetitionRunner


ENGINE_SCRIPT = """#!{python}
import sys

MOVES = {moves!r}
ply = 0

for raw in sys.stdin:
    line = raw.strip()
    if line.startswith("position startpos"):
        parts = line.split()
        ply = max(0, len(parts) - parts.index("moves") - 1) if "moves" in parts else 0
    if line == "uci":
        print("id name fake", flush=True)
        print("uciok", flush=True)
    elif line == "isready":
        print("readyok", flush=True)
    elif line.startswith("go"):
        move = MOVES[ply] if ply < len(MOVES) else "0000"
        print(f"bestmove {{move}}", flush=True)
    elif line == "quit":
        break
"""


def write_engine(path: Path, moves: list[str]) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(ENGINE_SCRIPT.format(python=sys.executable, moves=moves), encoding="utf-8")
    path.chmod(0o755)
    (path.parent / "manifest.json").write_text('{"compile_ok": true}\n', encoding="utf-8")


def test_discover_engines_finds_executables(tmp_path) -> None:
    write_engine(tmp_path / "openai-gpt-test" / "v1" / "engine", ["e2e4"])

    engines = discover_engines(tmp_path)

    assert len(engines) == 1
    assert engines[0].provider_model == "openai-gpt-test"
    assert engines[0].run_id == "v1"
    assert engines[0].command[0].endswith("/engine")


def test_competition_runner_persists_game_data(tmp_path) -> None:
    line = ["e2e4", "e7e5", "g1f3", "b8c6"]
    write_engine(tmp_path / "a" / "v1" / "engine", line)
    write_engine(tmp_path / "b" / "v1" / "engine", line)
    db_path = tmp_path / "results.sqlite3"

    played = CompetitionRunner(
        generations_root=tmp_path,
        results_db=db_path,
        time_control=TimeControl(movetime_ms=1),
        max_plies=4,
    ).run(max_games=1, forever=False)

    assert played == 1
    db = sqlite3.connect(db_path)
    try:
        assert db.execute("SELECT COUNT(*) FROM engines").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM games WHERE status='finished'").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM moves").fetchone()[0] == 4
        assert db.execute("SELECT COUNT(*) FROM uci_events").fetchone()[0] > 8
        pgn = db.execute("SELECT pgn FROM games").fetchone()[0]
        assert "1. e4 e5 2. Nf3 Nc6" in pgn
        assert db.execute("SELECT COUNT(*) FROM standings").fetchone()[0] == 2
    finally:
        db.close()
