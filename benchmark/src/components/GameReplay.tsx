"use client";

import { useEffect, useMemo, useState } from "react";
import { Chess, type Color, type PieceSymbol } from "chess.js";
import {
  BookOpen,
  ChevronsLeft,
  ChevronsRight,
  Clock3,
  FlipHorizontal2,
  Gauge,
  Pause,
  Play,
  RotateCcw,
  SkipBack,
  SkipForward,
  ShieldAlert,
  TimerReset,
} from "lucide-react";

import { durationLabel, formatInteger, formatShortDate, modelLabel, providerLabel, resultLabel, timeControlLabel } from "@/core/format";
import type { GameDetail, LeaderboardRow, MoveRecord } from "@/core/types";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const PIECES: Record<string, string> = {
  wp: "/assets/chess/wp.png",
  wn: "/assets/chess/wn.png",
  wb: "/assets/chess/wb.png",
  wr: "/assets/chess/wr.png",
  wq: "/assets/chess/wq.png",
  wk: "/assets/chess/wk.png",
  bp: "/assets/chess/bp.png",
  bn: "/assets/chess/bn.png",
  bb: "/assets/chess/bb.png",
  br: "/assets/chess/br.png",
  bq: "/assets/chess/bq.png",
  bk: "/assets/chess/bk.png",
};

type ReplayMove = MoveRecord & {
  san: string;
  side: "white" | "black";
  locked: boolean;
};

type Replay = {
  positions: string[];
  moves: ReplayMove[];
  openingPlyCount: number;
};

type MovePair = {
  moveNumber: number;
  white?: ReplayMove;
  black?: ReplayMove;
};

