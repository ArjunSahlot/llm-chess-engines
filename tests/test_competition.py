from __future__ import annotations

import os
import random
import sqlite3
import sys
from pathlib import Path

from competition.discovery import discover_engines
from competition.leaderboard import build_leaderboard, save_leaderboard
from competition.models import CompetitionConfig, Engine, TimeControl
from competition.results_migration import migrate_results_db
from competition.runner import CompetitionRunner
from competition.store import CompetitionStore


ENGINE_SCRIPT = """#!{python}
import chess
import sys
import time

MOVES = {moves!r}
SUPPORTS_FEN = {supports_fen!r}
GO_SLEEP_SECONDS = {go_sleep_seconds!r}
ply = 0
board = chess.Board()

for raw in sys.stdin:
    line = raw.strip()
    if line.startswith("position startpos"):
        parts = line.split()
        board = chess.Board()
        if "moves" in parts:
            for move_text in parts[parts.index("moves") + 1:]:
                board.push(chess.Move.from_uci(move_text))
        ply = max(0, len(parts) - parts.index("moves") - 1) if "moves" in parts else 0
    elif SUPPORTS_FEN and line.startswith("position fen "):
        board = chess.Board(line.removeprefix("position fen "))
        ply = board.ply()
    if line == "uci":
        print("id name fake", flush=True)
        print("uciok", flush=True)
    elif line == "isready":
        print("readyok", flush=True)
    elif line.startswith("go"):
        if GO_SLEEP_SECONDS:
            time.sleep(GO_SLEEP_SECONDS)
        move = MOVES[ply] if ply < len(MOVES) else next(iter(board.legal_moves), chess.Move.null()).uci()
        print(f"bestmove {{move}}", flush=True)
    elif line == "quit":
        break
"""


def write_engine(path: Path, moves: list[str], supports_fen: bool = True, go_sleep_seconds: float = 0) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        ENGINE_SCRIPT.format(
            python=sys.executable,
            moves=moves,
            supports_fen=supports_fen,
            go_sleep_seconds=go_sleep_seconds,
        ),
        encoding="utf-8",
    )
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
        openings_file=None,
        max_plies=4,
    ).run(max_games=1, forever=False)

    assert played == 1
    db = sqlite3.connect(db_path)
    try:
        assert db.execute("SELECT COUNT(*) FROM engines").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM games WHERE status='finished'").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM moves").fetchone()[0] == 4
        assert db.execute("SELECT COUNT(*) FROM uci_events").fetchone()[0] > 8
        assert db.execute("SELECT COUNT(*) FROM uci_events WHERE direction='in' AND line LIKE 'position fen %'").fetchone()[0] == 4
        pgn = db.execute("SELECT pgn FROM games").fetchone()[0]
        assert "1. e4 e5 2. Nf3 Nc6" in pgn
        assert db.execute("SELECT COUNT(*) FROM standings").fetchone()[0] == 2
    finally:
        db.close()


def test_competition_cycles_time_controls_and_persists_opening(tmp_path) -> None:
    line = ["e2e4", "e7e5", "g1f3", "b8c6"]
    write_engine(tmp_path / "a" / "v1" / "engine", line)
    write_engine(tmp_path / "b" / "v1" / "engine", line)
    openings = tmp_path / "openings.txt"
    openings.write_text("e2e4 e7e5\n", encoding="utf-8")
    db_path = tmp_path / "results.sqlite3"

    played = CompetitionRunner(
        generations_root=tmp_path,
        results_db=db_path,
        time_controls=[TimeControl(movetime_ms=1), TimeControl(movetime_ms=2)],
        openings_file=openings,
        max_plies=4,
    ).run(max_games=2, forever=False)

    assert played == 2
    db = sqlite3.connect(db_path)
    try:
        rows = db.execute("SELECT time_control_json, opening_moves, opening_fen, pgn FROM games ORDER BY scheduled_at").fetchall()
        assert '"movetime_ms": 1' in rows[0][0]
        assert '"movetime_ms": 2' in rows[1][0]
        assert rows[0][1] == "e2e4 e7e5"
        assert rows[0][2]
        assert "Opening" in rows[0][3]
        assert "FEN" in rows[0][3]
        assert "2. Nf3" in rows[0][3]
    finally:
        db.close()


