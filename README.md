# llm-chess-engines
Benchmarking LLMs ability to generate strong chess engines in a standardized harness.

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

The v1 scope is generation and compile verification. Match running, result analysis, and ELO reporting are intentionally left for the next layer.

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

Use `--max-plies`, `--handshake-timeout-seconds`, and `--move-timeout-seconds` to keep malformed generated engines from blocking the loop.
