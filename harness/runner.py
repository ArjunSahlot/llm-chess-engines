from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from adapters import ProviderAdapter, make_adapter
from harness.prompts import SYSTEM_PROMPT, USER_PROMPT
from harness.tools import execute_tool, tool_specs
from harness.types import Message, RunConfig, RunManifest
from harness.workspace import GenerationWorkspace


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    return repr(value)


class GenerationRunner:
    def __init__(self, config: RunConfig, adapter: ProviderAdapter | None = None) -> None:
        self.config = config
        self.adapter = adapter or make_adapter(config)
        self.workspace = GenerationWorkspace(config.root, config.provider, config.model, config.run_id)
        self.manifest = RunManifest(config.provider, config.model, config.run_id, str(self.workspace.path))
        self.transcript_path = self.workspace.path / "transcript.jsonl"
        self.manifest_path = self.workspace.path / "manifest.json"

    def run(self) -> RunManifest:
        self.workspace.create()
        self._write_manifest()
        messages = [Message("system", SYSTEM_PROMPT.format(**asdict(self.config))), Message("user", USER_PROMPT)]
        compile_ok = False
        final_text = ""

        try:
            self._record("start", {"config": asdict(self.config)})
            for turn in range(1, self.config.max_turns + 1):
                response = self.adapter.complete(messages, tool_specs(), self.config)
                final_text = response.text or final_text
                messages.append(Message("assistant", response.text, tool_calls=response.tool_calls))
                self._record("assistant", {"turn": turn, "response": response})

                if not response.tool_calls:
                    self.manifest.finish(status="completed", turns=turn, compile_ok=compile_ok, final_text=final_text)
                    self._write_manifest()
                    return self.manifest

                for call in response.tool_calls:
                    result = execute_tool(self.workspace, call)
                    compile_ok = result.name == "compile_engine" and result.ok
                    messages.append(Message("tool", result.content, tool_call_id=call.id, tool_name=result.name))
                    self._record("tool", {"turn": turn, "call": call, "result": result})

            self.manifest.finish(status="turn_limit", turns=self.config.max_turns, compile_ok=compile_ok, final_text=final_text)
            self._write_manifest()
            return self.manifest
        except Exception as exc:
            self.manifest.finish(status="error", turns=self.manifest.turns, compile_ok=compile_ok, final_text=final_text, error=str(exc))
            self._write_manifest()
            raise

    def _record(self, event: str, payload: dict[str, Any]) -> None:
        with self.transcript_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"event": event, **payload}, default=_json_default, ensure_ascii=False) + "\n")

    def _write_manifest(self) -> None:
        self.manifest_path.write_text(json.dumps(self.manifest.to_dict(), indent=2) + "\n", encoding="utf-8")
