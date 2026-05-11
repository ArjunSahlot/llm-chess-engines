import { EloBar, RecordBadge } from "@/components/LeaderboardVisuals";
import { ModelMark } from "@/components/ModelMark";
import { SiteNav } from "@/components/SiteNav";
import { formatInteger } from "@/core/format";
import { landingSnapshot } from "@/core/landing-snapshot";
import type { LandingSnapshot, LeaderboardRow } from "@/core/types";

const rows = (landingSnapshot as LandingSnapshot).leaderboard as LeaderboardRow[];
const minElo = Math.min(...rows.map((row) => row.elo));
const maxElo = Math.max(...rows.map((row) => row.elo));

export default function LeaderboardPage() {
  return (
    <>
      <SiteNav />
      <main className="leaderboard-page page-pad">
        <section className="table-hero">
          <p className="eyebrow">Full ELO leaderboard</p>
          <h1>Chess<span className="brand-bench">Bench</span> standings</h1>
          <p>
            Ratings are computed from generated-engine games. Stockfish and internal reference engines may appear as
            calibration or sanity-check entries, but the benchmark is about LLM-created engines.
          </p>
        </section>

        <div className="leaderboard-table">
          <div className="leaderboard-table-head">
            <span>Rank</span>
            <span>Model</span>
            <span>ELO</span>
            <span>Score</span>
            <span>Record</span>
            <span>Avg opponent</span>
          </div>
          {rows.map((row, index) => (
            <div className="leaderboard-table-row" key={row.engine_id}>
              <span className="rank-cell">{row.rank ?? index + 1}</span>
              <ModelMark model={row} />
              <EloBar row={row} minElo={minElo} maxElo={maxElo} />
              <span className="score-points">{row.score.toFixed(1)} / {formatInteger(row.games)}</span>
              <RecordBadge row={row} />
              <span className="avg-opponent-cell">{row.avg_opponent_elo ? formatInteger(row.avg_opponent_elo) : "n/a"}</span>
            </div>
          ))}
        </div>
      </main>
    </>
  );
}
