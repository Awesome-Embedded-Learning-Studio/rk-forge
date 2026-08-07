"""Logging — the single source of truth for forge output.

Honours the bash lib/log.sh seam contract: human-facing chatter → stdout,
diagnostics (warn/error/debug) → stderr. Data meant for capture (a stage's
machine-readable product) must never be printed to stdout — that's what lets a
future wrapper capture a stage's output cleanly.
"""
from __future__ import annotations

import sys
from typing import TextIO

# ANSI codes (empty when not a TTY / colour disabled).
_COLORS = {
    "blue": "\033[34m", "green": "\033[32m", "yellow": "\033[33m",
    "red": "\033[31m", "dim": "\033[2m", "off": "\033[0m",
}


class Log:
    """Stamped, level-prefixed logger. info/ok → stdout; warn/error/debug → stderr."""

    def __init__(self, stream_out: TextIO | None = None, stream_err: TextIO | None = None,
                 color: bool | None = None, debug: bool = False):
        self._out = stream_out if stream_out is not None else sys.stdout
        self._err = stream_err if stream_err is not None else sys.stderr
        self._color = color if color is not None else self._err.isatty()
        self._debug = debug

    def _emit(self, stream: TextIO, tag: str, msg: str, color: str) -> None:
        c = self._c(color)
        off = self._c("off")
        stream.write(f"{c}[{tag}]{off} {msg}\n")
        stream.flush()

    def _c(self, name: str) -> str:
        return _COLORS[name] if self._color else ""

    # ── levels ───────────────────────────────────────────────────────────────
    def info(self, msg: str) -> None:
        self._emit(self._out, "INFO", msg, "blue")

    def ok(self, msg: str) -> None:
        self._emit(self._out, " OK ", msg, "green")

    def warn(self, msg: str) -> None:
        self._emit(self._err, "WARN", msg, "yellow")

    def error(self, msg: str) -> None:
        self._emit(self._err, "ERR ", msg, "red")

    def debug(self, msg: str) -> None:
        if self._debug:
            self._emit(self._err, "DBG ", msg, "dim")

    def die(self, msg: str) -> None:
        """Log an error and exit(1)."""
        self.error(msg)
        raise SystemExit(1)
