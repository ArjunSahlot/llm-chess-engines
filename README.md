# llm-chess-engines
Benchmarking LLMs ability to generate strong chess engines in a standardized harness.

## Generate an engine

```bash
uv run llm-chess generate --provider openai --model gpt-5.5 --run-id smoke-001
```

Runs are isolated under `generations/[provider-model]/[run-id]`. The generated engine must be C++ with a root `Makefile`; the harness exposes only confined file tools and a `compile_engine` tool that runs `make` in the run directory.

Large source files should be written in chunks with `write_file` followed by `append_file`. This avoids provider output limits truncating a tool call midway through a large file body. Use `--max-output-tokens` to raise the per-response output budget when the provider/model supports it.

Provider defaults:

- `openai`: `OPENAI_API_KEY`
- `anthropic`: `ANTHROPIC_API_KEY`
- `gemini`: `GEMINI_API_KEY`
- `deepseek`: `DEEPSEEK_API_KEY`, `https://api.deepseek.com`
- `kimi` / `moonshot`: `MOONSHOT_API_KEY`, `https://api.moonshot.ai/v1`

The v1 scope is generation and compile verification. Match running, result analysis, and ELO reporting are intentionally left for the next layer.
