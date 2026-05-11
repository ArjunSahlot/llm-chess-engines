# ChessBench

Benchmarking LLMs' ability to generate strong chess engines in a standardized harness.

## Project Structure

- **Harness & Generation (`adapters/`, `tools/`, `harness/`)**: The core structure to elicit engine generations from a wide variety of supported LLM providers. It places models in a standardized harness equipped with confined file tools and a compiler tool to yield valid C++ engines.
- **Competition Runner (`competition/`)**: The logic to run an ongoing round-robin tournament. Compiled engines are practically ELO-tested against each other to evaluate their playing strength.
- **Local GUI (`web-chess-gui/`)**: A small, local web application for quickly viewing games, stats, and results from the internal SQLite competition database.
- **Benchmark Website (`benchmark/`)**: Contains the full source code for the public benchmark website, [chessbench.live](https://chessbench.live).

## Generate an engine

```bash
uv run llm-chess generate --provider openai --model gpt-5.5 --run-id smoke-001
```

Runs are isolated under `generations/[provider-model]/[run-id]`. The generated engine must be C++ with a root `Makefile`; the harness exposes only confined file tools and a `compile_engine` tool that runs `make` in the run directory.

Adapters stream by default, which keeps high token-cap runs compatible with providers that require streaming for long outputs. Use `--no-stream` only when debugging a non-streaming provider path.

Large source files should be written in chunks with `write_file` followed by `append_file`. This avoids provider output limits truncating a tool call midway through a large file body. Use `--max-output-tokens` to raise the per-response output budget when the provider/model supports it.

Provider defaults:
- `openai`: `OPENAI_API_KEY`
- `anthropic`: `ANTHROPIC_API_KEY`
- `gemini`: `GEMINI_API_KEY`
- `deepseek`: `DEEPSEEK_API_KEY`, `https://api.deepseek.com`
- `kimi` / `moonshot`: `MOONSHOT_API_KEY`, `https://api.moonshot.ai/v1`

## Run the round robin

```bash
uv run llm-chess compete --forever --movetime-ms 100
```

The competition runner discovers compiled generated engines from `generations/`, schedules the least-played ordered pairing next, validates moves with `python-chess`, and persists all engine metadata, games, moves, PGN, raw UCI output, time-control config, and aggregate scores to `results/competition.sqlite3`.

Useful smoke run:
```bash
uv run llm-chess compete --max-games 2 --movetime-ms 50
```

Clock mode is also supported:
```bash
uv run llm-chess compete --forever --clock-ms 60000 --increment-ms 500 --move-overhead-ms 20
```

For overnight runs, pass multiple repeatable `--time-control` values. They cycle by persisted game count, so restarting the runner continues the rotation:
```bash
uv run llm-chess compete --forever \
  --time-control movetime:50 \
  --time-control movetime:200 \
  --time-control clock:60000+500
```

Openings are randomized from `competition/openings.txt` by default. Each non-empty line is a space-separated UCI move sequence, and the selected opening line, source, and resulting FEN are persisted with the game. Use `--openings-file path/to/book.txt` to swap books or `--no-openings` to disable this.

Before an engine receives opening positions, the runner probes whether it can return a legal move from a non-start FEN. Engines that fail still play in the round robin, but from startpos only; the skip reason is stored in SQLite and PGN as `OpeningSkipped`.

Use `--max-plies`, `--handshake-timeout-seconds`, and `--move-timeout-seconds` to keep malformed generated engines from blocking the loop.

## Build the ELO leaderboard

```bash
uv run llm-chess leaderboard
```

The leaderboard TUI reads `results/competition.sqlite3`, lets you set known anchor ratings for engines such as Stockfish, and saves `results/elo_anchors.json`, `results/elo_leaderboard.json`, and `results/elo_leaderboard.md`. You can also run it non-interactively:

```bash
uv run llm-chess leaderboard --anchor stockfish=3200 --no-tui
```