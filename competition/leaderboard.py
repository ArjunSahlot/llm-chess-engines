from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable


DEFAULT_RATING = 1500.0
ELO_SCALE = 400.0 / math.log(10)
RESULT_SCORES = {
    "1-0": (1.0, 0.0),
    "0-1": (0.0, 1.0),
    "1/2-1/2": (0.5, 0.5),
}


@dataclass(frozen=True, slots=True)
class EngineRecord:
    engine_id: str
    name: str
    provider_model: str
    run_id: str


@dataclass(slots=True)
class PlayerStats:
    games: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    score: float = 0.0
    white_games: int = 0
    white_score: float = 0.0
    black_games: int = 0
    black_score: float = 0.0


@dataclass(frozen=True, slots=True)
class GameResult:
    white_engine_id: str
    black_engine_id: str
    white_score: float
    black_score: float


@dataclass(frozen=True, slots=True)
class LeaderboardRow:
    rank: int
    engine_id: str
    name: str
    provider_model: str
    run_id: str
    elo: int
    anchored: bool
    games: int
    wins: int
    losses: int
    draws: int
    score: float
    score_pct: float
    win_pct: float
    draw_pct: float
    loss_pct: float
    white_games: int
    white_score: float
    black_games: int
    black_score: float
    avg_opponent_elo: int | None


def load_competition_data(db_path: Path) -> tuple[dict[str, EngineRecord], list[GameResult], dict[str, PlayerStats]]:
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        engine_rows = db.execute("SELECT engine_id, name, provider_model, run_id FROM engines").fetchall()
        raw_engines = {
            row["engine_id"]: EngineRecord(
                engine_id=row["engine_id"],
                name=row["name"],
                provider_model=row["provider_model"],
                run_id=row["run_id"],
            )
            for row in engine_rows
        }
        rows = db.execute(
            f"""
            SELECT
                games.white_engine_id,
                games.black_engine_id,
                games.status,
                games.result,
                games.reason,
                COALESCE(
                    (SELECT engine_id FROM game_errors WHERE game_errors.game_id = games.game_id AND engine_id IS NOT NULL ORDER BY id DESC LIMIT 1),
                    games.forfeiting_engine_id
                ) AS failed_engine_id
            FROM games
            WHERE (status='finished' AND result IN ('1-0', '0-1', '1/2-1/2'))
               OR status='failed'
            """
        ).fetchall()
    finally:
        db.close()

    engines = _collapse_engines_by_name(raw_engines.values())
    id_to_name = {engine_id: engine.name for engine_id, engine in raw_engines.items()}
    stats = {engine_id: PlayerStats() for engine_id in engines}
    games: list[GameResult] = []
    for row in rows:
        white_score, black_score = _scores_from_row(row)
        if white_score is None or black_score is None:
            continue
        white = id_to_name.get(row["white_engine_id"])
        black = id_to_name.get(row["black_engine_id"])
        if white not in stats or black not in stats:
            continue
        games.append(GameResult(white, black, white_score, black_score))
        _record_stats(stats[white], white_score, white=True)
        _record_stats(stats[black], black_score, white=False)
    return engines, games, stats


def _scores_from_row(row: sqlite3.Row) -> tuple[float | None, float | None]:
    if row["status"] == "finished":
        return RESULT_SCORES.get(row["result"], (None, None))
    reason = (row["reason"] or "").lower()
    if not any(token in reason for token in ("timed out", "engine exited", "broken pipe", "engine error")):
        return None, None
    failed_engine_id = row["failed_engine_id"]
    if failed_engine_id == row["white_engine_id"]:
        return 0.0, 1.0
    if failed_engine_id == row["black_engine_id"]:
        return 1.0, 0.0
    return None, None


def load_anchors(path: Path) -> dict[str, float]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    anchors: dict[str, float] = {}
    for key, value in payload.items():
        try:
            anchors[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return anchors


def save_anchors(path: Path, anchors: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(anchors.items())), indent=2) + "\n", encoding="utf-8")


def build_leaderboard(db_path: Path, anchors: dict[str, float] | None = None) -> list[LeaderboardRow]:
    engines, games, stats = load_competition_data(db_path)
    resolved_anchors = resolve_anchors(engines.values(), anchors or {})
    ratings = estimate_elos(engines.keys(), games, resolved_anchors)

    opponent_totals: dict[str, list[float]] = {engine_id: [] for engine_id in engines}
    for game in games:
        opponent_totals[game.white_engine_id].append(ratings[game.black_engine_id])
        opponent_totals[game.black_engine_id].append(ratings[game.white_engine_id])

    rows: list[LeaderboardRow] = []
    ordered = sorted(engines.values(), key=lambda engine: (-ratings[engine.engine_id], engine.name))
    for index, engine in enumerate(ordered, start=1):
        player = stats[engine.engine_id]
        games_played = player.games
        opponents = opponent_totals[engine.engine_id]
        rows.append(
            LeaderboardRow(
                rank=index,
                engine_id=engine.engine_id,
                name=engine.name,
                provider_model=engine.provider_model,
                run_id=engine.run_id,
                elo=round(ratings[engine.engine_id]),
                anchored=engine.engine_id in resolved_anchors,
                games=games_played,
                wins=player.wins,
                losses=player.losses,
                draws=player.draws,
                score=round(player.score, 1),
                score_pct=_pct(player.score, games_played),
                win_pct=_pct(player.wins, games_played),
                draw_pct=_pct(player.draws, games_played),
                loss_pct=_pct(player.losses, games_played),
                white_games=player.white_games,
                white_score=round(player.white_score, 1),
                black_games=player.black_games,
                black_score=round(player.black_score, 1),
                avg_opponent_elo=round(sum(opponents) / len(opponents)) if opponents else None,
            )
        )
    return rows


