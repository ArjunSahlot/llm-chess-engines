"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  BadgeAlert,
  Clock3,
  Crown,
  Filter,
  Flag,
  Gauge,
  ListFilter,
  Search,
  Shield,
  Swords,
  Trophy,
  X,
} from "lucide-react";

import { ModelMark } from "@/components/ModelMark";
import { fetchGames, fetchLeaderboard } from "@/core/benchmark-api";
import { durationLabel, formatInteger, gameHeadline, modelLabel, providerLabel, resultLabel, timeControlLabel } from "@/core/format";
import { hasSupabaseConfig } from "@/core/supabase";
import type { GameSummary, LeaderboardRow } from "@/core/types";

const PAGE_SIZE = 60;
const ALL = "all";

type MenuModel = LeaderboardRow & { label: string };

export function GamesExplorer() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const configured = hasSupabaseConfig();
  const [models, setModels] = useState<LeaderboardRow[]>([]);
  const [games, setGames] = useState<GameSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [modelFilter, setModelFilter] = useState(searchParams.get("model") ?? ALL);
  const [opponentFilter, setOpponentFilter] = useState(searchParams.get("opponent") ?? ALL);
  const [resultFilter, setResultFilter] = useState(searchParams.get("result") ?? ALL);
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const filters = useMemo(
    () => ({
      search: query,
      model: modelFilter,
      opponent: modelFilter === ALL ? ALL : opponentFilter,
      result: resultFilter,
      limit: PAGE_SIZE,
    }),
    [modelFilter, opponentFilter, query, resultFilter],
  );

  const menuModels = useMemo(() => {
    return models
      .map((model) => ({ ...model, label: model.label || modelLabel(model) }))
      .sort((a, b) => providerLabel(a.provider).localeCompare(providerLabel(b.provider)) || a.label.localeCompare(b.label));
  }, [models]);

  const selectedModel = menuModels.find((model) => model.engine_id === modelFilter);
  const selectedOpponent = menuModels.find((model) => model.engine_id === opponentFilter);
  const opponentModels = useMemo(() => menuModels.filter((model) => model.engine_id !== modelFilter), [menuModels, modelFilter]);

  const loadFirstPage = useCallback(() => {
    if (!configured) return;
    setLoading(true);
    setError("");
    Promise.all([fetchLeaderboard(), fetchGames({ ...filters, offset: 0 })])
      .then(([rows, payload]) => {
        setModels(rows);
        setGames(payload.games);
        setTotal(payload.count);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [configured, filters]);

  useEffect(() => {
    loadFirstPage();
  }, [loadFirstPage]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !configured) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting) || loading || games.length >= total) return;
        setLoading(true);
        fetchGames({ ...filters, offset: games.length })
          .then((payload) => {
            setGames((current) => [...current, ...payload.games]);
            setTotal(payload.count);
          })
          .catch((err: Error) => setError(err.message))
          .finally(() => setLoading(false));
      },
      { rootMargin: "900px 0px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [configured, filters, games.length, loading, total]);

  const updateUrl = useCallback(
    (next: { model?: string; opponent?: string; result?: string; q?: string }) => {
      const params = new URLSearchParams();
      const nextModel = next.model ?? modelFilter;
      const nextOpponent = next.opponent ?? opponentFilter;
      const nextResult = next.result ?? resultFilter;
      const text = next.q ?? query;
      if (nextModel !== ALL) params.set("model", nextModel);
      if (nextModel !== ALL && nextOpponent !== ALL) params.set("opponent", nextOpponent);
      if (nextResult !== ALL) params.set("result", nextResult);
      if (text.trim()) params.set("q", text.trim());
      router.replace(`/games/${params.toString() ? `?${params.toString()}` : ""}`, { scroll: false });
    },
    [modelFilter, opponentFilter, query, resultFilter, router],
  );

  const setModel = (value: string) => {
    setModelFilter(value);
    if (value === ALL || value === opponentFilter) {
      setOpponentFilter(ALL);
      startTransition(() => updateUrl({ model: value, opponent: ALL }));
    } else {
      startTransition(() => updateUrl({ model: value }));
    }
  };

  const clearFilters = () => {
    setQuery("");
    setModelFilter(ALL);
    setOpponentFilter(ALL);
    setResultFilter(ALL);
    setOpenMenu(null);
    router.replace("/games/", { scroll: false });
  };

  if (!configured) {
    return (
      <section className="games-shell">
        <div className="games-toolbar">
          <div>
            <p className="eyebrow">Game archive</p>
            <h1>Archive unavailable</h1>
          </div>
        </div>
        <div className="setup-notice large">
          <Shield size={24} style={{ marginBottom: "1rem", color: "var(--brand)" }} />
          <p>The detailed game archive requires a database connection, which is not currently configured for this deployment.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="games-shell archive-only">
      <div className="games-toolbar archive-hero">
        <div>
          <p className="eyebrow">Game finder</p>
          <h1>{formatInteger(total)} games, sorted by plies</h1>
          <p className="games-intro">Find long, high-signal games first, then open one into the focused replay room.</p>
        </div>
        <button className="icon-text-button" onClick={clearFilters}>
          <X size={16} /> Clear filters
        </button>
      </div>

      {error && <div className="setup-notice error">{error}</div>}

      <div className="archive-filter-panel">
        <label className="field-shell search-field archive-search">
          <Search size={17} />
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              startTransition(() => updateUrl({ q: event.target.value }));
            }}
            placeholder="Search games, models, endings"
          />
        </label>
        <ModelMenu
          id="model"
          icon={<Filter size={17} />}
          label="Model"
          value={modelFilter}
          selected={selectedModel}
          models={menuModels}
          openMenu={openMenu}
          setOpenMenu={setOpenMenu}
          onSelect={setModel}
        />
        {modelFilter !== ALL && (
          <ModelMenu
            id="opponent"
            icon={<Swords size={17} />}
            label="Opponent"
            value={opponentFilter}
            selected={selectedOpponent}
            models={opponentModels}
            openMenu={openMenu}
            setOpenMenu={setOpenMenu}
            onSelect={(value) => {
              setOpponentFilter(value);
              startTransition(() => updateUrl({ opponent: value }));
            }}
          />
        )}
        <ResultMenu
          value={resultFilter}
          openMenu={openMenu}
          setOpenMenu={setOpenMenu}
          onSelect={(value) => {
            setResultFilter(value);
            startTransition(() => updateUrl({ result: value }));
          }}
        />
      </div>

      <div className="archive-status">
        <span>
          <ListFilter size={15} /> {loading || isPending ? "Loading games" : `Showing ${formatInteger(games.length)} of ${formatInteger(total)}`}
        </span>
        <span>
          <Gauge size={15} /> Longest games first
        </span>
      </div>

      <div className="archive-game-list">
        {games.map((game) => (
          <GameListItem game={game} key={game.game_id} filteredModel={modelFilter !== ALL ? modelFilter : null} />
        ))}
        {!loading && games.length === 0 && (
          <div className="empty-list archive-empty">
            <BadgeAlert size={26} />
            <span>No games match those filters.</span>
          </div>
        )}
        <div ref={sentinelRef} className="scroll-sentinel" />
      </div>
    </section>
  );
}

