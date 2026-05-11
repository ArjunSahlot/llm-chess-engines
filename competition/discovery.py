from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from competition.models import Engine


_SKIP_NAMES = {
    "manifest.json",
    "transcript.jsonl",
    "Makefile",
}
_SKIP_SUFFIXES = {".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".hh", ".o", ".a", ".so", ".json", ".txt", ".pgn", ".log"}


def discover_engines(generations_root: Path) -> list[Engine]:
    root = generations_root.resolve()
    if not root.exists():
        return []

    engines: list[Engine] = []
    for run_dir in sorted(path for path in root.glob("*/*") if path.is_dir()):
        manifest = _read_manifest(run_dir / "manifest.json")
        executable = _find_executable(run_dir)
        if executable is None:
            continue
        provider_model = run_dir.parent.name
        run_id = run_dir.name
        engine_id = _engine_id(provider_model, run_id)
        engines.append(
            Engine(
                engine_id=engine_id,
                name=f"{provider_model}/{run_id}",
                provider_model=provider_model,
                run_id=run_id,
                root=run_dir.resolve(),
                command=[str(executable.resolve())],
                manifest_path=(run_dir / "manifest.json") if manifest is not None else None,
                manifest=manifest,
            )
        )
    return engines


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _find_executable(run_dir: Path) -> Path | None:
    candidates = []
    for path in run_dir.rglob("*"):
        if not path.is_file() or path.name in _SKIP_NAMES or path.suffix in _SKIP_SUFFIXES:
            continue
        try:
            mode = path.stat().st_mode
        except OSError:
            continue
        if mode & (os.X_OK | 0o111):
            candidates.append(path)
    if not candidates:
        return None
    candidates.sort(key=lambda path: (0 if path.name in {"engine", "chess_engine", "stockfish"} else 1, len(path.parts), str(path)))
    return candidates[0]


def _engine_id(provider_model: str, run_id: str) -> str:
    payload = f"{provider_model}\0{run_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
