import {
  BadgeAlert,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Crown,
  Filter,
  Gauge,
  Pause,
  Play,
  RotateCcw,
  Search,
  ShieldCheck,
  Swords,
  Trophy,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Chess } from "chess.js";

type Engine = {
  engine_id: string;
  name: string;
  provider_model: string;
  run_id: string;
  compile_ok: boolean | null;
};

type Standing = {
  engine_id: string;
  name: string;
  provider_model: string;
  games: number;
  wins: number;
  losses: number;
  draws: number;
  score: number;
};

type MoveRecord = {
  ply: number;
  engine_id: string;
  move_uci: string;
  fen_before: string;
  fen_after: string;
  elapsed_ms: number | null;
  clock_ms: number | null;
};

type GameError = {
  engine_id: string | null;
  message: string;
  created_at: string;
};

type TimeControl = {
  movetime_ms: number;
  init_ms: number | null;
  increment_ms: number;
  move_overhead_ms: number;
} | null;

type Game = {
  game_id: string;
  white_engine_id: string;
  black_engine_id: string;
  white_name: string;
  black_name: string;
  scheduled_at: string;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  result: string | null;
  reason: string | null;
  pgn: string | null;
  time_control: TimeControl;
  opening_moves: string | null;
  opening_fen: string | null;
  opening_source: string | null;
  opening_skip_reason: string | null;
  white_clock_ms: number | null;
  black_clock_ms: number | null;
  moves: MoveRecord[];
  errors: GameError[];
};

type CompetitionData = {
  exported_at: string;
  summary: {
    engines: number;
    games: number;
    moves: number;
    finished: number;
    failed: number;
  };
  engines: Engine[];
  standings: Standing[];
  games: Game[];
};

type ReplayMove = MoveRecord & {
  san: string;
  side: "white" | "black";
  locked: boolean;
};

type Replay = {
  initialFen: string;
  positions: string[];
  moves: ReplayMove[];
  openingPlyCount: number;
};

type MovePair = {
  moveNumber: number;
  white?: ReplayMove;
  black?: ReplayMove;
};

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const PIECES: Record<string, string> = {
  wp: "/assets/wp.png",
  wn: "/assets/wn.png",
  wb: "/assets/wb.png",
  wr: "/assets/wr.png",
  wq: "/assets/wq.png",
  wk: "/assets/wk.png",
  bp: "/assets/bp.png",
  bn: "/assets/bn.png",
  bb: "/assets/bb.png",
  br: "/assets/br.png",
  bq: "/assets/bq.png",
  bk: "/assets/bk.png",
};

const FALLBACK_PIECES: Record<string, string> = {
  wp: "♙",
  wn: "♘",
  wb: "♗",
  wr: "♖",
  wq: "♕",
  wk: "♔",
  bp: "♟",
  bn: "♞",
  bb: "♝",
  br: "♜",
  bq: "♛",
  bk: "♚",
};

