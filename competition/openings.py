from __future__ import annotations

import random
from pathlib import Path

import chess

from competition.models import Opening


def load_openings(path: Path | None) -> list[Opening]:
    if path is None or not path.exists():
        return []
    openings: list[Opening] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        moves = tuple(line.split())
        board = chess.Board()
        try:
            for move_text in moves:
                move = chess.Move.from_uci(move_text)
                if move not in board.legal_moves:
                    raise ValueError(f"illegal opening move {move_text}")
                board.push(move)
        except ValueError:
            continue
        openings.append(Opening(moves=moves, source=f"{path}:{line_no}"))
    return openings


class OpeningBook:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.openings = load_openings(path)
        self.random = random.SystemRandom()

    def choose(self) -> Opening | None:
        if not self.openings:
            return None
        return self.random.choice(self.openings)
