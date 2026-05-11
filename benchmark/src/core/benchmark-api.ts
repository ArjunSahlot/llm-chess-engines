"use client";

import type { SupabaseClient } from "@supabase/supabase-js";

import { getSupabaseClient } from "./supabase";
import type { BenchmarkSummary, GameDetail, GameError, GameSummary, LeaderboardRow, MoveRecord } from "./types";

const LLM_EXCLUDED_PROVIDERS = new Set(["stockfish", "megalodon"]);

function client(): SupabaseClient {
  const supabase = getSupabaseClient();
  if (!supabase) throw new Error("Supabase is not configured.");
  return supabase;
}

export async function fetchLeaderboard(limit?: number): Promise<LeaderboardRow[]> {
  let query = client().from("chessbench_leaderboard_public").select("*").order("rank", { ascending: true });
  if (limit) query = query.limit(limit);
  const { data, error } = await query;
  if (error) throw error;
  return (data ?? []) as LeaderboardRow[];
}

export async function fetchSummary(): Promise<BenchmarkSummary> {
  const supabase = client();
  const [{ count: totalGames, error: totalError }, { count: finishedGames, error: finishedError }, { count: moves, error: movesError }, leaderboard] =
    await Promise.all([
      supabase.from("chessbench_games_public").select("game_id", { count: "exact", head: true }),
      supabase.from("chessbench_games_public").select("game_id", { count: "exact", head: true }).eq("status", "finished"),
      supabase.from("chessbench_moves_public").select("game_id", { count: "exact", head: true }),
      fetchLeaderboard(),
    ]);
  if (totalError) throw totalError;
  if (finishedError) throw finishedError;
  if (movesError) throw movesError;

  const llmRows = leaderboard.filter((row) => !LLM_EXCLUDED_PROVIDERS.has(row.provider ?? ""));
  const latest = await supabase
    .from("chessbench_games_public")
    .select("finished_at")
    .eq("status", "finished")
    .order("finished_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (latest.error) throw latest.error;

  return {
    latest_finished_at: latest.data?.finished_at ?? null,
    finished_games: finishedGames ?? 0,
    total_games: totalGames ?? 0,
    llm_models: llmRows.length,
    generated_engines: llmRows.length,
    moves: moves ?? 0,
  };
}

export async function fetchGames(params: {
  search?: string;
  model?: string;
  opponent?: string;
  result?: string;
  offset?: number;
  limit?: number;
}): Promise<{ games: GameSummary[]; count: number }> {
  const supabase = client();
  const from = params.offset ?? 0;
  const to = from + (params.limit ?? 50) - 1;
  let query = supabase
    .from("chessbench_games_public")
    .select("*", { count: "exact" })
    .order("plies", { ascending: false, nullsFirst: false })
    .order("finished_at", { ascending: false, nullsFirst: false })
    .range(from, to);

  if (params.model && params.model !== "all") {
    query = query.contains("participants", [params.model]);
  }
  if (params.opponent && params.opponent !== "all") {
    query = query.contains("participants", [params.opponent]);
  }
  if (params.result && params.result !== "all") {
    if (params.result === "draws") query = query.eq("result", "1/2-1/2");
    if (params.result === "decisive") query = query.in("result", ["1-0", "0-1"]);
    if (params.result === "forfeits") query = query.ilike("result_source", "%forfeit%");
  }
  if (params.search?.trim()) {
    const text = params.search.trim().replaceAll(",", " ");
    query = query.or(
      `white_name.ilike.%${text}%,black_name.ilike.%${text}%,reason.ilike.%${text}%,game_id.ilike.%${text}%`,
    );
  }

  const { data, count, error } = await query;
  if (error) throw error;
  return { games: (data ?? []) as GameSummary[], count: count ?? 0 };
}

export async function fetchGameDetail(gameId: string): Promise<GameDetail> {
  const supabase = client();
  const [{ data: game, error: gameError }, { data: moves, error: movesError }, { data: errors, error: errorsError }] =
    await Promise.all([
      supabase.from("chessbench_games_public").select("*").eq("game_id", gameId).maybeSingle(),
      supabase.from("chessbench_moves_public").select("*").eq("game_id", gameId).order("ply", { ascending: true }),
      supabase.from("chessbench_game_errors_public").select("*").eq("game_id", gameId).order("created_at", { ascending: true }),
    ]);
  if (gameError) throw gameError;
  if (movesError) throw movesError;
  if (errorsError) throw errorsError;
  if (!game) throw new Error("Game not found.");
  return { ...(game as GameSummary), moves: (moves ?? []) as MoveRecord[], errors: (errors ?? []) as GameError[] };
}
