from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from competition.models import CompetitionConfig, Engine, Opening, TimeControl


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class CompetitionStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def close(self) -> None:
        with self.lock:
            self.db.close()

    def migrate(self) -> None:
        with self.lock:
            self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS engines (
                engine_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                provider_model TEXT NOT NULL,
                run_id TEXT NOT NULL,
                root TEXT NOT NULL,
                command_json TEXT NOT NULL,
                manifest_json TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                white_engine_id TEXT NOT NULL,
                black_engine_id TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                status TEXT NOT NULL,
                result TEXT,
                reason TEXT,
                pgn TEXT,
                config_json TEXT NOT NULL,
                time_control_json TEXT,
                opening_moves TEXT,
                opening_fen TEXT,
                opening_source TEXT,
                white_clock_ms INTEGER,
                black_clock_ms INTEGER,
                FOREIGN KEY (white_engine_id) REFERENCES engines(engine_id),
                FOREIGN KEY (black_engine_id) REFERENCES engines(engine_id)
            );
            CREATE TABLE IF NOT EXISTS moves (
                game_id TEXT NOT NULL,
                ply INTEGER NOT NULL,
                engine_id TEXT NOT NULL,
                move_uci TEXT NOT NULL,
                fen_before TEXT NOT NULL,
                fen_after TEXT NOT NULL,
                elapsed_ms INTEGER,
                clock_ms INTEGER,
                created_at TEXT NOT NULL,
                PRIMARY KEY (game_id, ply),
                FOREIGN KEY (game_id) REFERENCES games(game_id),
                FOREIGN KEY (engine_id) REFERENCES engines(engine_id)
            );
            CREATE TABLE IF NOT EXISTS uci_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                engine_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                line TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (game_id) REFERENCES games(game_id),
                FOREIGN KEY (engine_id) REFERENCES engines(engine_id)
            );
            CREATE TABLE IF NOT EXISTS game_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                engine_id TEXT,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (game_id) REFERENCES games(game_id)
            );
            CREATE TABLE IF NOT EXISTS standings (
                engine_id TEXT PRIMARY KEY,
                games INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                losses INTEGER NOT NULL DEFAULT 0,
                draws INTEGER NOT NULL DEFAULT 0,
                score REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (engine_id) REFERENCES engines(engine_id)
            );
            CREATE INDEX IF NOT EXISTS idx_games_pair ON games(white_engine_id, black_engine_id, status);
            CREATE INDEX IF NOT EXISTS idx_moves_game ON moves(game_id, ply);
            CREATE INDEX IF NOT EXISTS idx_uci_game ON uci_events(game_id);
            """
        )
            self._add_column("games", "time_control_json", "TEXT")
            self._add_column("games", "opening_moves", "TEXT")
            self._add_column("games", "opening_fen", "TEXT")
            self._add_column("games", "opening_source", "TEXT")
            self.db.commit()

    def _add_column(self, table: str, name: str, kind: str) -> None:
        columns = {row["name"] for row in self.db.execute(f"PRAGMA table_info({table})")}
        if name not in columns:
            self.db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")

    def upsert_engine(self, engine: Engine) -> None:
        ts = now_iso()
        manifest_json = json.dumps(engine.manifest, sort_keys=True) if engine.manifest is not None else None
        with self.lock:
            self.db.execute(
            """
            INSERT INTO engines(engine_id, name, provider_model, run_id, root, command_json, manifest_json, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(engine_id) DO UPDATE SET
                name=excluded.name,
                root=excluded.root,
                command_json=excluded.command_json,
                manifest_json=excluded.manifest_json,
                last_seen_at=excluded.last_seen_at
            """,
            (
                engine.engine_id,
                engine.name,
                engine.provider_model,
                engine.run_id,
                str(engine.root),
                json.dumps(engine.command),
                manifest_json,
                ts,
                ts,
            ),
        )
            self.db.commit()

    def create_game(
        self,
        game_id: str,
        white: Engine,
        black: Engine,
        config: CompetitionConfig,
        time_control: TimeControl,
        opening: Opening | None,
        opening_fen: str,
    ) -> None:
        with self.lock:
            self.db.execute(
            """
            INSERT INTO games(
                game_id, white_engine_id, black_engine_id, scheduled_at, status, config_json,
                time_control_json, opening_moves, opening_fen, opening_source, white_clock_ms, black_clock_ms
            )
            VALUES (?, ?, ?, ?, 'scheduled', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                game_id,
                white.engine_id,
                black.engine_id,
                now_iso(),
                json.dumps(config.to_dict(), sort_keys=True),
                json.dumps(time_control.to_dict(), sort_keys=True),
                opening.label if opening is not None else "",
                opening_fen,
                opening.source if opening is not None else "",
                time_control.init_ms,
                time_control.init_ms,
            ),
        )
            self.db.commit()

    def start_game(self, game_id: str) -> None:
        with self.lock:
            self.db.execute("UPDATE games SET status='running', started_at=? WHERE game_id=?", (now_iso(), game_id))
            self.db.commit()

    def finish_game(self, game_id: str, result: str, reason: str, pgn: str, white_clock_ms: int | None, black_clock_ms: int | None) -> None:
        with self.lock:
            self.db.execute(
            """
            UPDATE games SET status='finished', finished_at=?, result=?, reason=?, pgn=?, white_clock_ms=?, black_clock_ms=?
            WHERE game_id=?
            """,
            (now_iso(), result, reason, pgn, white_clock_ms, black_clock_ms, game_id),
        )
            self._rebuild_standings()
            self.db.commit()

    def fail_game(self, game_id: str, reason: str, pgn: str = "") -> None:
        with self.lock:
            self.db.execute(
            "UPDATE games SET status='failed', finished_at=?, reason=?, pgn=? WHERE game_id=?",
            (now_iso(), reason, pgn, game_id),
        )
            self.db.commit()

    def record_move(
        self,
        game_id: str,
        ply: int,
        engine_id: str,
        move_uci: str,
        fen_before: str,
        fen_after: str,
        elapsed_ms: int | None,
        clock_ms: int | None,
    ) -> None:
        with self.lock:
            self.db.execute(
            """
            INSERT OR REPLACE INTO moves(game_id, ply, engine_id, move_uci, fen_before, fen_after, elapsed_ms, clock_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (game_id, ply, engine_id, move_uci, fen_before, fen_after, elapsed_ms, clock_ms, now_iso()),
        )
            self.db.commit()

    def record_uci(self, game_id: str, engine_id: str, direction: str, line: str) -> None:
        with self.lock:
            self.db.execute(
            "INSERT INTO uci_events(game_id, engine_id, direction, line, created_at) VALUES (?, ?, ?, ?, ?)",
            (game_id, engine_id, direction, line, now_iso()),
        )
            self.db.commit()

    def record_error(self, game_id: str, engine_id: str | None, message: str) -> None:
        with self.lock:
            self.db.execute(
            "INSERT INTO game_errors(game_id, engine_id, message, created_at) VALUES (?, ?, ?, ?)",
            (game_id, engine_id, message, now_iso()),
        )
            self.db.commit()

    def pair_counts(self) -> dict[tuple[str, str], int]:
        with self.lock:
            rows = self.db.execute(
                """
                SELECT white_engine_id, black_engine_id, COUNT(*) AS n
                FROM games
                WHERE status IN ('finished', 'failed', 'running', 'scheduled')
                GROUP BY white_engine_id, black_engine_id
                """
            ).fetchall()
        return {(row["white_engine_id"], row["black_engine_id"]): int(row["n"]) for row in rows}

    def game_count(self) -> int:
        with self.lock:
            return int(self.db.execute("SELECT COUNT(*) FROM games").fetchone()[0])

    def _rebuild_standings(self) -> None:
        self.db.execute("DELETE FROM standings")
        rows = self.db.execute("SELECT white_engine_id, black_engine_id, result FROM games WHERE status='finished'").fetchall()
        scores: dict[str, dict[str, Any]] = {}
        for row in rows:
            white = row["white_engine_id"]
            black = row["black_engine_id"]
            for engine_id in (white, black):
                scores.setdefault(engine_id, {"games": 0, "wins": 0, "losses": 0, "draws": 0, "score": 0.0})
                scores[engine_id]["games"] += 1
            if row["result"] == "1-0":
                scores[white]["wins"] += 1
                scores[white]["score"] += 1.0
                scores[black]["losses"] += 1
            elif row["result"] == "0-1":
                scores[black]["wins"] += 1
                scores[black]["score"] += 1.0
                scores[white]["losses"] += 1
            else:
                scores[white]["draws"] += 1
                scores[black]["draws"] += 1
                scores[white]["score"] += 0.5
                scores[black]["score"] += 0.5
        ts = now_iso()
        for engine_id, score in scores.items():
            self.db.execute(
                "INSERT INTO standings(engine_id, games, wins, losses, draws, score, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (engine_id, score["games"], score["wins"], score["losses"], score["draws"], score["score"], ts),
            )