function GameListItem({ game, filteredModel }: { game: GameSummary; filteredModel: string | null }) {
  const resultClass = filteredModel ? resultClassForModel(game, filteredModel) : game.result === "1/2-1/2" ? "draw" : game.result_source?.includes("forfeit") ? "forfeit" : "decisive";
  const white = { name: game.white_name, provider_model: game.white_provider_model, provider: game.white_provider };
  const black = { name: game.black_name, provider_model: game.black_provider_model, provider: game.black_provider };

  return (
    <Link className="archive-game-row" href={`/games/view/?game=${encodeURIComponent(game.game_id)}`}>
      <span className={`result-pill ${resultClass}`}>{filteredModel ? perspectiveResultLabel(game, filteredModel) : resultLabel(game.result)}</span>
      <span className="archive-game-match">
        <strong>
          {modelLabel(white)} <em>vs</em> {modelLabel(black)}
        </strong>
        <small>{gameHeadline(game)}</small>
      </span>
      <span className="archive-game-facts">
        <Fact icon={<Gauge size={15} />} label="Plies" value={formatInteger(game.plies)} />
        <Fact icon={<Flag size={15} />} label="Ending" value={game.reason ?? game.status} />
        <Fact icon={<Clock3 size={15} />} label="Time" value={timeControlLabel(game.time_control)} />
        <Fact icon={<Trophy size={15} />} label="Avg move" value={durationLabel(game.avg_elapsed_ms)} />
      </span>
    </Link>
  );
}

