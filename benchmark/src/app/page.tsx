import Link from "next/link";
import { ArrowRight, BrainCircuit, Code2, Swords, Trophy } from "lucide-react";

import { EloBar, RecordBadge } from "@/components/LeaderboardVisuals";
import { ModelMark } from "@/components/ModelMark";
import { SiteNav } from "@/components/SiteNav";
import { formatDate, formatInteger } from "@/core/format";
import { landingSnapshot } from "@/core/landing-snapshot";
import type { BenchmarkSummary, LandingSnapshot, LeaderboardRow } from "@/core/types";

const snapshot = landingSnapshot as LandingSnapshot;
const summary = snapshot.summary as BenchmarkSummary;
const leaderboard = snapshot.leaderboard.slice(0, 8) as LeaderboardRow[];
const minElo = Math.min(...snapshot.leaderboard.map((row) => row.elo));
const maxElo = Math.max(...snapshot.leaderboard.map((row) => row.elo));

export default function HomePage() {
  return (
    <>
      <SiteNav />
      <main>
        <section className="hero-shell">
          <div className="hero-board" aria-hidden="true" />
          <div className="hero-content page-pad">
            <div className="hero-copy">
              <h1>Chess<span className="brand-bench">Bench</span></h1>
              <p className="hero-lede">
                Language models are asked to write complete C++ UCI chess engines in a standardized agentic harness,
                then the generated engines play each other to climb the ELO leaderboard.
              </p>
              <div className="hero-actions">
                <Link className="primary-action" href="/leaderboard/">
                  View leaderboard <ArrowRight size={18} />
                </Link>
                <Link className="secondary-action" href="/methodology/">
                  How it works
                </Link>
              </div>
              <div className="hero-stats llm-stats">
                <Metric icon={<Code2 />} label="Engines" value={formatInteger(summary.generated_engines)} />
                <Metric icon={<Swords />} label="Finished games" value={formatInteger(summary.finished_games)} />
                <Metric icon={<BrainCircuit />} label="Ply count" value={formatInteger(summary.moves)} />
              </div>
            </div>

            <div className="leaderboard-panel" aria-label="ChessBench ELO leaderboard">
              <div className="panel-title-row">
                <div>
                  <h2>ELO standings</h2>
                </div>
                <span className="freshness">
                  {summary.latest_finished_at ? `Updated ${formatDate(summary.latest_finished_at)}` : `Snapshot ${formatDate(snapshot.generated_at)}`}
                </span>
              </div>

              <div className="leaderboard-list">
                {leaderboard.map((row, index) => (
                  <Link
                    className="leaderboard-row professional"
                    href={`/games/?model=${encodeURIComponent(row.engine_id)}`}
                    key={row.engine_id}
                  >
                    <span className="rank-cell">{row.rank ?? index + 1}</span>
                    <ModelMark model={row} />
                    <EloBar row={row} minElo={minElo} maxElo={maxElo} />
                    <RecordBadge row={row} compact />
                  </Link>
                ))}
                <Link className="full-leaderboard-link" href="/leaderboard/">
                  See full leaderboard <ArrowRight size={16} />
                </Link>
              </div>
            </div>
          </div>
        </section>

        <section className="section-band page-pad">
          <div className="section-heading-row">
            <div>
              <h2>What ChessBench measures</h2>
            </div>
            <Link className="text-link" href="/methodology/">
              Read methodology <ArrowRight size={16} />
            </Link>
          </div>
          <div className="signal-grid">
            <SignalCard
              icon={<BrainCircuit />}
              title="Autonomous Efficiency"
              body="Operating with capped iteration limits, models must strategically leverage compiler feedback and make decisive edits to construct a functional engine before running out of cycles."
            />
            <SignalCard
              icon={<Code2 />}
              title="Uncompromising Precision"
              body="The simulation is merciless to logical flaws. A single mistake in move generation or board state handling leads straight to an illegal move and a large hit to hard-earned ELO."
            />
            <SignalCard
              icon={<Trophy />}
              title="Algorithmic Dominance"
              body="Simply knowing the rules isn't enough to win. Champions are crowned by their ability to successfully weave together complex search heuristics and deep performance enhancements."
            />
          </div>
        </section>
      </main>
    </>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="metric">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SignalCard({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <article className="signal-card">
      <div className="signal-icon">{icon}</div>
      <strong>{title}</strong>
      <p>{body}</p>
    </article>
  );
}
