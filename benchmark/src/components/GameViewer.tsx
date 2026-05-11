"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, Shield } from "lucide-react";

import { GameReplay } from "@/components/GameReplay";
import { fetchGameDetail, fetchLeaderboard } from "@/core/benchmark-api";
import { hasSupabaseConfig } from "@/core/supabase";
import type { GameDetail, LeaderboardRow } from "@/core/types";

export function GameViewer({ gameId: initialGameId }: { gameId?: string }) {
  const searchParams = useSearchParams();
  const gameId = initialGameId ?? searchParams.get("game") ?? "";
  const configured = hasSupabaseConfig();
  const [models, setModels] = useState<LeaderboardRow[]>([]);
  const [detail, setDetail] = useState<GameDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!configured || !gameId) return;
    setLoading(true);
    setError("");
    Promise.all([fetchLeaderboard(), fetchGameDetail(gameId)])
      .then(([rows, game]) => {
        setModels(rows);
        setDetail(game);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [configured, gameId]);

  if (!configured) {
    return (
      <section className="games-shell">
        <div className="setup-notice large">
          <Shield size={24} style={{ marginBottom: "1rem", color: "var(--brand)" }} />
          <p>The detailed game archive requires a database connection, which is not currently configured for this deployment.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="game-viewer-shell">
      <div className="viewer-topbar">
        <Link className="icon-text-button" href="/games/">
          <ArrowLeft size={16} /> All games
        </Link>
        {loading && <span>Loading game...</span>}
      </div>
      {error && <div className="setup-notice error">{error}</div>}
      {!gameId && <div className="loading-panel">Choose a game from the archive.</div>}
      {detail ? <GameReplay detail={detail} models={models} loading={loading} /> : gameId && !error && <div className="loading-panel">Loading game...</div>}
    </section>
  );
}