def estimate_elos(
    engine_ids: Iterable[str],
    games: list[GameResult],
    anchors: dict[str, float] | None = None,
    iterations: int = 200,
) -> dict[str, float]:
    ids = sorted(engine_ids)
    anchor_values = {engine_id: float(value) for engine_id, value in (anchors or {}).items() if engine_id in ids}
    ratings = {engine_id: anchor_values.get(engine_id, DEFAULT_RATING) for engine_id in ids}
    if not games:
        return ratings

    for _ in range(iterations):
        deltas = {engine_id: 0.0 for engine_id in ids}
        weights = {engine_id: 0.0 for engine_id in ids}
        for game in games:
            white = game.white_engine_id
            black = game.black_engine_id
            expected_white = expected_score(ratings[white], ratings[black])
            variance = max(0.0001, expected_white * (1.0 - expected_white))
            error = game.white_score - expected_white
            deltas[white] += error
            deltas[black] -= error
            weights[white] += variance
            weights[black] += variance

        max_change = 0.0
        for engine_id in ids:
            if engine_id in anchor_values or weights[engine_id] == 0:
                ratings[engine_id] = anchor_values.get(engine_id, ratings[engine_id])
                continue
            change = ELO_SCALE * deltas[engine_id] / weights[engine_id]
            change = max(-50.0, min(50.0, change))
            ratings[engine_id] += change
            max_change = max(max_change, abs(change))

        if not anchor_values:
            mean = sum(ratings.values()) / len(ratings)
            ratings = {engine_id: rating + DEFAULT_RATING - mean for engine_id, rating in ratings.items()}

        if max_change < 0.01:
            break
    return ratings


def expected_score(player_elo: float, opponent_elo: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((opponent_elo - player_elo) / 400.0))


def resolve_anchors(engines: Iterable[EngineRecord], anchors: dict[str, float]) -> dict[str, float]:
    resolved: dict[str, float] = {}
    records = list(engines)
    for key, value in anchors.items():
        normalized = key.lower()
        for engine in records:
            engine_keys = (engine.engine_id, engine.name, engine.provider_model, engine.run_id)
            if normalized in {engine_key.lower() for engine_key in engine_keys}:
                resolved[engine.engine_id] = float(value)
    return resolved


def _collapse_engines_by_name(engines: Iterable[EngineRecord]) -> dict[str, EngineRecord]:
    collapsed: dict[str, EngineRecord] = {}
    for engine in sorted(engines, key=lambda item: (item.name, item.engine_id)):
        collapsed.setdefault(
            engine.name,
            EngineRecord(
                engine_id=engine.name,
                name=engine.name,
                provider_model=engine.provider_model,
                run_id=engine.run_id,
            ),
        )
    return collapsed


def save_leaderboard(output_dir: Path, rows: list[LeaderboardRow], anchors: dict[str, float]) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    anchors_path = output_dir / "elo_anchors.json"
    json_path = output_dir / "elo_leaderboard.json"
    markdown_path = output_dir / "elo_leaderboard.md"
    save_anchors(anchors_path, anchors)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "anchors": dict(sorted(anchors.items())),
        "leaderboard": [asdict(row) for row in rows],
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_leaderboard_markdown(rows), encoding="utf-8")
    return anchors_path, json_path, markdown_path


def _record_stats(stats: PlayerStats, score: float, white: bool) -> None:
    stats.games += 1
    stats.score += score
    if score == 1.0:
        stats.wins += 1
    elif score == 0.0:
        stats.losses += 1
    else:
        stats.draws += 1
    if white:
        stats.white_games += 1
        stats.white_score += score
    else:
        stats.black_games += 1
        stats.black_score += score


def _pct(value: float, games: int) -> float:
    if games == 0:
        return 0.0
    return round(100.0 * value / games, 1)


def _leaderboard_markdown(rows: list[LeaderboardRow]) -> str:
    lines = [
        "# ELO Leaderboard",
        "",
        "| Rank | Engine | ELO | Games | W | L | D | Score | Score% | Avg Opp | Anchor |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for row in rows:
        avg_opp = "" if row.avg_opponent_elo is None else str(row.avg_opponent_elo)
        anchor = "yes" if row.anchored else ""
        lines.append(
            f"| {row.rank} | {row.name} | {row.elo} | {row.games} | {row.wins} | {row.losses} | "
            f"{row.draws} | {row.score:g} | {row.score_pct:.1f} | {avg_opp} | {anchor} |"
        )
    return "\n".join(lines) + "\n"
