"""DriverDrop — materialize a WiFi driver drop into the kernel tree.

Replaces ``fetch-rtl8852bs-driver.sh`` + ``fetch-rtl8733bu-driver.sh`` with ONE
class (the two scripts were ~identical). The board's ``wifi_driver`` field
(``rtl8733bu`` / ``rtl8852bs``) selects which; the fork IS the ready-to-build
driver, so this only:

1. clone the driver source @ the pinned ref into the kernel tree, capture HEAD sha
2. (optional) apply a forge-local adapt patch — e.g. rtl8852bs's ``arm_rk.mk``
   drops the ``ARCH=arm`` + vendor toolchain poison and swaps a platform object
   for a mainline stub. The patch is data-driven: any
   ``boards/<board>/patches/linux/*<driver>*forge-adapt*.patch`` is applied (rtl8733bu
   has none — its port is baked into the fork).
3. strip the drop's ``.git`` (the drop is gitignored working source)
4. clean stale build artifacts
5. gitignore the drop via the kernel clone's ``.git/info/exclude`` (NOT a tracked
   ``.gitignore`` edit) so ``git status`` stays clean

Idempotent: a ``.forge-fetched`` marker records the cloned sha; re-run no-ops
unless ``--force``. Run BEFORE ``forge apply`` so the driver's ``Kconfig`` exists
when the wire patch sources it.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from forge import fetch
from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.proc import Proc

# stale build artifacts the fork might ship (defensive; it ships none).
_ARTIFACT_GLOBS = ("*.o", "*.o.cmd", "*.ko", "*.ko.cmd", "*.mod", "*.mod.c",
                   "*.mod.o", ".*.cmd", "Module.symvers", "modules.order",
                   ".module-common.o", ".tmp_*")


class DriverDrop:
    """Materializes the board's WiFi driver into its kernel tree."""

    def __init__(self, board: Board, project: Project,
                 proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)
        self.driver = board.wifi_driver
        self.linux_dir = project.src_dir / board.id / "linux"
        self.drop = self.linux_dir / "drivers" / "net" / "wireless" / "realtek" / self.driver
        self.marker = self.drop / ".forge-fetched"

    def fetch(self, *, force: bool = False) -> None:
        if not self.driver:
            self.log.info(f"no wifi_driver for board {self.board.id!r} — skip driver drop")
            return
        pin = fetch.read_source(self.board.sources, self.project.sources, self.driver)
        if pin is None:
            self.log.die(f"missing source: {self.driver} (forge.yaml sources:{self.driver})")
        url, ref = pin
        if not self.linux_dir.is_dir():
            self.log.die(f"linux tree not found: {self.linux_dir} (run: forge fetch linux)")

        self.drop.parent.mkdir(parents=True, exist_ok=True)
        if self.marker.is_file() and not force:
            self.log.ok(f"{self.driver}/ already fetched @ {self.marker.read_text().strip()} "
                        f"— --force to refresh from {ref}")
            return

        # 1. clone @ pin (shallow; the drop is just working source).
        self.log.info(f"cloning {url} @ {ref} → {self.drop}")
        shutil.rmtree(self.drop, ignore_errors=True)
        sha = fetch.clone_shallow_sha(self.proc, url, ref, self.drop, self.log)

        # 2. optional forge-local adapt patch (data-driven; rtl8852bs has one,
        #    rtl8733bu has none). Applied BEFORE stripping .git — the drop is
        #    gitignored, so this can't go through apply-series / git am.
        self._apply_adapt_patch()

        # 3. strip the drop's .git.
        shutil.rmtree(self.drop / ".git", ignore_errors=True)
        self.marker.write_text(sha + "\n")

        # 4. clean stale build artifacts.
        for pat in _ARTIFACT_GLOBS:
            for p in self.drop.rglob(pat):
                p.unlink(missing_ok=True)

        # 5. gitignore the drop via the kernel clone's info/exclude.
        self._add_to_exclude()

        self.log.ok(f"{self.driver} driver materialized @ {sha} (from {url} {ref})")
        self.log.info("next: forge apply --component linux (wire patch), then build the module")

    def _apply_adapt_patch(self) -> None:
        patch_dir = self.project.root / "boards" / self.board.id / "patches" / "linux"
        if not patch_dir.is_dir():
            return
        candidates = [p for p in patch_dir.iterdir()
                      if self.driver in p.name and "forge-adapt" in p.name and p.suffix == ".patch"]
        for patch in candidates:
            self.log.info(f"applying forge-adapt patch: {patch.name}")
            rc = self.proc.run(["git", "-C", str(self.drop), "apply",
                                "--whitespace=nowarn", str(patch)],
                               check=False, quiet=True).returncode
            if rc != 0:
                self.log.die(
                    f"forge-adapt patch failed to apply: {patch.name} — "
                    "the fork's main may have advanced; refresh the patch"
                )
            self.log.ok(f"forge-adapt applied ({patch.name})")

    def _add_to_exclude(self) -> None:
        """Ignore the drop WITHOUT editing a tracked .gitignore."""
        cp = self.proc.run(["git", "-C", str(self.linux_dir),
                            "rev-parse", "--absolute-git-dir"], capture=True, quiet=True)
        exclude = Path(cp.stdout.strip()) / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.touch()
        entry = f"drivers/net/wireless/realtek/{self.driver}/"
        lines = exclude.read_text().splitlines() if exclude.is_file() else []
        if entry not in lines:
            with open(exclude, "a") as f:
                f.write(f"\n# forge: fetched vendor driver drop\n{entry}\n")
