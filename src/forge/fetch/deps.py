"""DepsFetcher — clone the upstream source trees at their pinned refs.

Replaces ``scripts/fetch-deps.sh``. Implements the fetched-clone + tracked-pin
model: the src trees (linux/uboot/buildroot/openwrt) are gitignored local clones
(NOT submodules — patched trees with a submodule drift the superproject gitlink);
board.yaml / forge.yaml ``sources:`` lock the exact ref for reproducibility.

Target dirs: linux/uboot/openwrt are **per-board** (``src/<board>/<name>`` — two
boards can't share a patched tree); buildroot is **shared** (no patches; the
board delta is the ``BR2_EXTERNAL`` tree). Idempotent: trees already present are
skipped (``rm -rf`` to refetch @ the pin). Built on the shared
:mod:`forge.fetch` primitives.
"""
from __future__ import annotations

from pathlib import Path

from forge import fetch
from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.proc import Proc

# `all` covers the buildroot-profile deps. openwrt is NOT in `all` — it's a
# large optional tree fetched only for the openwrt profile.
_ALL = ("linux", "uboot", "buildroot")


class DepsFetcher:
    """Fetches pinned source trees (linux / uboot / buildroot / openwrt)."""

    def __init__(self, board: Board, project: Project,
                 proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)

    def fetch(self, what: str = "all") -> None:
        names = _ALL if what == "all" else [what]
        for name in names:
            self._fetch_one(name)
        self.log.info("next: forge apply for linux/uboot (+openwrt if --rootfs=openwrt) "
                      "+ forge fetch driver")

    def _target(self, name: str) -> Path:
        # per-board for linux/uboot/openwrt; shared for buildroot.
        if name == "buildroot":
            return self.project.buildroot_dir
        return self.project.src_dir / self.board.id / name

    def _fetch_one(self, name: str) -> None:
        pin = fetch.read_source(self.board.sources, self.project.sources, name)
        if pin is None:
            self.log.warn(f"{name}: no pin file — skipping")
            return
        url, ref = pin
        target = self._target(name)
        if target.is_dir():
            self.log.info(f"{name}: already present ({target}) — skipping "
                          f"(rm -rf it to refetch @ {ref})")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        self.log.info(f"{name}: cloning {url} @ {ref} → {target}")
        fetch.clone_at_ref(self.proc, url, ref, target, self.log)
        self.log.ok(f"{name} @ {ref} → {target}")