function App() {
  const [data, setData] = useState<CompetitionData | null>(null);
  const [loadError, setLoadError] = useState<string>("");
  const [query, setQuery] = useState("");
  const [resultFilter, setResultFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [engineFilter, setEngineFilter] = useState("all");
  const [selectedGameId, setSelectedGameId] = useState<string>("");
  const [plyIndex, setPlyIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    fetch("/data/competition.json")
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Data export not found (${response.status})`);
        }
        return response.json() as Promise<CompetitionData>;
      })
      .then((payload) => {
        setData(payload);
        setSelectedGameId(payload.games[0]?.game_id ?? "");
      })
      .catch((error: Error) => setLoadError(error.message));
  }, []);

  const enginesById = useMemo(() => {
    const map = new Map<string, Engine>();
    data?.engines.forEach((engine) => map.set(engine.engine_id, engine));
    return map;
  }, [data]);

  const filteredGames = useMemo(() => {
    if (!data) return [];
    const text = query.trim().toLowerCase();
    return data.games.filter((game) => {
      const matchesText =
        !text ||
        game.white_name.toLowerCase().includes(text) ||
        game.black_name.toLowerCase().includes(text) ||
        game.reason?.toLowerCase().includes(text) ||
        game.opening_moves?.toLowerCase().includes(text) ||
        game.game_id.toLowerCase().includes(text);
      const matchesResult = resultFilter === "all" || (game.result ?? "*") === resultFilter;
      const matchesStatus = statusFilter === "all" || game.status === statusFilter;
      const matchesEngine =
        engineFilter === "all" || game.white_engine_id === engineFilter || game.black_engine_id === engineFilter;
      return matchesText && matchesResult && matchesStatus && matchesEngine;
    });
  }, [data, engineFilter, query, resultFilter, statusFilter]);

  useEffect(() => {
    if (filteredGames.length === 0) {
      setSelectedGameId("");
      return;
    }
    if (!filteredGames.some((game) => game.game_id === selectedGameId)) {
      setSelectedGameId(filteredGames[0].game_id);
      setPlyIndex(0);
      setPlaying(false);
    }
  }, [filteredGames, selectedGameId]);

  const selectedGame = useMemo(
    () => filteredGames.find((game) => game.game_id === selectedGameId) ?? filteredGames[0],
    [filteredGames, selectedGameId],
  );

  const replay = useMemo(() => (selectedGame ? buildReplay(selectedGame) : null), [selectedGame]);
  const activeFen = replay?.positions[Math.min(plyIndex, replay.positions.length - 1)] ?? START_FEN;
  const activeMove = replay?.moves[Math.max(0, plyIndex - 1)] ?? null;

  const selectGame = useCallback((gameId: string) => {
    setSelectedGameId(gameId);
    setPlyIndex(0);
    setPlaying(false);
  }, []);

  useEffect(() => {
    setPlyIndex(0);
    setPlaying(false);
  }, [selectedGame?.game_id]);

  useEffect(() => {
    if (!playing || !replay) return;
    if (plyIndex >= replay.positions.length - 1) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => setPlyIndex((value) => value + 1), 650);
    return () => window.clearTimeout(timer);
  }, [playing, plyIndex, replay]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!replay) return;
      if (event.key === "ArrowLeft") {
        setPlyIndex((value) => Math.max(0, value - 1));
      }
      if (event.key === "ArrowRight") {
        setPlyIndex((value) => Math.min(replay.positions.length - 1, value + 1));
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [replay]);

  if (loadError) {
    return (
      <main className="empty-state">
        <BadgeAlert size={40} />
        <h1>Competition export missing</h1>
        <p>Run `npm run export:data` from `web-chess-gui`, then start the dev server again.</p>
        <code>{loadError}</code>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="loading-shell">
        <div className="board-skeleton" />
        <p>Loading arena...</p>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">LLM Chess Engines</p>
          <h1>Round Robin Arena</h1>
        </div>
        <div className="summary-strip">
          <Stat icon={<Swords />} label="Games" value={data.summary.games.toLocaleString()} />
          <Stat icon={<Gauge />} label="Moves" value={data.summary.moves.toLocaleString()} />
          <Stat icon={<Trophy />} label="Engines" value={data.summary.engines.toLocaleString()} />
        </div>
      </header>

      <section className="arena-grid">
        <aside className="left-rail panel">
          <div className="section-heading">
            <Crown size={18} />
            <h2>Standings</h2>
          </div>
          <Standings standings={data.standings} selectedEngine={engineFilter} onSelectEngine={setEngineFilter} />
          <div className="section-heading compact">
            <Filter size={18} />
            <h2>Games</h2>
          </div>
          <div className="filters">
            <label className="search-box">
              <Search size={16} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search games" />
            </label>
            <select value={engineFilter} onChange={(event) => setEngineFilter(event.target.value)}>
              <option value="all">All engines</option>
              {data.engines.map((engine) => (
                <option key={engine.engine_id} value={engine.engine_id}>
                  {engine.name}
                </option>
              ))}
            </select>
            <div className="filter-row">
              <select value={resultFilter} onChange={(event) => setResultFilter(event.target.value)}>
                <option value="all">All results</option>
                <option value="1-0">1-0</option>
                <option value="0-1">0-1</option>
                <option value="1/2-1/2">Draw</option>
                <option value="*">*</option>
              </select>
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="all">All statuses</option>
                <option value="finished">Finished</option>
                <option value="failed">Failed</option>
                <option value="running">Running</option>
                <option value="scheduled">Scheduled</option>
              </select>
            </div>
          </div>
          <div className="game-list">
            {filteredGames.map((game) => (
              <button
                className={`game-card ${game.game_id === selectedGame?.game_id ? "active" : ""}`}
                key={game.game_id}
                onClick={() => selectGame(game.game_id)}
              >
                <span className={`game-card-result ${resultClass(game.result)}`}>{displayResult(game.result)}</span>
                <span className="game-card-players">
                  <strong>{shortName(game.white_name)}</strong>
                  <em>vs</em>
                  <strong>{shortName(game.black_name)}</strong>
                </span>
                <small>
                  <span>{game.status}</span>
                  <span>{game.reason ?? "ongoing"}</span>
                </small>
              </button>
            ))}
          </div>
        </aside>

        <section className="board-stage">
          {selectedGame && replay ? (
            <>
              <GameHeader game={selectedGame} enginesById={enginesById} />
              <ChessBoard fen={activeFen} flipped={flipped} lastMove={activeMove?.move_uci ?? ""} />
              <div className="transport panel">
                <button title="First move" onClick={() => setPlyIndex(0)}>
                  <ChevronsLeft />
                </button>
                <button title="Previous move" onClick={() => setPlyIndex((value) => Math.max(0, value - 1))}>
                  <ChevronLeft />
                </button>
                <button className="play-button" title={playing ? "Pause" : "Play"} onClick={() => setPlaying(!playing)}>
                  {playing ? <Pause /> : <Play />}
                </button>
                <button
                  title="Next move"
                  onClick={() => setPlyIndex((value) => Math.min(replay.positions.length - 1, value + 1))}
                >
                  <ChevronRight />
                </button>
                <button title="Last move" onClick={() => setPlyIndex(replay.positions.length - 1)}>
                  <ChevronsRight />
                </button>
                <button title="Flip board" onClick={() => setFlipped((value) => !value)}>
                  <RotateCcw />
                </button>
                <div className="progress-wrap">
                  <input
                    type="range"
                    min={0}
                    max={Math.max(0, replay.positions.length - 1)}
                    value={plyIndex}
                    onChange={(event) => setPlyIndex(Number(event.target.value))}
                  />
                  <span>
                    {plyIndex}/{Math.max(0, replay.positions.length - 1)}
                  </span>
                </div>
              </div>
            </>
          ) : (
            <div className="empty-board panel">No games match the current filters.</div>
          )}
        </section>

        <aside className="right-rail panel">
          {selectedGame && replay && (
            <>
              <div className="section-heading">
                <Gauge size={18} />
                <h2>Game Detail</h2>
              </div>
              <dl className="detail-grid">
                <div>
                  <dt>Result</dt>
                  <dd>{selectedGame.result ?? "*"}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{selectedGame.status}</dd>
                </div>
                <div>
                  <dt>Time</dt>
                  <dd>{timeControlLabel(selectedGame.time_control)}</dd>
                </div>
                <div>
                  <dt>Termination</dt>
                  <dd>{selectedGame.reason ?? "ongoing"}</dd>
                </div>
              </dl>
              <div className="opening-box">
                <span>Opening</span>
                <p>
                  {replay.openingPlyCount > 0
                    ? `${replay.openingPlyCount} locked book plies`
                    : selectedGame.opening_skip_reason || "Start position"}
                </p>
              </div>
              {selectedGame.errors.length > 0 && (
                <div className="error-box">
                  <BadgeAlert size={16} />
                  <span>{selectedGame.errors[0].message}</span>
                </div>
              )}
              <div className="move-table">
                {pairMoves(replay.moves).map((pair) => (
                  <div className="move-row" key={pair.moveNumber}>
                    <span className="move-number">{pair.moveNumber}</span>
                    <MoveButton move={pair.white} replay={replay} plyIndex={plyIndex} onSelect={setPlyIndex} />
                    <MoveButton move={pair.black} replay={replay} plyIndex={plyIndex} onSelect={setPlyIndex} />
                  </div>
                ))}
              </div>
            </>
          )}
        </aside>
      </section>
    </main>
  );
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="stat">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
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
  if (!move) return <span className="move-placeholder" />;
  const index = replay.moves.indexOf(move) + 1;
  return (
    <button className={`${plyIndex === index ? "current" : ""} ${move.locked ? "locked" : ""}`} onClick={() => onSelect(index)}>
      {move.san}
      <small>{move.locked ? <ShieldCheck size={12} /> : `${move.elapsed_ms ?? 0}ms`}</small>
    </button>
  );
}

function Standings({
  standings,
  selectedEngine,
  onSelectEngine,
}: {
  standings: Standing[];
  selectedEngine: string;
  onSelectEngine: (engineId: string) => void;
}) {
  return (
    <div className="standings">
      {standings.map((standing, index) => (
        <button
          className={`standing-row ${selectedEngine === standing.engine_id ? "active" : ""}`}
          key={standing.engine_id}
          onClick={() => onSelectEngine(selectedEngine === standing.engine_id ? "all" : standing.engine_id)}
        >
          <span className="rank">{index + 1}</span>
          <span className="standing-name">{shortName(standing.name)}</span>
          <strong>{standing.score}</strong>
          <small>
            {standing.wins}-{standing.losses}-{standing.draws}
          </small>
        </button>
      ))}
    </div>
  );
}

function GameHeader({ game, enginesById }: { game: Game; enginesById: Map<string, Engine> }) {
  const white = enginesById.get(game.white_engine_id);
  const black = enginesById.get(game.black_engine_id);
  return (
    <div className="game-header panel">
      <PlayerBadge color="white" name={game.white_name} compileOk={white?.compile_ok} />
      <div className="score-pill">
        <span>{game.result ?? "*"}</span>
        <small>{formatDate(game.finished_at ?? game.started_at ?? game.scheduled_at)}</small>
      </div>
      <PlayerBadge color="black" name={game.black_name} compileOk={black?.compile_ok} />
    </div>
  );
}

function PlayerBadge({ color, name, compileOk }: { color: "white" | "black"; name: string; compileOk?: boolean | null }) {
  return (
    <div className={`player-badge ${color}`}>
      <span className="piece-dot">{color === "white" ? "♔" : "♚"}</span>
      <div>
        <strong>{shortName(name)}</strong>
        <small>{compileOk === false ? "compile issue" : "compiled"}</small>
      </div>
    </div>
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
    <div className="board-frame">
      <div className="chess-board">
        {ranks.map((rank) =>
          files.map((file) => {
            const square = `${file}${rank}`;
            const piece = board[8 - rank][file.charCodeAt(0) - 97];
            const isLight = (files.indexOf(file) + ranks.indexOf(rank)) % 2 === 0;
            return (
              <div className={`square ${isLight ? "light" : "dark"} ${lastSquares.includes(square) ? "last" : ""}`} key={square}>
                <span className="coord rank-label">{file === files[0] ? rank : ""}</span>
                {piece && <Piece pieceKey={`${piece.color}${piece.type}`} color={piece.color} />}
                <span className="coord file-label">{rank === ranks[ranks.length - 1] ? file : ""}</span>
              </div>
            );
          }),
        )}
      </div>
    </div>
  );
}

function Piece({ pieceKey, color }: { pieceKey: string; color: "w" | "b" }) {
  const [errored, setErrored] = useState(false);
  if (errored) {
    return <span className={`piece fallback-piece ${color}`}>{FALLBACK_PIECES[pieceKey]}</span>;
  }
  return (
    <img
      className={`piece ${color}`}
      src={PIECES[pieceKey]}
      alt={pieceKey}
      draggable={false}
      onError={() => setErrored(true)}
    />
  );
}

function buildReplay(game: Game): Replay {
  const chess = new Chess(START_FEN);
  const positions = [START_FEN];
  const replayMoves: ReplayMove[] = [];
  const openingMoves = (game.opening_moves ?? "").split(/\s+/).filter(Boolean);
  let lockedOpeningPlies = 0;

  for (const [index, moveText] of openingMoves.entries()) {
    const fenBefore = chess.fen();
    const side: "white" | "black" = chess.turn() === "w" ? "white" : "black";
    const parsed = uciToMove(moveText);
    let san = moveText;
    try {
      san = chess.move(parsed).san;
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
    lockedOpeningPlies += 1;
    positions.push(chess.fen());
  }

  for (const move of [...game.moves].sort((a, b) => a.ply - b.ply)) {
    const parsed = uciToMove(move.move_uci);
    let san = move.move_uci;
    try {
      if (chess.fen() !== move.fen_before) {
        chess.load(move.fen_before);
      }
      san = chess.move(parsed).san;
    } catch {
      try {
        chess.load(move.fen_after);
      } catch {
        // Keep the replay usable even when a failed game has a partial trail.
      }
    }
    positions.push(move.fen_after);
    const [, turn] = move.fen_before.split(" ");
    const side: "white" | "black" = turn === "b" ? "black" : "white";
    replayMoves.push({ ...move, san, side, locked: false });
  }

  return { initialFen: START_FEN, positions, moves: replayMoves, openingPlyCount: lockedOpeningPlies };
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

function shortName(name: string) {
  return name.replace(/^anthropic-/, "").replace(/^openai-/, "").replace(/^gemini-/, "").replace(/^deepseek-/, "");
}

function displayResult(result: string | null) {
  if (result === "1/2-1/2") return "Draw";
  return result ?? "*";
}

function resultClass(result: string | null) {
  if (result === "1/2-1/2") return "draw";
  if (result === "1-0" || result === "0-1") return "decisive";
  return "pending";
}

function timeControlLabel(timeControl: TimeControl) {
  if (!timeControl) return "unknown";
  if (timeControl.init_ms === null) return `${timeControl.movetime_ms}ms/move`;
  return `${Math.round(timeControl.init_ms / 1000)}s + ${timeControl.increment_ms}ms`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export { App };
