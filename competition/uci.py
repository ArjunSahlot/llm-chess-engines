from __future__ import annotations

import queue
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path


EventSink = Callable[[str, str], None]


class UciEngine:
    def __init__(self, command: list[str], cwd: Path, event_sink: EventSink) -> None:
        self.command = command
        self.cwd = cwd
        self.event_sink = event_sink
        self.proc: subprocess.Popen[str] | None = None
        self.lines: queue.Queue[str] = queue.Queue()
        self.reader: threading.Thread | None = None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.reader = threading.Thread(target=self._read_loop, daemon=True)
        self.reader.start()

    def initialize(self, timeout: float) -> None:
        self.send("uci")
        self.wait_for("uciok", timeout)
        self.send("isready")
        self.wait_for("readyok", timeout)

    def send(self, line: str) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise RuntimeError("engine is not running")
        self.event_sink("in", line)
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def wait_bestmove(self, timeout: float) -> tuple[str, int]:
        started = time.monotonic()
        while True:
            line = self._get_line(max(0.01, timeout - (time.monotonic() - started)))
            if line.startswith("bestmove "):
                parts = line.split()
                return (parts[1] if len(parts) > 1 else "0000", int((time.monotonic() - started) * 1000))
            if time.monotonic() - started >= timeout:
                raise TimeoutError(f"timed out waiting for bestmove after {timeout}s")

    def wait_for(self, token: str, timeout: float) -> None:
        started = time.monotonic()
        while True:
            line = self._get_line(max(0.01, timeout - (time.monotonic() - started)))
            if line == token:
                return
            if time.monotonic() - started >= timeout:
                raise TimeoutError(f"timed out waiting for {token}")

    def stop(self) -> None:
        if self.proc is None:
            return
        try:
            if self.proc.poll() is None:
                self.send("quit")
                self.proc.wait(timeout=1)
        except Exception:
            if self.proc.poll() is None:
                self.proc.kill()
        finally:
            self.proc = None

    def _get_line(self, timeout: float) -> str:
        if self.proc is not None and self.proc.poll() is not None and self.lines.empty():
            raise RuntimeError(f"engine exited with code {self.proc.returncode}")
        try:
            return self.lines.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("timed out waiting for engine output") from exc

    def _read_loop(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for raw in self.proc.stdout:
            line = raw.rstrip("\n")
            self.event_sink("out", line)
            self.lines.put(line)
