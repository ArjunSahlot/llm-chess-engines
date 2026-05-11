from __future__ import annotations

import argparse
import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "results" / "competition.sqlite3"
DEFAULT_LEADERBOARD = ROOT / "results" / "elo_leaderboard.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Force-push local ChessBench SQLite results to Supabase.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--leaderboard", type=Path, default=DEFAULT_LEADERBOARD)
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("CHESSBENCH_BATCH_SIZE", "500")))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-uci", action="store_true", help="Sync raw UCI event lines. This can be large.")
    args = parser.parse_args(argv)

    supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not args.dry_run and (not supabase_url or not service_key):
        raise SystemExit("Set NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, or run with --dry-run.")
    if not args.db.exists():
        raise SystemExit(f"Competition database not found: {args.db}")

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row
    client = SupabaseRestClient(supabase_url, service_key, args.dry_run)
    try:
        reset_remote_tables(client)
        raw_to_canonical = sync_engines(db, client, args.batch_size)
        sync_games(db, client, raw_to_canonical, args.batch_size)
        sync_moves(db, client, raw_to_canonical, args.batch_size)
        sync_game_errors(db, client, raw_to_canonical, args.batch_size)
        sync_engine_capabilities(db, client, args.batch_size)
        if args.include_uci:
            sync_uci_events(db, client, raw_to_canonical, args.batch_size)
        if args.leaderboard.exists():
            sync_leaderboard(args.leaderboard, client, args.batch_size)
    finally:
        db.close()
    return 0


