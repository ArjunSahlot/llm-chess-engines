from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from competition.store import CompetitionStore, now_iso


@dataclass(frozen=True, slots=True)
class MigrationSummary:
    fixed_failed_games: int
    ignored_failed_games: int
    annotated_finished_games: int
    backup_path: Path | None


def migrate_results_db(db_path: Path, create_backup: bool = True) -> MigrationSummary:
    backup_path = _backup(db_path) if create_backup and db_path.exists() else None
    store = CompetitionStore(db_path)
    try:
        fixed = _migrate_failed_games(store.db)
        annotated = _annotate_finished_games(store.db)
        store._rebuild_standings()
        store.db.commit()
        ignored = int(
            store.db.execute(
                "SELECT COUNT(*) FROM games WHERE status='ignored' AND result_source='migration_ignored'"
            ).fetchone()[0]
        )
        return MigrationSummary(
            fixed_failed_games=fixed,
            ignored_failed_games=ignored,
            annotated_finished_games=annotated,
            backup_path=backup_path,
        )
    finally:
        store.close()


def inferred_failed_engine_sql() -> str:
    return """
    COALESCE(
        (
            SELECT game_errors.engine_id
            FROM game_errors
            WHERE game_errors.game_id = games.game_id
              AND game_errors.engine_id IN (games.white_engine_id, games.black_engine_id)
            ORDER BY game_errors.id DESC
            LIMIT 1
        ),
        (
            SELECT uci_events.engine_id
            FROM uci_events
            WHERE uci_events.game_id = games.game_id
              AND uci_events.direction = 'in'
              AND uci_events.line LIKE 'go %'
              AND uci_events.engine_id IN (games.white_engine_id, games.black_engine_id)
            ORDER BY uci_events.id DESC
            LIMIT 1
        ),
        (
            SELECT uci_events.engine_id
            FROM uci_events
            WHERE uci_events.game_id = games.game_id
              AND uci_events.direction = 'in'
              AND uci_events.line != 'quit'
              AND uci_events.engine_id IN (games.white_engine_id, games.black_engine_id)
            ORDER BY uci_events.id DESC
            LIMIT 1
        )
    )
    """


def _migrate_failed_games(db: sqlite3.Connection) -> int:
    rows = db.execute(
        f"""
        SELECT
            games.game_id,
            games.white_engine_id,
            games.black_engine_id,
            games.reason,
            {inferred_failed_engine_sql()} AS failed_engine_id
        FROM games
        WHERE status='failed'
        """
    ).fetchall()
    fixed = 0
    ts = now_iso()
    for row in rows:
        failed_engine_id = row["failed_engine_id"]
        if failed_engine_id == row["white_engine_id"]:
            result = "0-1"
        elif failed_engine_id == row["black_engine_id"]:
            result = "1-0"
        else:
            db.execute(
                """
                UPDATE games
                SET status='ignored',
                    result=NULL,
                    result_source='migration_ignored',
                    migration_note=?,
                    finished_at=COALESCE(finished_at, ?)
                WHERE game_id=?
                """,
                ("could not infer forfeiting engine for failed game", ts, row["game_id"]),
            )
            continue

        reason = f"migrated forfeit: {row['reason'] or 'failed game'}"
        db.execute(
            """
            UPDATE games
            SET status='finished',
                result=?,
                reason=?,
                result_source='migrated_forfeit',
                forfeiting_engine_id=?,
                migration_note='converted failed game to forfeit from recorded UCI/error events',
                finished_at=COALESCE(finished_at, ?)
            WHERE game_id=?
            """,
            (result, reason, failed_engine_id, ts, row["game_id"]),
        )
        fixed += 1
    return fixed


def _annotate_finished_games(db: sqlite3.Connection) -> int:
    rows = db.execute(
        """
        SELECT game_id, white_engine_id, black_engine_id, result, reason, result_source, forfeiting_engine_id
        FROM games
        WHERE status='finished' AND result IN ('1-0', '0-1', '1/2-1/2')
        """
    ).fetchall()
    annotated = 0
    for row in rows:
        if row["result_source"]:
            continue
        reason = (row["reason"] or "").lower()
        forfeiting_engine_id = None
        result_source = "game"
        if any(token in reason for token in ("engine error", "illegal move", "invalid move", "null bestmove", "flagged")):
            result_source = "forfeit"
            if row["result"] == "1-0":
                forfeiting_engine_id = row["black_engine_id"]
            elif row["result"] == "0-1":
                forfeiting_engine_id = row["white_engine_id"]
        db.execute(
            """
            UPDATE games
            SET result_source=?, forfeiting_engine_id=?
            WHERE game_id=?
            """,
            (result_source, forfeiting_engine_id, row["game_id"]),
        )
        annotated += 1
    return annotated


def _backup(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.bak-{stamp}")
    shutil.copy2(db_path, backup_path)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(db_path) + suffix)
        if sidecar.exists():
            shutil.copy2(sidecar, Path(str(backup_path) + suffix))
    return backup_path
