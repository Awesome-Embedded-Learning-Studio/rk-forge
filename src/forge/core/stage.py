"""Stage — content-hash incremental stage skipping.

Faithful port of ``lib/stage.sh``. rk-forge's answer to RK-SDK ``build.sh``
rebuilding everything every time: a stage reruns only when its INPUTS (sources +
config + patches + DT) change, not merely when an output artifact is absent.

The fingerprint is a sha1 over a deterministic representation:

* a ``stage=<name> arch=<ARCH> cross=<CROSS_COMPILE>`` header (so an arch switch
  invalidates every stage), then
* per input IN INPUT ORDER: a directory is reduced via ``find … -printf '%P %s
  %T@'`` to its build-relevant files (``*.c/*.h/*.S/*.dts/*.dtsi/*.config/
  defconfig/series/*.patch/Kconfig*/Makefile*``), sorted within that dir; a file
  is one ``stat -c '%n %s %Y'`` line.

Dir inputs hash the **float** mtime (find ``%T@``); file inputs hash the
**integer** mtime (stat ``%Y``) — that asymmetry is in ``stage.sh`` itself, so
the SAME ``find``/``stat`` tools are used here (not a Python re-implementation)
to keep fingerprints **byte-identical** to the bash version → existing
``.fingerprint`` state carries over, and legacy-vs-new ``run_stage`` behaves
identically. Only sizes + mtimes are hashed (a touch/edit changes the mtime).
``run()`` is the ``run_stage`` replacement: skip when the stored fingerprint
matches unless ``force``/``no_skip``.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from forge.config.board import Board
from forge.core.log import Log

# build-relevant file globs under a directory input (stage.sh's find -name list).
_FIND_NAMES = [
    "*.c", "*.h", "*.S", "*.dts", "*.dtsi", "*.config", "defconfig",
    "series", "*.patch", "Kconfig*", "Makefile*",
]


def _find_argv(p: Path) -> list[str]:
    """The exact ``find`` invocation stage.sh uses for a directory input:
    ``find <dir> -type f ( -name a -o -name b -o … ) -printf '%P %s %T@\\n'``."""
    expr: list[str] = []
    for i, name in enumerate(_FIND_NAMES):
        if i:
            expr.append("-o")
        expr += ["-name", name]
    return ["find", str(p), "-type", "f", "(", *expr, ")", "-printf", "%P %s %T@\n"]


class Stage:
    """Content-hash stage skipper (port of lib/stage.sh)."""

    def __init__(self, state_dir: Path, board: Board, log: Log | None = None):
        self.state_dir = Path(state_dir)
        self.board = board
        self.log = log or Log()

    def fingerprint(self, name: str, inputs: list[Path | str]) -> str:
        lines = [f"stage={name} arch={self.board.arch} cross={self.board.toolchain_prefix}"]
        for p in inputs:
            p = Path(p)
            if p.is_dir():
                cp = subprocess.run(_find_argv(p), capture_output=True, text=True)
                lines.extend(sorted(cp.stdout.splitlines()))   # per-dir sort (bash)
            elif p.is_file():
                cp = subprocess.run(["stat", "-c", "%n %s %Y", str(p)],
                                    capture_output=True, text=True)
                lines.append(cp.stdout.strip())
        return hashlib.sha1(("\n".join(lines) + "\n").encode()).hexdigest()

    def up_to_date(self, name: str, inputs: list[Path | str]) -> bool:
        fp_file = self.state_dir / f"{name}.fingerprint"
        if not fp_file.is_file():
            return False
        return fp_file.read_text().strip() == self.fingerprint(name, inputs)

    def mark_done(self, name: str, inputs: list[Path | str]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / f"{name}.fingerprint").write_text(self.fingerprint(name, inputs) + "\n")

    def run(self, name: str, inputs: list[Path | str], action, *,
            force: bool = False, no_skip: bool = False) -> bool:
        """Run ``action`` unless the stage's inputs are unchanged.

        Returns True if the stage RAN, False if it skipped. ``force``/``no_skip``
        bypass the skip. ``action`` is a zero-arg callable (the leaf forge command).
        """
        if not force and not no_skip and self.up_to_date(name, inputs):
            self.log.info(f"{name}: up-to-date (skip; --force to rerun)")
            return False
        self.log.info(f"{name}: running")
        action()
        self.mark_done(name, inputs)
        self.log.ok(f"{name}: done")
        return True
