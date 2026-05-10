from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness.config import provider_defaults
from harness.runner import GenerationRunner
from harness.types import RunConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark LLMs by generating C++ chess engines.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Run one engine-generation attempt.")
    generate.add_argument("--provider", required=True, help="Provider name, e.g. openai, anthropic, gemini, deepseek, kimi.")
    generate.add_argument("--model", required=True, help="Provider model identifier.")
    generate.add_argument("--run-id", required=True, help="Deterministic run id under generations/[provider-model]/.")
    generate.add_argument("--api-key-env", help="Environment variable containing the provider API key.")
    generate.add_argument("--base-url", help="Optional OpenAI-compatible base URL.")
    generate.add_argument("--temperature", type=float, default=0.2)
    generate.add_argument("--max-turns", type=int, default=16)
    generate.add_argument("--timeout-seconds", type=int, default=60)
    generate.add_argument("--root", type=Path, default=Path("generations"))
    return parser


def run_generate(args: argparse.Namespace) -> int:
    api_key_env, base_url = provider_defaults(args.provider)
    config = RunConfig(
        provider=args.provider,
        model=args.model,
        run_id=args.run_id,
        api_key_env=args.api_key_env or api_key_env,
        base_url=args.base_url or base_url,
        temperature=args.temperature,
        max_turns=args.max_turns,
        timeout_seconds=args.timeout_seconds,
        root=args.root,
    )
    manifest = GenerationRunner(config).run()
    print(json.dumps(manifest.to_dict(), indent=2))
    return 0 if manifest.compile_ok else 1


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "generate":
        return run_generate(args)
    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