export function GameReplay({ detail, models, loading = false }: { detail: GameDetail; models: LeaderboardRow[]; loading?: boolean }) {
  const [plyIndex, setPlyIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [flipped, setFlipped] = useState(false);
  const replay = useMemo(() => buildReplay(detail), [detail]);
  const activeFen = replay.positions[Math.min(plyIndex, replay.positions.length - 1)] ?? START_FEN;
  const activeMove = replay.moves[Math.max(0, plyIndex - 1)] ?? null;
  const maxPly = Math.max(0, replay.positions.length - 1);
  const white = models.find((model) => model.engine_id === detail.white_engine_id);
  const black = models.find((model) => model.engine_id === detail.black_engine_id);

  useEffect(() => {
    setPlyIndex(0);
    setPlaying(false);
  }, [detail.game_id]);

  useEffect(() => {
    if (!playing) {
      return;
    }
    if (plyIndex >= maxPly) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => setPlyIndex((value) => value + 1), 520);
    return () => window.clearTimeout(timer);
  }, [maxPly, playing, plyIndex]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "ArrowLeft") {
        setPlyIndex((value) => Math.max(0, value - 1));
      }
      if (event.key === "ArrowRight") {
        setPlyIndex((value) => Math.min(replay.positions.length - 1, value + 1));
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [replay.positions.length]);

  return (
    <div className="replay-layout">
      <div className="replay-main">
        <div className="match-card">
          <PlayerPanel
            side="white"
            label={modelLabel({ name: detail.white_name, provider_model: detail.white_provider_model })}
            elo={white?.elo}
            provider={detail.white_provider}
          />
          <div className="match-score">
            <strong>{resultLabel(detail.result)}</strong>
            <span>{formatShortDate(detail.finished_at ?? detail.started_at ?? detail.scheduled_at)}</span>
          </div>
          <PlayerPanel
            side="black"
            label={modelLabel({ name: detail.black_name, provider_model: detail.black_provider_model })}
            elo={black?.elo}
            provider={detail.black_provider}
          />
        </div>

        <div className="board-theater">
          <div className="side-controls left">
            <button title="First move" onClick={() => setPlyIndex(0)}>
              <ChevronsLeft size={19} />
            </button>
            <button title="Previous move" onClick={() => setPlyIndex((value) => Math.max(0, value - 1))}>
              <SkipBack size={19} />
            </button>
          </div>
          <ChessBoard fen={activeFen} flipped={flipped} lastMove={activeMove?.move_uci ?? ""} />
          <div className="side-controls right">
            <button title="Next move" onClick={() => setPlyIndex((value) => Math.min(maxPly, value + 1))}>
              <SkipForward size={19} />
            </button>
            <button title="Last move" onClick={() => setPlyIndex(maxPly)}>
              <ChevronsRight size={19} />
            </button>
          </div>
        </div>

        <div className="transport-bar cinematic">
          {loading && <span className="replay-loading-inline">Refreshing game data...</span>}
          <button title="Reset" onClick={() => setPlyIndex(0)}>
            <RotateCcw size={18} />
          </button>
          <button className="play-control" title={playing ? "Pause" : "Play"} onClick={() => setPlaying((value) => !value)}>
            {playing ? <Pause size={18} /> : <Play size={18} />}
          </button>
          <label className="move-slider">
            <input min={0} max={maxPly} type="range" value={plyIndex} onChange={(event) => setPlyIndex(Number(event.target.value))} />
            <span>
              Ply {plyIndex}/{maxPly}
            </span>
          </label>
          <button title="Flip board" onClick={() => setFlipped((value) => !value)}>
            <FlipHorizontal2 size={18} />
          </button>
        </div>
      </div>

      <aside className="replay-side">
        <div className="detail-stat-grid">
          <DetailStat icon={<Gauge size={17} />} label="Ply count" value={formatInteger(detail.plies)} />
          <DetailStat icon={<Clock3 size={17} />} label="Avg move" value={durationLabel(detail.avg_elapsed_ms)} />
          <DetailStat icon={<ShieldAlert size={17} />} label="Result" value={resultLabel(detail.result)} />
        </div>

        <div className="storyline-panel">
          <StoryBeat icon={<BookOpen size={17} />} label="Opening" value={replay.openingPlyCount > 0 ? `${replay.openingPlyCount} book plies` : "No book"} detail={detail.opening_skip_reason || detail.opening_source || "Moves below show where the game left preparation."} />
          <StoryBeat icon={<TimerReset size={17} />} label="Clock" value={timeControlLabel(detail.time_control)} detail={`Final clocks: W ${formatClock(detail.white_clock_ms)} / B ${formatClock(detail.black_clock_ms)}`} />
          <StoryBeat icon={<ShieldAlert size={17} />} label="Ending" value={detail.reason ?? detail.status} detail={detail.result_source?.includes("forfeit") ? "Assigned by forfeit handling." : "Resolved from completed game play."} />
        </div>

        {detail.errors.length > 0 && (
          <div className="error-panel">
            <ShieldAlert size={17} />
            <span>{detail.errors[0].message}</span>
          </div>
        )}

        <div className="move-table redesigned" aria-label="Move list">
          {pairMoves(replay.moves).map((pair) => (
            <div className="move-row" key={pair.moveNumber}>
              <span>{pair.moveNumber}</span>
              <MoveButton move={pair.white} replay={replay} plyIndex={plyIndex} onSelect={setPlyIndex} />
              <MoveButton move={pair.black} replay={replay} plyIndex={plyIndex} onSelect={setPlyIndex} />
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
}

function PlayerPanel({
  side,
  label,
  elo,
  provider,
}: {
  side: "white" | "black";
  label: string;
  elo?: number;
  provider?: string;
}) {
  return (
    <div className={`player-panel ${side}`}>
      <span className="piece-token">{side === "white" ? "W" : "B"}</span>
      <div>
        <strong>{label}</strong>
        <small>
          {providerLabel(provider)} / {elo ? `${elo} ELO` : "unrated"}
        </small>
      </div>
    </div>
  );
}

function formatClock(value: number | null | undefined): string {
  if (value === null || value === undefined) return "n/a";
  return `${(value / 1000).toFixed(1)}s`;
}

function DetailStat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="detail-stat">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StoryBeat({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string; detail: string }) {
  return (
    <div className="story-beat">
      <span className="story-icon">{icon}</span>
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </div>
  );
}

function MoveButton({
  move,
  replay,
  plyIndex,
  onSelect,
}: {
  move?: ReplayMove;
  replay: Replay;
  plyIndex: number;
  onSelect: (plyIndex: number) => void;
}) {
  if (!move) {
    return <span className="move-empty" />;
  }
  const index = replay.moves.indexOf(move) + 1;
  return (
    <button className={`${plyIndex === index ? "current" : ""} ${move.locked ? "locked" : ""}`} onClick={() => onSelect(index)}>
      <span>{move.san}</span>
      <small>{move.locked ? "book" : durationLabel(move.elapsed_ms)}</small>
    </button>
  );
}

function ChessBoard({ fen, flipped, lastMove }: { fen: string; flipped: boolean; lastMove: string }) {
  const board = useMemo(() => {
    try {
      return new Chess(fen).board();
    } catch {
      return new Chess().board();
    }
  }, [fen]);

  const files = flipped ? ["h", "g", "f", "e", "d", "c", "b", "a"] : ["a", "b", "c", "d", "e", "f", "g", "h"];
  const ranks = flipped ? [1, 2, 3, 4, 5, 6, 7, 8] : [8, 7, 6, 5, 4, 3, 2, 1];
  const lastSquares = lastMove ? [lastMove.slice(0, 2), lastMove.slice(2, 4)] : [];

  return (
    <div className="board-shell">
      <div className="board-grid">
        {ranks.map((rank) =>
          files.map((file) => {
            const piece = board[8 - rank]?.[file.charCodeAt(0) - 97] ?? null;
            const square = `${file}${rank}`;
            return (
              <div className={`board-square ${lastSquares.includes(square) ? "last" : ""}`} key={square}>
                <span className="coord rank">{file === files[0] ? rank : ""}</span>
                {piece && <Piece color={piece.color} type={piece.type} />}
                <span className="coord file">{rank === ranks[ranks.length - 1] ? file : ""}</span>
              </div>
            );
          }),
        )}
      </div>
    </div>
  );
}

function Piece({ color, type }: { color: Color; type: PieceSymbol }) {
  const key = `${color}${type}`;
  return <img className="piece-img" src={PIECES[key]} alt="" draggable={false} />;
}

function buildReplay(game: GameDetail): Replay {
  const chess = new Chess(START_FEN);
  const positions = [START_FEN];
  const replayMoves: ReplayMove[] = [];
  let openingPlyCount = 0;

  for (const [index, moveText] of game.opening_moves.entries()) {
    const fenBefore = chess.fen();
    const side: "white" | "black" = chess.turn() === "w" ? "white" : "black";
    let san = moveText;
    try {
      san = chess.move(uciToMove(moveText)).san;
    } catch {
      break;
    }
    replayMoves.push({
      ply: index + 1,
      engine_id: "",
      move_uci: moveText,
      fen_before: fenBefore,
      fen_after: chess.fen(),
      elapsed_ms: null,
      clock_ms: null,
      san,
      side,
      locked: true,
    });
    openingPlyCount += 1;
    positions.push(chess.fen());
  }

  for (const move of [...game.moves].sort((a, b) => a.ply - b.ply)) {
    let san = move.move_uci;
    try {
      if (chess.fen() !== move.fen_before) {
        chess.load(move.fen_before);
      }
      san = chess.move(uciToMove(move.move_uci)).san;
    } catch {
      try {
        chess.load(move.fen_after);
      } catch {
        // Failed games can leave partial traces; keep the replay shell usable.
      }
    }
    positions.push(move.fen_after);
    const [, turn] = move.fen_before.split(" ");
    replayMoves.push({
      ...move,
      san,
      side: turn === "b" ? "black" : "white",
      locked: false,
    });
  }

  return { positions, moves: replayMoves, openingPlyCount };
}

function uciToMove(uci: string) {
  return {
    from: uci.slice(0, 2),
    to: uci.slice(2, 4),
    promotion: uci.length > 4 ? uci.slice(4, 5) : undefined,
  };
}

function pairMoves(moves: ReplayMove[]): MovePair[] {
  const pairs = new Map<number, MovePair>();
  for (const move of moves) {
    const [, turn, , , , fullmove] = move.fen_before.split(" ");
    const moveNumber = Number(fullmove) || Math.ceil(move.ply / 2);
    const pair = pairs.get(moveNumber) ?? { moveNumber };
    if (turn === "w") {
      pair.white = move;
    } else {
      pair.black = move;
    }
    pairs.set(moveNumber, pair);
  }
  return [...pairs.values()].sort((a, b) => a.moveNumber - b.moveNumber);
}