function Fact({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <span>
      {icon}
      <small>{label}</small>
      <strong>{value}</strong>
    </span>
  );
}

function ModelMenu({
  id,
  icon,
  label,
  value,
  selected,
  models,
  openMenu,
  setOpenMenu,
  onSelect,
}: {
  id: string;
  icon: React.ReactNode;
  label: string;
  value: string;
  selected?: MenuModel;
  models: MenuModel[];
  openMenu: string | null;
  setOpenMenu: (value: string | null) => void;
  onSelect: (value: string) => void;
}) {
  const groups = groupModels(models);
  const open = openMenu === id;
  return (
    <div className="custom-menu">
      <button className={`menu-trigger ${open ? "open" : ""}`} onClick={() => setOpenMenu(open ? null : id)}>
        {icon}
        <span>
          <small>{label}</small>
          <strong>{selected ? selected.label : "All models"}</strong>
        </span>
      </button>
      {open && (
        <div className="menu-popover model-menu-popover">
          <button className={value === ALL ? "selected" : ""} onClick={() => { onSelect(ALL); setOpenMenu(null); }}>
            <Crown size={16} />
            <span>All models</span>
          </button>
          {groups.map((group) => (
            <div className="menu-group" key={group.provider}>
              <p>{group.provider}</p>
              {group.models.map((model) => (
                <button
                  className={value === model.engine_id ? "selected" : ""}
                  key={model.engine_id}
                  onClick={() => {
                    onSelect(model.engine_id);
                    setOpenMenu(null);
                  }}
                >
                  <ModelMark model={model} compact />
                  <span className="menu-record">{formatInteger(model.games)} games</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ResultMenu({
  value,
  openMenu,
  setOpenMenu,
  onSelect,
}: {
  value: string;
  openMenu: string | null;
  setOpenMenu: (value: string | null) => void;
  onSelect: (value: string) => void;
}) {
  const open = openMenu === "result";
  const options = [
    { value: ALL, label: "All results", icon: <Trophy size={16} /> },
    { value: "decisive", label: "Decisive", icon: <Crown size={16} /> },
    { value: "draws", label: "Draws", icon: <Shield size={16} /> },
    { value: "forfeits", label: "Forfeits", icon: <Flag size={16} /> },
  ];
  const selected = options.find((option) => option.value === value) ?? options[0];
  return (
    <div className="custom-menu">
      <button className={`menu-trigger ${open ? "open" : ""}`} onClick={() => setOpenMenu(open ? null : "result")}>
        <Trophy size={17} />
        <span>
          <small>Result</small>
          <strong>{selected.label}</strong>
        </span>
      </button>
      {open && (
        <div className="menu-popover compact-menu-popover">
          {options.map((option) => (
            <button
              className={value === option.value ? "selected" : ""}
              key={option.value}
              onClick={() => {
                onSelect(option.value);
                setOpenMenu(null);
              }}
            >
              {option.icon}
              <span>{option.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function groupModels(models: MenuModel[]) {
  const groups = new Map<string, MenuModel[]>();
  for (const model of models) {
    const provider = providerLabel(model.provider);
    groups.set(provider, [...(groups.get(provider) ?? []), model]);
  }
  return [...groups.entries()]
    .map(([provider, groupModels]) => ({ provider, models: groupModels.sort((a, b) => a.label.localeCompare(b.label)) }))
    .sort((a, b) => a.provider.localeCompare(b.provider));
}

function resultClassForModel(game: GameSummary, modelId: string): string {
  if (game.result === "1/2-1/2") return "draw";
  if (game.winner_engine_id === modelId) return "model-win";
  if (game.result === "1-0" || game.result === "0-1") return "model-loss";
  if (game.result_source?.includes("forfeit")) return "forfeit";
  return "decisive";
}

function perspectiveResultLabel(game: GameSummary, modelId: string): string {
  if (game.result === "1/2-1/2") return "Draw";
  if (game.winner_engine_id === modelId) return "Win";
  if (game.result === "1-0" || game.result === "0-1") return "Loss";
  return resultLabel(game.result);
}
