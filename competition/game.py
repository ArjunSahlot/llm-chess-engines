from __future__ import annotations

import io
import uuid

import chess
import chess.pgn

from competition.models import CompetitionConfig, Engine, Opening, TimeControl
from competition.store import CompetitionStore
from competition.uci import UciEngine


class GameRunner:
    def __init__(self, store: CompetitionStore, config: CompetitionConfig) -> None:
        self.store = store
        self.config = config

    def play(
        self,
        white: Engine,
        black: Engine,
        time_control: TimeControl,
        opening: Opening | None = None,
        opening_skip_reason: str = "",
    ) -> str:
        game_id = uuid.uuid4().hex
        board = chess.Board()
        opening_moves = list(opening.moves) if opening is not None else []
        for move_text in opening_moves:
            board.push(chess.Move.from_uci(move_text))
        self.store.create_game(game_id, white, black, self.config, time_control, opening, board.fen(), opening_skip_reason)
        self.store.start_game(game_id)

        pgn_game = chess.pgn.Game()
        pgn_game.headers["Event"] = "LLM Chess Engines Round Robin"
        pgn_game.headers["White"] = white.name
        pgn_game.headers["Black"] = black.name
        pgn_game.headers["TimeControl"] = time_control.label()
        if opening is not None:
            pgn_game.setup(board)
            pgn_game.headers["Opening"] = opening.label
            pgn_game.headers["OpeningSource"] = opening.source
        elif opening_skip_reason:
            pgn_game.headers["OpeningSkipped"] = opening_skip_reason
        node = pgn_game
        clocks = {chess.WHITE: time_control.init_ms, chess.BLACK: time_control.init_ms}

        engines = {
            chess.WHITE: UciEngine(white.command, white.root, lambda direction, line: self.store.record_uci(game_id, white.engine_id, direction, line)),
            chess.BLACK: UciEngine(black.command, black.root, lambda direction, line: self.store.record_uci(game_id, black.engine_id, direction, line)),
        }

        try:
            for side, engine in engines.items():
                current_engine = white if side == chess.WHITE else black
                try:
                    engine.start()
                    engine.initialize(self.config.handshake_timeout_seconds)
                    engine.send("ucinewgame")
                    engine.send("isready")
                    engine.wait_for("readyok", self.config.handshake_timeout_seconds)
                except Exception as exc:
                    self.store.record_error(game_id, current_engine.engine_id, str(exc))
                    result, reason = self._forfeit(side, f"engine error: {exc}")
                    pgn_game.headers["Result"] = result
                    pgn_game.headers["Termination"] = reason
                    self.store.finish_game(
                        game_id,
                        result,
                        reason,
                        _pgn_string(pgn_game),
                        clocks[chess.WHITE],
                        clocks[chess.BLACK],
                        result_source="forfeit",
                        forfeiting_engine_id=current_engine.engine_id,
                    )
                    return game_id

            result = "*"
            reason = "max plies"
            forfeiting_engine_id: str | None = None
            while not board.is_game_over(claim_draw=True) and board.ply() < self.config.max_plies:
                side = board.turn
                current = engines[side]
                current_engine = white if side == chess.WHITE else black
                fen_before = board.fen()
                try:
                    current.send(f"position fen {fen_before}")
                    current.send(time_control.go_command(clocks[chess.WHITE], clocks[chess.BLACK]))
                    bestmove, elapsed_ms = current.wait_bestmove(self.config.move_timeout_seconds)
                except Exception as exc:
                    self.store.record_error(game_id, current_engine.engine_id, str(exc))
                    result, reason = self._forfeit(side, f"engine error: {exc}")
                    forfeiting_engine_id = current_engine.engine_id
                    break

                if bestmove == "0000":
                    result, reason = self._forfeit(side, "null bestmove")
                    forfeiting_engine_id = current_engine.engine_id
                    break

                try:
                    move = chess.Move.from_uci(bestmove)
                except ValueError:
                    result, reason = self._forfeit(side, f"invalid move syntax {bestmove!r}")
                    forfeiting_engine_id = current_engine.engine_id
                    break
                if move not in board.legal_moves:
                    result, reason = self._forfeit(side, f"illegal move {bestmove}")
                    forfeiting_engine_id = current_engine.engine_id
                    break

                if clocks[side] is not None:
                    clocks[side] = max(0, clocks[side] - elapsed_ms - time_control.move_overhead_ms)
                    clocks[side] += time_control.increment_ms
                    if clocks[side] <= 0:
                        result, reason = self._forfeit(side, "flagged")
                        forfeiting_engine_id = current_engine.engine_id
                        break

                board.push(move)
                node = node.add_variation(move)
                self.store.record_move(
                    game_id,
                    board.ply(),
                    current_engine.engine_id,
                    bestmove,
                    fen_before,
                    board.fen(),
                    elapsed_ms,
                    clocks[side],
                )

            if board.is_game_over(claim_draw=True):
                result = board.result(claim_draw=True)
                reason = board.outcome(claim_draw=True).termination.name.lower()
            elif result == "*":
                result = "1/2-1/2"

            pgn_game.headers["Result"] = result
            pgn_game.headers["Termination"] = reason
            pgn = _pgn_string(pgn_game)
            self.store.finish_game(
                game_id,
                result,
                reason,
                pgn,
                clocks[chess.WHITE],
                clocks[chess.BLACK],
                result_source="forfeit" if forfeiting_engine_id is not None else "game",
                forfeiting_engine_id=forfeiting_engine_id,
            )
            return game_id
        except Exception as exc:
            self.store.record_error(game_id, None, str(exc))
            pgn_game.headers["Result"] = "*"
            pgn_game.headers["Termination"] = f"error: {exc}"
            self.store.fail_game(game_id, str(exc), _pgn_string(pgn_game))
            return game_id
        finally:
            for engine in engines.values():
                engine.stop()

    @staticmethod
    def _forfeit(side: chess.Color, reason: str) -> tuple[str, str]:
        return ("0-1" if side == chess.WHITE else "1-0", reason)


def _pgn_string(game: chess.pgn.Game) -> str:
    output = io.StringIO()
    print(game, file=output, end="\n")
    return output.getvalue()
