from __future__ import annotations

import re
from pathlib import Path


_SLUG_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def safe_slug(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.strip()).strip(".-").lower()
    if not slug:
        raise ValueError("slug cannot be empty")
    if slug in {".", ".."} or "/" in slug or "\\" in slug:
        raise ValueError(f"unsafe slug: {value!r}")
    return slug


class GenerationWorkspace:
    def __init__(self, root: Path, provider: str, model: str, run_id: str) -> None:
        self.root = root.resolve()
        provider_model = safe_slug(f"{provider}-{model}")
        self.run_id = safe_slug(run_id)
        self.path = (self.root / provider_model / self.run_id).resolve()

    def create(self) -> None:
        self.path.mkdir(parents=True, exist_ok=False)

    def resolve_inside(self, relative_path: str | Path) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ValueError("absolute paths are not allowed")
        resolved = (self.path / candidate).resolve()
        if resolved != self.path and self.path not in resolved.parents:
            raise ValueError(f"path escapes run directory: {relative_path}")
        return resolved