def test_competition_skips_openings_for_engines_that_ignore_fen(tmp_path) -> None:
    line = ["e2e4", "e7e5", "g1f3", "b8c6"]
    write_engine(tmp_path / "a" / "v1" / "engine", line)
    write_engine(tmp_path / "b" / "v1" / "engine", line, supports_fen=False)
    openings = tmp_path / "openings.txt"
    openings.write_text("d2d4 g8f6 f2f3\n", encoding="utf-8")
    db_path = tmp_path / "results.sqlite3"

    played = CompetitionRunner(
        generations_root=tmp_path,
        results_db=db_path,
        time_control=TimeControl(movetime_ms=1),
        openings_file=openings,
        max_plies=4,
    ).run(max_games=1, forever=False)

    assert played == 1
    db = sqlite3.connect(db_path)
    try:
        row = db.execute("SELECT opening_moves, opening_skip_reason, pgn FROM games").fetchone()
        assert row[0] == ""
        assert "probe returned illegal move" in row[1]
        assert "OpeningSkipped" in row[2]
        assert db.execute("SELECT COUNT(*) FROM engine_capabilities").fetchone()[0] == 2
    finally:
        db.close()


def test_competition_counts_bestmove_timeout_as_loss(tmp_path) -> None:
    line = ["e2e4", "e7e5", "g1f3", "b8c6"]
    write_engine(tmp_path / "slow" / "v1" / "engine", line, go_sleep_seconds=0.2)
    write_engine(tmp_path / "fast" / "v1" / "engine", line)
    db_path = tmp_path / "results.sqlite3"

    played = CompetitionRunner(
        generations_root=tmp_path,
        results_db=db_path,
        time_control=TimeControl(movetime_ms=1),
        openings_file=None,
        max_plies=4,
        move_timeout_seconds=0.01,
    ).run(max_games=1, forever=False)

    assert played == 1
    db = sqlite3.connect(db_path)
    try:
        row = db.execute(
            """
            SELECT games.status, games.result, games.reason, standings.losses
            FROM engines
            JOIN standings ON standings.engine_id = engines.engine_id
            JOIN games ON engines.engine_id IN (games.white_engine_id, games.black_engine_id)
            WHERE engines.name = 'slow/v1'
            """
        ).fetchone()
        assert row[0] == "finished"
        assert row[1] in {"1-0", "0-1"}
        assert "timed out" in row[2]
        assert row[3] == 1
        assert db.execute("SELECT result_source FROM games").fetchone()[0] == "forfeit"
    finally:
        db.close()


def test_next_pairing_prioritizes_engine_with_lowest_total_games(tmp_path) -> None:
    write_engine(tmp_path / "a" / "v1" / "engine", ["e2e4"])
    write_engine(tmp_path / "b" / "v1" / "engine", ["e2e4"])
    write_engine(tmp_path / "megalodon" / "v1" / "engine", ["e2e4"])
    engines = discover_engines(tmp_path)
    by_model = {engine.provider_model: engine for engine in engines}
    db_path = tmp_path / "results.sqlite3"
    store = CompetitionStore(db_path)
    try:
        for engine in engines:
            store.upsert_engine(engine)
        config = CompetitionConfig(generations_root=tmp_path, results_db=db_path)
        tc = TimeControl(movetime_ms=1)
        old_white = by_model["a"]
        old_black = by_model["b"]
        new_engine = by_model["megalodon"]
        for index in range(40):
            store.create_game(f"old-{index}", old_white, old_black, config, tc, None, "")
        for index in range(5):
            store.create_game(f"new-{index}", new_engine, old_white, config, tc, None, "")

        white, black = CompetitionRunner._next_pairing(store, engines)

        assert new_engine.engine_id in {white.engine_id, black.engine_id}
    finally:
        store.close()


def test_next_pairing_rotates_underplayed_engines_until_near_leader(tmp_path) -> None:
    for name in ("leader", "mid", "megalodon", "newcomer"):
        write_engine(tmp_path / name / "v1" / "engine", ["e2e4"])
    engines = discover_engines(tmp_path)
    by_model = {engine.provider_model: engine for engine in engines}
    db_path = tmp_path / "results.sqlite3"
    store = CompetitionStore(db_path)
    try:
        for engine in engines:
            store.upsert_engine(engine)
        config = CompetitionConfig(generations_root=tmp_path, results_db=db_path)
        tc = TimeControl(movetime_ms=1)
        for index in range(400):
            store.create_game(f"leader-{index}", by_model["leader"], by_model["mid"], config, tc, None, "")
        for index in range(120):
            store.create_game(f"megalodon-{index}", by_model["megalodon"], by_model["leader"], config, tc, None, "")
        for index in range(50):
            store.create_game(f"newcomer-{index}", by_model["newcomer"], by_model["leader"], config, tc, None, "")

        chosen_names = set()
        for _ in range(12):
            white, black = CompetitionRunner._next_pairing(store, engines)
            chosen_names.update([white.name, black.name])
            store.create_game(f"next-{_}", white, black, config, tc, None, "")

        assert by_model["newcomer"].name in chosen_names
        assert by_model["leader"].name in chosen_names or by_model["mid"].name in chosen_names
    finally:
        store.close()


