from __future__ import annotations

import argparse
import curses
from pathlib import Path

from competition.leaderboard import build_leaderboard, load_anchors, save_leaderboard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an interactive ELO leaderboard from competition results.")
    parser.add_argument("--results-db", type=Path, default=Path("results/competition.sqlite3"))
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument(
        "--anchor",
        action="append",
        default=[],
        help="Known model ELO as name=elo, provider_model=elo, run_id=elo, or engine_id=elo. Repeatable.",
    )
    parser.add_argument("--no-tui", action="store_true", help="Write leaderboard files without opening the TUI.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run(args)


def run(args: argparse.Namespace) -> int:
    anchors_path = args.output_dir / "elo_anchors.json"
    anchors = load_anchors(anchors_path)
    anchors.update(_parse_anchors(args.anchor))

    if not args.results_db.exists():
        raise SystemExit(f"results database not found: {args.results_db}")

    if args.no_tui:
        rows = build_leaderboard(args.results_db, anchors)
        _, json_path, markdown_path = save_leaderboard(args.output_dir, rows, anchors)
        print(f"saved {json_path} and {markdown_path}")
        return 0

    return curses.wrapper(_run_tui, args.results_db, args.output_dir, anchors)


def _run_tui(screen, results_db: Path, output_dir: Path, anchors: dict[str, float]) -> int:
    curses.curs_set(0)
    selected = 0
    message = "e: edit anchor  c: clear anchor  s: save  q: quit"

    while True:
        rows = build_leaderboard(results_db, anchors)
        selected = min(selected, max(0, len(rows) - 1))
        _draw(screen, rows, anchors, selected, message)
        key = screen.getch()
        if key in (ord("q"), 27):
            return 0
        if key in (curses.KEY_UP, ord("k")):
            selected = max(0, selected - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            selected = min(max(0, len(rows) - 1), selected + 1)
        elif key == ord("e") and rows:
            row = rows[selected]
            current = _anchor_for(row, anchors)
            entered = _prompt(screen, f"Known ELO for {row.name}", "" if current is None else str(int(current)))
            if entered:
                try:
                    anchors[row.name] = float(entered)
                    message = f"anchored {row.name} at {float(entered):.0f}"
                except ValueError:
                    message = f"not a number: {entered}"
        elif key == ord("c") and rows:
            removed = _clear_anchor(rows[selected], anchors)
            message = "anchor cleared" if removed else "no anchor set for selected engine"
        elif key == ord("s"):
            rows = build_leaderboard(results_db, anchors)
            _, json_path, markdown_path = save_leaderboard(output_dir, rows, anchors)
            message = f"saved {json_path} and {markdown_path}"


def _draw(screen, rows, anchors: dict[str, float], selected: int, message: str) -> None:
    screen.erase()
    height, width = screen.getmaxyx()
    title = "ChessBench ELO Leaderboard"
    screen.addnstr(0, 0, title, width - 1, curses.A_BOLD)
    screen.addnstr(1, 0, message, width - 1)
    screen.addnstr(3, 0, " #  ELO  Gms  W  L  D  Score%  AvgOpp  Anchor  Engine", width - 1, curses.A_UNDERLINE)

    visible = max(0, height - 6)
    start = max(0, selected - visible + 1)
    for index, row in enumerate(rows[start : start + visible], start=start):
        attr = curses.A_REVERSE if index == selected else curses.A_NORMAL
        anchor = _anchor_for(row, anchors)
        anchor_text = "" if anchor is None else f"{anchor:.0f}"
        avg_opp = "" if row.avg_opponent_elo is None else str(row.avg_opponent_elo)
        line = (
            f"{row.rank:>2} {row.elo:>5} {row.games:>4} {row.wins:>2} {row.losses:>2} {row.draws:>2} "
            f"{row.score_pct:>6.1f} {avg_opp:>7} {anchor_text:>7}  {row.name}"
        )
        screen.addnstr(4 + index - start, 0, line, width - 1, attr)

    footer = f"{len(rows)} engine(s). Outputs: results/elo_leaderboard.json and results/elo_leaderboard.md"
    screen.addnstr(height - 1, 0, footer, width - 1)
    screen.refresh()


def _prompt(screen, label: str, default: str) -> str:
    height, width = screen.getmaxyx()
    curses.echo()
    curses.curs_set(1)
    prompt = f"{label} [{default}]: "
    screen.move(height - 2, 0)
    screen.clrtoeol()
    screen.addnstr(height - 2, 0, prompt, width - 1)
    raw = screen.getstr(height - 2, min(len(prompt), width - 1), 32).decode("utf-8").strip()
    curses.noecho()
    curses.curs_set(0)
    return raw or default


def _parse_anchors(values: list[str]) -> dict[str, float]:
    anchors: dict[str, float] = {}
    for value in values:
        key, sep, raw_elo = value.partition("=")
        if not sep:
            raise SystemExit(f"anchor must be name=elo: {value}")
        try:
            anchors[key.strip()] = float(raw_elo)
        except ValueError as exc:
            raise SystemExit(f"anchor ELO must be numeric: {value}") from exc
    return anchors


def _anchor_for(row, anchors: dict[str, float]) -> float | None:
    for key in (row.name, row.provider_model, row.run_id, row.engine_id):
        if key in anchors:
            return anchors[key]
    return None


def _clear_anchor(row, anchors: dict[str, float]) -> bool:
    removed = False
    for key in (row.name, row.provider_model, row.run_id, row.engine_id):
        if key in anchors:
            del anchors[key]
            removed = True
    return removed


if __name__ == "__main__":
    raise SystemExit(main())
