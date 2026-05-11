from __future__ import annotations

import random
import time
from itertools import permutations
from pathlib import Path

from competition.capabilities import probe_opening_support
from competition.discovery import discover_engines
from competition.game import GameRunner
from competition.models import CompetitionConfig, TimeControl
from competition.openings import OpeningBook
from competition.store import CompetitionStore


CATCH_UP_GAME_MARGIN = 20


class CompetitionRunner:
    def __init__(
        self,
        generations_root: Path = Path("generations"),
        results_db: Path = Path("results/competition.sqlite3"),
        time_control: TimeControl | None = None,
        time_controls: list[TimeControl] | tuple[TimeControl, ...] | None = None,
        openings_file: Path | None = Path("competition/openings.txt"),
        max_plies: int = 240,
        poll_seconds: float = 5.0,
        handshake_timeout_seconds: float = 5.0,
        move_timeout_seconds: float = 10.0,
    ) -> None:
        controls = tuple(time_controls or ([time_control] if time_control is not None else [TimeControl()]))
        self.config = CompetitionConfig(
            generations_root=generations_root,
            results_db=results_db,
            time_controls=controls,
            openings_file=openings_file,
            max_plies=max_plies,
            poll_seconds=poll_seconds,
            handshake_timeout_seconds=handshake_timeout_seconds,
            move_timeout_seconds=move_timeout_seconds,
        )

    def run(self, max_games: int | None = None, forever: bool = True) -> int:
        played = 0
        store = CompetitionStore(self.config.results_db)
        try:
            game_runner = GameRunner(store, self.config)
            openings = OpeningBook(self.config.openings_file)
            while forever or max_games is None or played < max_games:
                engines = discover_engines(self.config.generations_root)
                for engine in engines:
                    store.upsert_engine(engine)

                pairing = self._next_pairing(store, engines)
                if pairing is None:
                    if not forever:
                        break
                    time.sleep(self.config.poll_seconds)
                    continue

                white, black = pairing
                game_index = store.game_count()
                time_control = self.config.time_controls[game_index % len(self.config.time_controls)]
                opening, skip_reason = self._choose_opening(store, openings, white, black)
                game_runner.play(white, black, time_control, opening, skip_reason)
                played += 1
                if max_games is not None and played >= max_games:
                    break
            return played
        finally:
            store.close()

    @staticmethod
    def _next_pairing(store: CompetitionStore, engines):
        if len(engines) < 2:
            return None
        counts = store.pair_counts_by_name()
        engine_counts = store.engine_game_counts_by_name()
        max_engine_games = max(engine_counts.get(engine.name, 0) for engine in engines)
        catch_up_floor = max(0, max_engine_games - CATCH_UP_GAME_MARGIN)
        deficits = {engine.name: max(0, catch_up_floor - engine_counts.get(engine.name, 0)) for engine in engines}

        catch_up_engines = [engine for engine in engines if deficits[engine.name] > 0]
        if catch_up_engines:
            focal = _choose_catch_up_engine(catch_up_engines, deficits, engine_counts)
            opponents = [engine for engine in engines if engine.name != focal.name]
            pairs = [(focal, opponent) for opponent in opponents] + [(opponent, focal) for opponent in opponents]
            random.shuffle(pairs)
            pairs.sort(
                key=lambda pair: (
                    _unordered_pair_count(counts, pair[0].name, pair[1].name),
                    counts.get((pair[0].name, pair[1].name), 0),
                    engine_counts.get(pair[0].name if pair[1].name == focal.name else pair[1].name, 0),
                )
            )
            return pairs[0]

        pairs = list(permutations(sorted(engines, key=lambda engine: engine.engine_id), 2))
        random.shuffle(pairs)
        pairs.sort(
            key=lambda pair: (
                _unordered_pair_count(counts, pair[0].name, pair[1].name),
                counts.get((pair[0].name, pair[1].name), 0),
                max(engine_counts.get(pair[0].name, 0), engine_counts.get(pair[1].name, 0)),
            )
        )
        return pairs[0]

    def _choose_opening(self, store: CompetitionStore, openings: OpeningBook, white, black):
        if not openings.openings:
            return None, ""
        white_ok, white_reason = self._opening_capability(store, white)
        black_ok, black_reason = self._opening_capability(store, black)
        if white_ok and black_ok:
            return openings.choose(), ""
        reasons = []
        if not white_ok:
            reasons.append(f"{white.name}: {white_reason}")
        if not black_ok:
            reasons.append(f"{black.name}: {black_reason}")
        return None, "; ".join(reasons)

    def _opening_capability(self, store: CompetitionStore, engine):
        cached = store.get_opening_capability(engine.engine_id)
        if cached is not None:
            return cached
        supports, reason = probe_opening_support(engine, self.config.handshake_timeout_seconds)
        store.set_opening_capability(engine.engine_id, supports, reason)
        return supports, reason


def _choose_catch_up_engine(engines, deficits: dict[str, int], engine_counts: dict[str, int]):
    max_deficit = max(deficits[engine.name] for engine in engines)
    candidates = [engine for engine in engines if deficits[engine.name] == max_deficit]
    min_games = min(engine_counts.get(engine.name, 0) for engine in candidates)
    candidates = [engine for engine in candidates if engine_counts.get(engine.name, 0) == min_games]
    return random.choice(candidates)


def _unordered_pair_count(counts: dict[tuple[str, str], int], first: str, second: str) -> int:
    return counts.get((first, second), 0) + counts.get((second, first), 0)
