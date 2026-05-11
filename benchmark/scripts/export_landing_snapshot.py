from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.scripts.sync_supabase import infer_provider

DEFAULT_DB = ROOT / "results" / "competition.sqlite3"
DEFAULT_LEADERBOARD = ROOT / "results" / "elo_leaderboard.json"
DEFAULT_OUTPUT = ROOT / "benchmark" / "public" / "data" / "landing-data.json"
LLM_EXCLUDED_PROVIDERS = {"stockfish", "megalodon"}
PROVIDER_META = {
    "anthropic": {"logo": "/assets/anthropic.svg", "accent": "#d89f72"},
    "deepseek": {"logo": "/assets/deepseek.svg", "accent": "#6f8dff"},
    "gemini": {"logo": "/assets/gemini.svg", "accent": "#78c7ff"},
    "kimi": {"logo": "/assets/kimi.svg", "accent": "#8be7c0"},
    "megalodon": {"logo": "/assets/megalodon.svg", "accent": "#f3d36b"},
    "openai": {"logo": "/assets/openai.svg", "accent": "#70e6a4"},
    "stockfish": {"logo": "/assets/stockfish.svg", "accent": "#78c7ff"},
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the small static ChessBench landing snapshot.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--leaderboard", type=Path, default=DEFAULT_LEADERBOARD)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    if not args.leaderboard.exists():
        raise SystemExit(f"Leaderboard not found: {args.leaderboard}")
    if not args.db.exists():
        raise SystemExit(f"Competition database not found: {args.db}")

    snapshot = build_snapshot(args.db, args.leaderboard)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote static landing snapshot to {args.output}")
    return 0


def build_snapshot(db_path: Path, leaderboard_path: Path) -> dict[str, Any]:
    payload = json.loads(leaderboard_path.read_text(encoding="utf-8"))
    leaderboard = [normalize_row(row) for row in payload.get("leaderboard", [])]
    generated_at = payload.get("generated_at") or datetime.now(UTC).isoformat()

    with sqlite3.connect(db_path) as db:
        summary_row = db.execute(
            """
            SELECT
              COUNT(*) AS total_games,
              SUM(CASE WHEN status = 'finished' THEN 1 ELSE 0 END) AS finished_games,
              MAX(finished_at) AS latest_finished_at
            FROM games
            """
        ).fetchone()
        moves = db.execute("SELECT COUNT(*) FROM moves").fetchone()[0]

    llm_rows = [row for row in leaderboard if row.get("provider") not in LLM_EXCLUDED_PROVIDERS]
    return {
        "generated_at": generated_at,
        "summary": {
            "latest_finished_at": summary_row[2],
            "finished_games": int(summary_row[1] or 0),
            "total_games": int(summary_row[0] or 0),
            "llm_models": len(llm_rows),
            "generated_engines": len(llm_rows),
            "moves": int(moves or 0),
        },
        "leaderboard": leaderboard,
    }


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    provider = infer_provider(row.get("provider_model"))
    meta = PROVIDER_META.get(provider, {})
    return {
        **row,
        "provider": provider,
        "model": row.get("provider_model"),
        "logo": meta.get("logo"),
        "accent": meta.get("accent"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
