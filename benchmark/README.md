# ChessBench Benchmark Site

Static Next.js site for publishing ChessBench results with an optional Supabase
backend for the full game archive.

## Local development

```bash
cd benchmark
npm install
npm run dev
```

The landing page and `/leaderboard` use a tiny static snapshot at
`public/data/landing-data.json`, generated from `results/elo_leaderboard.json`
and `results/competition.sqlite3`. The full game archive and replay views still
require Supabase because they are too large to bundle into the deployed site.

Set the public Supabase variables to exercise the games archive in development:

```bash
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
```

## Static export

```bash
cd benchmark
npm run build
```

The app uses `output: "export"` and writes the deployable static site to
`benchmark/out`. `npm run build` refreshes the static landing snapshot before
the Next.js export.

To refresh that snapshot directly:

```bash
uv run llm-chess export-landing-snapshot
```

## Supabase sync

1. Run `supabase/schema.sql` in your Supabase project.
2. Set `NEXT_PUBLIC_SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.
3. Force-push local results:

```bash
uv run llm-chess sync-supabase --dry-run
uv run llm-chess sync-supabase
```

The sync command treats local files as the source of truth. It clears the
ChessBench Supabase tables first, then uploads the local SQLite games, moves,
engine metadata, errors, capabilities, and ELO snapshot.

The public game archive reads from Supabase when `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` are present at build time. Without those values,
data-heavy pages intentionally show a setup notice instead of falling back to
local game files.