class SupabaseRestClient:
    def __init__(self, base_url: str, service_key: str, dry_run: bool) -> None:
        self.base_url = base_url
        self.service_key = service_key
        self.dry_run = dry_run

    def upsert(self, table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
        if not rows:
            return
        if self.dry_run:
            print(f"[dry-run] upsert {len(rows):>5} rows into {table} on {on_conflict}")
            return
        query = urllib.parse.urlencode({"on_conflict": on_conflict})
        url = f"{self.base_url}/rest/v1/{table}?{query}"
        data = json.dumps(rows, separators=(",", ":"), default=str).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"Supabase upsert failed for {table}: {exc.code} {body}") from exc

    def delete_all(self, table: str, required_column: str) -> None:
        if self.dry_run:
            print(f"[dry-run] delete all rows from {table}")
            return
        query = urllib.parse.urlencode({required_column: "not.is.null"})
        url = f"{self.base_url}/rest/v1/{table}?{query}"
        request = urllib.request.Request(
            url,
            method="DELETE",
            headers={
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
                "Prefer": "return=minimal",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"Supabase delete failed for {table}: {exc.code} {body}") from exc


def reset_remote_tables(client: SupabaseRestClient) -> None:
    for table, required_column in (
        ("chessbench_uci_events", "id"),
        ("chessbench_game_errors", "id"),
        ("chessbench_moves", "game_id"),
        ("chessbench_engine_capabilities", "raw_engine_id"),
        ("chessbench_games", "game_id"),
        ("chessbench_leaderboard_entries", "snapshot_id"),
        ("chessbench_leaderboard_snapshots", "snapshot_id"),
        ("chessbench_engines", "raw_engine_id"),
    ):
        client.delete_all(table, required_column)


def sync_engines(db: sqlite3.Connection, client: SupabaseRestClient, batch_size: int) -> dict[str, str]:
    engine_rows = []
    raw_to_canonical = {}
    for row in rows(
        db,
        """
        SELECT engine_id, name, provider_model, run_id, root, command_json, manifest_json, first_seen_at, last_seen_at
        FROM engines
        ORDER BY engine_id
        """,
    ):
        manifest = compact_json(row["manifest_json"])
        provider = manifest.get("provider") if isinstance(manifest, dict) else None
        model = manifest.get("model") if isinstance(manifest, dict) else None
        raw_to_canonical[row["engine_id"]] = row["name"]
        engine_rows.append(
            {
                "raw_engine_id": row["engine_id"],
                "canonical_engine_id": row["name"],
                "name": row["name"],
                "provider": provider or infer_provider(row["provider_model"]),
                "provider_model": row["provider_model"],
                "model": model or row["provider_model"],
                "run_id": row["run_id"],
                "root": row["root"],
                "command": compact_json(row["command_json"]),
                "manifest": manifest,
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
            }
        )
    upsert_batches(client, "chessbench_engines", engine_rows, "raw_engine_id", batch_size)
    return raw_to_canonical


def sync_games(
    db: sqlite3.Connection,
    client: SupabaseRestClient,
    raw_to_canonical: dict[str, str],
    batch_size: int,
) -> None:
    game_rows = []
    for row in rows(db, "SELECT * FROM games ORDER BY game_id"):
        game_rows.append(
            {
                "game_id": row["game_id"],
                "white_raw_engine_id": row["white_engine_id"],
                "black_raw_engine_id": row["black_engine_id"],
                "white_engine_id": raw_to_canonical.get(row["white_engine_id"], row["white_engine_id"]),
                "black_engine_id": raw_to_canonical.get(row["black_engine_id"], row["black_engine_id"]),
                "scheduled_at": row["scheduled_at"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "status": row["status"],
                "result": row["result"],
                "reason": row["reason"],
                "pgn": row["pgn"],
                "config": compact_json(row["config_json"]),
                "time_control": compact_json(row["time_control_json"]),
                "opening_moves": split_moves(row["opening_moves"]),
                "opening_fen": row["opening_fen"],
                "opening_source": row["opening_source"],
                "opening_skip_reason": row["opening_skip_reason"],
                "white_clock_ms": row["white_clock_ms"],
                "black_clock_ms": row["black_clock_ms"],
                "result_source": row["result_source"],
                "forfeiting_raw_engine_id": row["forfeiting_engine_id"],
                "forfeiting_engine_id": (
                    raw_to_canonical.get(row["forfeiting_engine_id"], row["forfeiting_engine_id"])
                    if row["forfeiting_engine_id"]
                    else None
                ),
                "migration_note": row["migration_note"],
            }
        )
    upsert_batches(client, "chessbench_games", game_rows, "game_id", batch_size)


def sync_moves(
    db: sqlite3.Connection,
    client: SupabaseRestClient,
    raw_to_canonical: dict[str, str],
    batch_size: int,
) -> None:
    move_rows = []
    for row in rows(db, "SELECT * FROM moves ORDER BY game_id, ply"):
        move_rows.append(
            {
                "game_id": row["game_id"],
                "ply": row["ply"],
                "raw_engine_id": row["engine_id"],
                "engine_id": raw_to_canonical.get(row["engine_id"], row["engine_id"]),
                "move_uci": row["move_uci"],
                "fen_before": row["fen_before"],
                "fen_after": row["fen_after"],
                "elapsed_ms": row["elapsed_ms"],
                "clock_ms": row["clock_ms"],
                "created_at": row["created_at"],
            }
        )
    upsert_batches(client, "chessbench_moves", move_rows, "game_id,ply", batch_size)


def sync_game_errors(
    db: sqlite3.Connection,
    client: SupabaseRestClient,
    raw_to_canonical: dict[str, str],
    batch_size: int,
) -> None:
    error_rows = []
    for row in rows(db, "SELECT * FROM game_errors ORDER BY id"):
        error_rows.append(
            {
                "id": row["id"],
                "game_id": row["game_id"],
                "raw_engine_id": row["engine_id"],
                "engine_id": raw_to_canonical.get(row["engine_id"], row["engine_id"]) if row["engine_id"] else None,
                "message": row["message"],
                "created_at": row["created_at"],
            }
        )
    upsert_batches(client, "chessbench_game_errors", error_rows, "id", batch_size)


def sync_engine_capabilities(db: sqlite3.Connection, client: SupabaseRestClient, batch_size: int) -> None:
    capability_rows = []
    for row in rows(db, "SELECT * FROM engine_capabilities ORDER BY engine_id"):
        capability_rows.append(
            {
                "raw_engine_id": row["engine_id"],
                "supports_openings": bool(row["supports_openings"]),
                "reason": row["reason"],
                "checked_at": row["checked_at"],
            }
        )
    upsert_batches(client, "chessbench_engine_capabilities", capability_rows, "raw_engine_id", batch_size)


def sync_uci_events(
    db: sqlite3.Connection,
    client: SupabaseRestClient,
    raw_to_canonical: dict[str, str],
    batch_size: int,
) -> None:
    event_rows = []
    for row in rows(db, "SELECT * FROM uci_events ORDER BY id"):
        event_rows.append(
            {
                "id": row["id"],
                "game_id": row["game_id"],
                "raw_engine_id": row["engine_id"],
                "engine_id": raw_to_canonical.get(row["engine_id"], row["engine_id"]),
                "direction": row["direction"],
                "line": row["line"],
                "created_at": row["created_at"],
            }
        )
    upsert_batches(client, "chessbench_uci_events", event_rows, "id", batch_size)


def sync_leaderboard(path: Path, client: SupabaseRestClient, batch_size: int) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    generated_at = payload.get("generated_at") or datetime.now(UTC).isoformat()
    snapshot_id = generated_at.replace(":", "").replace(".", "").replace("+", "Z")
    client.upsert(
        "chessbench_leaderboard_snapshots",
        [
            {
                "snapshot_id": snapshot_id,
                "generated_at": generated_at,
                "anchors": payload.get("anchors") or {},
            }
        ],
        "snapshot_id",
    )
    entries = []
    for row in payload.get("leaderboard", []):
        entries.append({"snapshot_id": snapshot_id, **row})
    upsert_batches(client, "chessbench_leaderboard_entries", entries, "snapshot_id,engine_id", batch_size)


def upsert_batches(
    client: SupabaseRestClient,
    table: str,
    items: list[dict[str, Any]],
    on_conflict: str,
    batch_size: int,
) -> None:
    for batch in batched(items, max(1, batch_size)):
        client.upsert(table, batch, on_conflict)


def batched(items: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def rows(db: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    return db.execute(sql).fetchall()


def compact_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def split_moves(value: str | None) -> list[str]:
    return [move for move in (value or "").split() if move]


def infer_provider(provider_model: str | None) -> str:
    value = (provider_model or "").lower()
    for provider in ("openai", "anthropic", "gemini", "deepseek", "kimi", "moonshot", "megalodon", "stockfish"):
        if value.startswith(provider):
            return "kimi" if provider == "moonshot" else provider
    return value.split("-", 1)[0] if value else "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
