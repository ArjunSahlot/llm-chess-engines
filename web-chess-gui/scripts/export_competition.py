from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "results" / "competition.sqlite3"
DEFAULT_OUT = APP_ROOT / "public" / "data" / "competition.json"
RESULT_SCORES = {
    "1-0": (1.0, 0.0),
    "0-1": (0.0, 1.0),
    "1/2-1/2": (0.5, 0.5),
}


def compact_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def rows(db: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(sql, params).fetchall()]


def main() -> None:
    db_path = Path(DEFAULT_DB)
    out_path = Path(DEFAULT_OUT)
    if not db_path.exists():
        raise SystemExit(f"Competition database not found: {db_path}")

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    raw_engines = rows(
        db,
        """
        SELECT engine_id, name, provider_model, run_id, root, manifest_json, first_seen_at, last_seen_at
        FROM engines
        ORDER BY name, last_seen_at DESC
        """,
    )
    engines_by_name: dict[str, dict[str, Any]] = {}
    raw_to_canonical: dict[str, str] = {}
    for engine in raw_engines:
        raw_to_canonical[engine["engine_id"]] = engine["name"]
        manifest = compact_json(engine.pop("manifest_json"))
        engine["compile_ok"] = manifest.get("compile_ok") if isinstance(manifest, dict) else None
        engine["provider"] = manifest.get("provider") if isinstance(manifest, dict) else None
        engine["model"] = manifest.get("model") if isinstance(manifest, dict) else engine["provider_model"]
        engine["raw_engine_id"] = engine["engine_id"]
        engine["engine_id"] = engine["name"]
        engines_by_name.setdefault(engine["name"], engine)
    engines = list(engines_by_name.values())

    stats = {
        engine["engine_id"]: {"games": 0, "wins": 0, "losses": 0, "draws": 0, "score": 0.0}
        for engine in engines
    }
    for game in rows(
        db,
        """
        SELECT white_engine_id, black_engine_id, result
        FROM games
        WHERE status='finished' AND result IN ('1-0', '0-1', '1/2-1/2')
        """,
    ):
        white = raw_to_canonical.get(game["white_engine_id"], game["white_engine_id"])
        black = raw_to_canonical.get(game["black_engine_id"], game["black_engine_id"])
        if white not in stats or black not in stats:
            continue
        white_score, black_score = RESULT_SCORES[game["result"]]
        record_score(stats[white], white_score)
        record_score(stats[black], black_score)

    standings = []
    for engine in engines:
        stat = stats[engine["engine_id"]]
        standings.append(
            {
                "engine_id": engine["engine_id"],
                "name": engine["name"],
                "provider_model": engine["provider_model"],
                "games": stat["games"],
                "wins": stat["wins"],
                "losses": stat["losses"],
                "draws": stat["draws"],
                "score": stat["score"],
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
    standings.sort(key=lambda item: (-item["score"], -item["wins"], -item["draws"], item["name"]))

    games = rows(
        db,
        """
        SELECT
            g.game_id, g.white_engine_id, g.black_engine_id,
            white.name AS white_name, black.name AS black_name,
            g.scheduled_at, g.started_at, g.finished_at, g.status, g.result, g.reason,
            g.pgn, g.time_control_json, g.opening_moves, g.opening_fen, g.opening_source,
            g.opening_skip_reason, g.white_clock_ms, g.black_clock_ms,
            g.result_source, g.forfeiting_engine_id, g.migration_note
        FROM games g
        JOIN engines white ON white.engine_id = g.white_engine_id
        JOIN engines black ON black.engine_id = g.black_engine_id
        WHERE g.status != 'ignored'
        ORDER BY COALESCE(g.finished_at, g.started_at, g.scheduled_at) DESC
        """,
    )

    game_ids = [game["game_id"] for game in games]
    moves_by_game: dict[str, list[dict[str, Any]]] = {game_id: [] for game_id in game_ids}
    for move in rows(
        db,
        """
        SELECT game_id, ply, engine_id, move_uci, fen_before, fen_after, elapsed_ms, clock_ms
        FROM moves
        ORDER BY game_id, ply
        """,
    ):
        move["raw_engine_id"] = move["engine_id"]
        move["engine_id"] = raw_to_canonical.get(move["engine_id"], move["engine_id"])
        moves_by_game.setdefault(move["game_id"], []).append(move)

    errors_by_game: dict[str, list[dict[str, Any]]] = {game_id: [] for game_id in game_ids}
    for error in rows(
        db,
        """
        SELECT game_id, engine_id, message, created_at
        FROM game_errors
        ORDER BY id
        """,
    ):
        error["raw_engine_id"] = error["engine_id"]
        error["engine_id"] = raw_to_canonical.get(error["engine_id"], error["engine_id"]) if error["engine_id"] else None
        errors_by_game.setdefault(error["game_id"], []).append(error)

    for game in games:
        game["raw_white_engine_id"] = game["white_engine_id"]
        game["raw_black_engine_id"] = game["black_engine_id"]
        game["white_engine_id"] = raw_to_canonical.get(game["white_engine_id"], game["white_engine_id"])
        game["black_engine_id"] = raw_to_canonical.get(game["black_engine_id"], game["black_engine_id"])
        game["forfeiting_engine_id"] = (
            raw_to_canonical.get(game["forfeiting_engine_id"], game["forfeiting_engine_id"])
            if game["forfeiting_engine_id"]
            else None
        )
        game["time_control"] = compact_json(game.pop("time_control_json"))
        game["moves"] = moves_by_game.get(game["game_id"], [])
        game["errors"] = errors_by_game.get(game["game_id"], [])

    payload = {
        "exported_at": datetime.now(UTC).isoformat(),
        "source_db": str(db_path),
        "summary": {
            "engines": len(engines),
            "games": len(games),
            "moves": sum(len(game["moves"]) for game in games),
            "finished": sum(1 for game in games if game["status"] == "finished"),
            "failed": sum(1 for game in games if game["status"] == "failed"),
            "ignored": int(db.execute("SELECT COUNT(*) FROM games WHERE status='ignored'").fetchone()[0]),
            "migrated_forfeits": sum(1 for game in games if game.get("result_source") == "migrated_forfeit"),
        },
        "engines": engines,
        "standings": standings,
        "games": games,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"Exported {len(games)} games to {out_path}")


def record_score(stat: dict[str, Any], score: float) -> None:
    stat["games"] += 1
    stat["score"] += score
    if score == 1.0:
        stat["wins"] += 1
    elif score == 0.0:
        stat["losses"] += 1
    else:
        stat["draws"] += 1


if __name__ == "__main__":
    main()
