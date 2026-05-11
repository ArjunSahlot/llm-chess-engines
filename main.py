from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness.config import provider_defaults
from harness.runner import GenerationRunner
from harness.types import RunConfig
from competition.models import TimeControl
from competition.runner import CompetitionRunner

from dotenv import load_dotenv
load_dotenv()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark LLMs by generating C++ chess engines.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Run one engine-generation attempt.")
    generate.add_argument("--provider", required=True, help="Provider name, e.g. openai, anthropic, gemini, deepseek, kimi.")
    generate.add_argument("--model", required=True, help="Provider model identifier.")
    generate.add_argument("--run-id", required=True, help="Deterministic run id under generations/[provider-model]/.")
    generate.add_argument("--api-key-env", help="Environment variable containing the provider API key.")
    generate.add_argument("--base-url", help="Optional OpenAI-compatible base URL.")
    generate.add_argument("--temperature", type=float, default=0.2)
    generate.add_argument("--max-turns", type=int, default=20)
    generate.add_argument("--max-output-tokens", type=int, default=64000)
    generate.add_argument("--no-stream", action="store_true", help="Disable provider streaming when supported.")
    generate.add_argument("--timeout-seconds", type=int, default=60)
    generate.add_argument("--root", type=Path, default=Path("generations"))

    compete = subparsers.add_parser("compete", help="Run persistent round-robin games between compiled generated engines.")
    compete.add_argument("--generations-root", type=Path, default=Path("generations"))
    compete.add_argument("--results-db", type=Path, default=Path("results/competition.sqlite3"))
    compete.add_argument("--forever", action="store_true", help="Keep polling for engines and playing games forever.")
    compete.add_argument("--max-games", type=int, help="Stop after this many games. Omit with --forever for continuous play.")
    compete.add_argument(
        "--time-control",
        action="append",
        help="Repeatable time control to cycle, e.g. movetime:50, movetime:200, clock:60000+500, or 60000+500.",
    )
    compete.add_argument("--movetime-ms", type=int, default=100, help="Fixed per-move search time when no clock is configured.")
    compete.add_argument("--clock-ms", type=int, help="Initial clock per side. Enables clock-based go commands.")
    compete.add_argument("--increment-ms", type=int, default=0)
    compete.add_argument("--move-overhead-ms", type=int, default=20)
    compete.add_argument("--openings-file", type=Path, default=Path("competition/openings.txt"))
    compete.add_argument("--no-openings", action="store_true", help="Disable opening randomization.")
    compete.add_argument("--max-plies", type=int, default=240)
    compete.add_argument("--poll-seconds", type=float, default=5.0)
    compete.add_argument("--handshake-timeout-seconds", type=float, default=5.0)
    compete.add_argument("--move-timeout-seconds", type=float, default=10.0)

    leaderboard = subparsers.add_parser("leaderboard", help="Open the ELO leaderboard TUI and save leaderboard files.")
    leaderboard.add_argument("--results-db", type=Path, default=Path("results/competition.sqlite3"))
    leaderboard.add_argument("--output-dir", type=Path, default=Path("results"))
    leaderboard.add_argument(
        "--anchor",
        action="append",
        default=[],
        help="Known model ELO as name=elo, provider_model=elo, run_id=elo, or engine_id=elo. Repeatable.",
    )
    leaderboard.add_argument("--no-tui", action="store_true", help="Write leaderboard files without opening the TUI.")

    sync_supabase = subparsers.add_parser("sync-supabase", help="Force-push local SQLite competition results to Supabase.")
    sync_supabase.add_argument("--db", type=Path, default=Path("results/competition.sqlite3"))
    sync_supabase.add_argument("--leaderboard", type=Path, default=Path("results/elo_leaderboard.json"))
    sync_supabase.add_argument("--batch-size", type=int, default=500)
    sync_supabase.add_argument("--dry-run", action="store_true")
    sync_supabase.add_argument("--include-uci", action="store_true", help="Also sync raw UCI event lines.")

    landing_snapshot = subparsers.add_parser("export-landing-snapshot", help="Export the small static benchmark landing snapshot.")
    landing_snapshot.add_argument("--db", type=Path, default=Path("results/competition.sqlite3"))
    landing_snapshot.add_argument("--leaderboard", type=Path, default=Path("results/elo_leaderboard.json"))
    landing_snapshot.add_argument("--output", type=Path, default=Path("benchmark/src/core/landing-data.json"))
    return parser


def run_generate(args: argparse.Namespace) -> int:
    api_key_env, base_url = provider_defaults(args.provider)
    config = RunConfig(
        provider=args.provider,
        model=args.model,
        run_id=args.run_id,
        api_key_env=args.api_key_env or api_key_env,
        base_url=args.base_url or base_url,
        temperature=args.temperature,
        max_turns=args.max_turns,
        max_output_tokens=args.max_output_tokens,
        stream=not args.no_stream,
        timeout_seconds=args.timeout_seconds,
        root=args.root,
    )
    manifest = GenerationRunner(config).run()
    print(json.dumps(manifest.to_dict(), indent=2))
    return 0 if manifest.compile_ok else 1


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "generate":
        return run_generate(args)
    if args.command == "compete":
        if args.time_control:
            time_controls = [TimeControl.parse(value, move_overhead_ms=args.move_overhead_ms) for value in args.time_control]
        else:
            time_controls = [
                TimeControl(
                    movetime_ms=args.movetime_ms,
                    init_ms=args.clock_ms,
                    increment_ms=args.increment_ms,
                    move_overhead_ms=args.move_overhead_ms,
                )
            ]
        forever = args.forever or args.max_games is None
        played = CompetitionRunner(
            generations_root=args.generations_root,
            results_db=args.results_db,
            time_controls=time_controls,
            openings_file=None if args.no_openings else args.openings_file,
            max_plies=args.max_plies,
            poll_seconds=args.poll_seconds,
            handshake_timeout_seconds=args.handshake_timeout_seconds,
            move_timeout_seconds=args.move_timeout_seconds,
        ).run(max_games=args.max_games, forever=forever)
        print(f"played {played} game(s)")
        return 0
    if args.command == "leaderboard":
        from leaderboard_tui import run as run_leaderboard

        return run_leaderboard(args)
    if args.command == "sync-supabase":
        from benchmark.scripts.sync_supabase import main as sync_supabase_main

        argv = [
            "--db",
            str(args.db),
            "--leaderboard",
            str(args.leaderboard),
            "--batch-size",
            str(args.batch_size),
        ]
        if args.dry_run:
            argv.append("--dry-run")
        if args.include_uci:
            argv.append("--include-uci")
        return sync_supabase_main(argv)
    if args.command == "export-landing-snapshot":
        from benchmark.scripts.export_landing_snapshot import main as export_landing_snapshot_main

        return export_landing_snapshot_main(
            ["--db", str(args.db), "--leaderboard", str(args.leaderboard), "--output", str(args.output)]
        )
    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