def test_next_pairing_spreads_two_new_engines_across_whole_field(tmp_path) -> None:
    random.seed(0)
    new_names = ("a-new", "b-new")
    established_names = ("c", "d", "e", "f", "g", "h")
    for name in (*new_names, *established_names):
        write_engine(tmp_path / name / "v1" / "engine", ["e2e4"])
    engines = discover_engines(tmp_path)
    by_model = {engine.provider_model: engine for engine in engines}
    db_path = tmp_path / "results.sqlite3"
    store = CompetitionStore(db_path)
    try:
        for engine in engines:
            store.upsert_engine(engine)
        config = CompetitionConfig(generations_root=tmp_path, results_db=db_path)
        tc = TimeControl(movetime_ms=1)
        for index in range(300):
            white = by_model[established_names[index % len(established_names)]]
            black = by_model[established_names[(index + 1) % len(established_names)]]
            store.create_game(f"established-{index}", white, black, config, tc, None, "")

        new_engine_names = {by_model[name].name for name in new_names}
        all_opponents_by_new = {
            by_model[name].name: {engine.name for engine in engines if engine.name != by_model[name].name}
            for name in new_names
        }
        opponents_by_new = {name: set() for name in new_engine_names}
        ordered_pairs = set()
        for index in range(28):
            white, black = CompetitionRunner._next_pairing(store, engines)
            pair_names = {white.name, black.name}
            ordered_pairs.add((white.name, black.name))
            for new_name in pair_names & new_engine_names:
                opponent_name = black.name if white.name == new_name else white.name
                opponents_by_new[new_name].add(opponent_name)
            store.create_game(f"next-{index}", white, black, config, tc, None, "")

        assert (by_model["a-new"].name, by_model["b-new"].name) in ordered_pairs
        assert (by_model["b-new"].name, by_model["a-new"].name) in ordered_pairs
        assert opponents_by_new == all_opponents_by_new
    finally:
        store.close()


def test_next_pairing_counts_historical_duplicate_engine_names(tmp_path) -> None:
    write_engine(tmp_path / "a" / "v1" / "engine", ["e2e4"])
    write_engine(tmp_path / "b" / "v1" / "engine", ["e2e4"])
    engines = discover_engines(tmp_path)
    by_model = {engine.provider_model: engine for engine in engines}
    old_a = Engine(
        engine_id="old-a-id",
        name=by_model["a"].name,
        provider_model=by_model["a"].provider_model,
        run_id=by_model["a"].run_id,
        root=by_model["a"].root,
        command=by_model["a"].command,
    )
    db_path = tmp_path / "results.sqlite3"
    store = CompetitionStore(db_path)
    try:
        for engine in [old_a, *engines]:
            store.upsert_engine(engine)
        config = CompetitionConfig(generations_root=tmp_path, results_db=db_path)
        tc = TimeControl(movetime_ms=1)
        for index in range(7):
            store.create_game(f"old-a-{index}", old_a, by_model["b"], config, tc, None, "")

        counts = store.engine_game_counts_by_name()

        assert counts[by_model["a"].name] == 7
        assert counts[by_model["b"].name] == 7
    finally:
        store.close()


def test_leaderboard_builds_anchored_elos_and_saves_outputs(tmp_path) -> None:
    write_engine(tmp_path / "stockfish" / "v1" / "engine", ["e2e4"])
    write_engine(tmp_path / "megalodon" / "v1" / "engine", ["e2e4"])
    engines = discover_engines(tmp_path)
    by_model = {engine.provider_model: engine for engine in engines}
    db_path = tmp_path / "results.sqlite3"
    store = CompetitionStore(db_path)
    try:
        for engine in engines:
            store.upsert_engine(engine)
        config = CompetitionConfig(generations_root=tmp_path, results_db=db_path)
        tc = TimeControl(movetime_ms=1)
        stockfish = by_model["stockfish"]
        megalodon = by_model["megalodon"]
        for index, result in enumerate(["1-0", "1-0", "1/2-1/2", "0-1"]):
            store.create_game(f"game-{index}", stockfish, megalodon, config, tc, None, "")
            store.finish_game(f"game-{index}", result, "test", "", None, None)
    finally:
        store.close()

    rows = build_leaderboard(db_path, {"stockfish/v1": 3200})
    stockfish_row = next(row for row in rows if row.name == "stockfish/v1")

    assert stockfish_row.elo == 3200
    assert stockfish_row.anchored
    assert stockfish_row.games == 4

    _, json_path, markdown_path = save_leaderboard(tmp_path / "results", rows, {"stockfish/v1": 3200})
    assert json_path.exists()
    assert markdown_path.exists()


