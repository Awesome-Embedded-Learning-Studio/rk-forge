"""Rkbin — resolve the board's rkbin blob tuple from the single pinned submodule.

Replaces lib/rkbin.sh. The board's patterns (``Board.rkbin_ddr/usbplug/spl/tee/
bl31`` + ``blob_subdir`` + ``tee_exclude``) drive a version-sort glob over
``project.rkbin_dir / blob_subdir``. pack-fit (needs ``tee``) and pack-loader
(needs ``ddr/usbplug/spl/bl31``) both route through here so the SPL↔tee hash pair
stays single-sourced — both MUST draw from the same ``project.rkbin_dir``.

No subprocess: pure glob + sort, so a wrong pattern fails loudly here, not later
when a mismatched SPL boots a BL31 into the wrong address (the rk3588 bootloop).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log

_NUM_SPLIT = re.compile(r"(\d+)")


def _version_key(name: str):
    """GNU ``sort -V`` analogue: split on digit runs, compare numerics as int.

    e.g. ``rk3588_spl_v1.14.bin`` sorts above ``..._v1.5.bin`` (14 > 5), matching
    ``sort -V`` so the same blob is picked as the bash resolver picked.
    """
    return tuple(int(t) if t.isdigit() else t for t in _NUM_SPLIT.split(name))


@dataclass(frozen=True)
class BlobTuple:
    """The resolved blob basenames + the dir that holds them."""

    ddr: str
    usbplug: str
    spl: str
    tee: str
    bl31: str | None     # None when the board has no ATF stage (RK3506)
    blob_dir: Path       # <rkbin_dir>/<blob_subdir>

    def path(self, basename: str) -> Path:
        """Absolute path to a resolved blob basename."""
        return self.blob_dir / basename


class Rkbin:
    """Resolves a board's blob tuple by version-sort glob over the rkbin submodule."""

    def __init__(self, project: Project, board: Board, log: Log | None = None):
        self.project = project
        self.board = board
        self.log = log or Log()

    def resolve(self) -> BlobTuple:
        b = self.board
        if not self.project.rkbin_dir.is_dir():
            self.log.die(f"rkbin source not found: {self.project.rkbin_dir} (init submodule / fetch-deps)")
        blob_dir = self.project.rkbin_dir / b.rkbin_blob_subdir
        if not blob_dir.is_dir():
            self.log.die(f"no {b.rkbin_blob_subdir} under {self.project.rkbin_dir} ({blob_dir})")

        return BlobTuple(
            ddr=self._resolve(blob_dir, b.rkbin_ddr, "DDR"),
            usbplug=self._resolve(blob_dir, b.rkbin_usbplug, "usbplug"),
            spl=self._resolve(blob_dir, b.rkbin_spl, "SPL"),
            tee=self._resolve(blob_dir, b.rkbin_tee, "tee", b.rkbin_tee_exclude or ""),
            bl31=self._resolve(blob_dir, b.rkbin_bl31, "BL31") if b.rkbin_bl31 else None,
            blob_dir=blob_dir,
        )

    def _resolve(self, blob_dir: Path, pattern: str, label: str, exclude: str = "") -> str:
        hits = [p.name for p in blob_dir.glob(pattern)]
        if exclude:
            hits = [h for h in hits if exclude not in h]
        if not hits:
            self.log.die(f"{label} blob not found under {blob_dir} (pattern: {pattern})")
        hits.sort(key=_version_key)
        return hits[-1]   # highest version