def test_leaderboard_collapses_duplicate_engine_names(tmp_path) -> None:
    write_engine(tmp_path / "stockfish" / "v1" / "engine", ["e2e4"])
    write_engine(tmp_path / "megalodon" / "v1" / "engine", ["e2e4"])
    engines = discover_engines(tmp_path)
    by_model = {engine.provider_model: engine for engine in engines}
    old_stockfish = Engine(
        engine_id="old-stockfish-id",
        name=by_model["stockfish"].name,
        provider_model=by_model["stockfish"].provider_model,
        run_id=by_model["stockfish"].run_id,
        root=by_model["stockfish"].root,
        command=by_model["stockfish"].command,
    )
    db_path = tmp_path / "results.sqlite3"
    store = CompetitionStore(db_path)
    try:
        for engine in [old_stockfish, *engines]:
            store.upsert_engine(engine)
        config = CompetitionConfig(generations_root=tmp_path, results_db=db_path)
        tc = TimeControl(movetime_ms=1)
        stockfish = by_model["stockfish"]
        megalodon = by_model["megalodon"]
        store.create_game("old-game", old_stockfish, megalodon, config, tc, None, "")
        store.finish_game("old-game", "1-0", "test", "", None, None)
        store.create_game("new-game", stockfish, megalodon, config, tc, None, "")
        store.finish_game("new-game", "1-0", "test", "", None, None)
    finally:
        store.close()

    rows = build_leaderboard(db_path, {"stockfish/v1": 3200})

    assert [row.name for row in rows].count("stockfish/v1") == 1
    assert next(row for row in rows if row.name == "stockfish/v1").games == 2


def test_leaderboard_counts_historical_failed_timeout_as_loss(tmp_path) -> None:
    write_engine(tmp_path / "slow" / "v1" / "engine", ["e2e4"])
    write_engine(tmp_path / "fast" / "v1" / "engine", ["e2e4"])
    engines = discover_engines(tmp_path)
    by_model = {engine.provider_model: engine for engine in engines}
    db_path = tmp_path / "results.sqlite3"
    store = CompetitionStore(db_path)
    try:
        for engine in engines:
            store.upsert_engine(engine)
        config = CompetitionConfig(generations_root=tmp_path, results_db=db_path)
        tc = TimeControl(movetime_ms=1)
        slow = by_model["slow"]
        fast = by_model["fast"]
        store.create_game("failed-timeout", slow, fast, config, tc, None, "")
        store.record_uci("failed-timeout", slow.engine_id, "in", "go movetime 1")
        store.fail_game("failed-timeout", "timed out waiting for bestmove after 0.01s")
    finally:
        store.close()

    rows = build_leaderboard(db_path)
    slow_row = next(row for row in rows if row.name == "slow/v1")
    fast_row = next(row for row in rows if row.name == "fast/v1")

    assert slow_row.losses == 1
    assert fast_row.wins == 1


def test_migrate_results_converts_inferable_failed_games_and_ignores_unknowns(tmp_path) -> None:
    write_engine(tmp_path / "slow" / "v1" / "engine", ["e2e4"])
    write_engine(tmp_path / "fast" / "v1" / "engine", ["e2e4"])
    engines = discover_engines(tmp_path)
    by_model = {engine.provider_model: engine for engine in engines}
    db_path = tmp_path / "results.sqlite3"
    store = CompetitionStore(db_path)
    try:
        for engine in engines:
            store.upsert_engine(engine)
        config = CompetitionConfig(generations_root=tmp_path, results_db=db_path)
        tc = TimeControl(movetime_ms=1)
        slow = by_model["slow"]
        fast = by_model["fast"]
        store.create_game("failed-timeout", slow, fast, config, tc, None, "")
        store.record_uci("failed-timeout", slow.engine_id, "in", "go movetime 1")
        store.record_uci("failed-timeout", fast.engine_id, "in", "quit")
        store.fail_game("failed-timeout", "timed out waiting for engine output")
        store.create_game("unknown-failure", fast, slow, config, tc, None, "")
        store.fail_game("unknown-failure", "unexpected harness exception")
    finally:
        store.close()

    summary = migrate_results_db(db_path, create_backup=False)

    assert summary.fixed_failed_games == 1
    assert summary.ignored_failed_games == 1
    db = sqlite3.connect(db_path)
    try:
        fixed = db.execute(
            "SELECT status, result, result_source, forfeiting_engine_id FROM games WHERE game_id='failed-timeout'"
        ).fetchone()
        ignored = db.execute("SELECT status, result_source FROM games WHERE game_id='unknown-failure'").fetchone()
        assert fixed == ("finished", "0-1", "migrated_forfeit", slow.engine_id)
        assert ignored == ("ignored", "migration_ignored")
    finally:
        db.close()
