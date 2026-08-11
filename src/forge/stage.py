"""StageRootfs — materialize the rootfs tree at ``out/rootfs/`` for packing.

Replaces ``scripts/stage-rootfs.sh``. Per architecture §5.3, this is **pure
materialization** — every customization (WiFi .ko, firmware, account, console,
watchdog, …) is baked by the base's NATIVE mechanism during ``forge build``
(buildroot post-build / openwrt package system / ubuntu chroot), so staging
just lays the tree down:

* buildroot — ``tar xf rootfs.tar``
* openwrt   — ``rsync TARGET_DIR/`` (kmod already in lib/modules)
* ubuntu    — ``tar xf ubuntu-rootfs.tar`` under fakeroot (preserves numeric
  root ownership across the stage→pack-emmc chain; the fakeroot state file is
  reloaded by pack-emmc before mke2fs)

The old stage-rootfs's post-extract provisioning (account re-creation, .ko drop,
firmware belt-and-suspenders, rk3588 console/watchdog) is GONE — moved into the
base builds (single-source, no build/stage drift). The fakeroot re-exec is
preserved via ``os.execvpe`` (§4.7); making it an explicit ``fakeroot forge`` is
F3 (the bash auto re-exec'd too — same behaviour).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.proc import Proc


class StageRootfs:
    """Materializes out/rootfs/ from the built rootfs source (profile-driven)."""

    def __init__(self, board: Board, project: Project,
                 proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)

    def stage(self, *, out_dir: Path, profile: str = "buildroot") -> None:
        out_dir = Path(out_dir)
        root = out_dir / "rootfs"
        # ubuntu: the rootfs tar stores root ownership; preserving it on extract
        # needs either root or fakeroot. Under root (the ubuntu build already
        # runs under sudo), extract directly. Unprivileged, re-exec under
        # fakeroot (the re-invocation carries RK_FORGE_STAGE_FAKEROOT=1).
        if (profile == "ubuntu" and os.geteuid() != 0
                and os.environ.get("RK_FORGE_STAGE_FAKEROOT") != "1"):
            self._rerun_under_fakeroot(out_dir, profile)
            return   # unreached — execvpe replaces the process

        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)

        if profile == "openwrt":
            self._stage_openwrt(root)
        elif profile == "ubuntu":
            self._stage_ubuntu(root)
        else:
            self._stage_buildroot(root)

        self.log.ok(f"rootfs staged → {root} ({_tree_size(root)})")

    # ── buildroot: extract rootfs.tar (post-build already baked .ko etc.) ──────
    def _stage_buildroot(self, root: Path) -> None:
        rootfs_tar = self.project.buildroot_dir / "output" / "images" / "rootfs.tar"
        if not rootfs_tar.is_file():
            self.log.die(
                f"missing buildroot rootfs.tar (build it first: forge build rootfs): {rootfs_tar}"
            )
        self.log.info(f"extracting buildroot rootfs.tar → {root}")
        self.proc.run(["tar", "xf", str(rootfs_tar), "-C", str(root)])
        self.log.info(f"next: forge pack (pack-ubifs → rootfs.ubi.img)")

    # ── openwrt: rsync TARGET_DIR (kmod packages already in lib/modules/) ─────
    def _stage_openwrt(self, root: Path) -> None:
        target_dir = self._find_openwrt_target_dir()
        if not (target_dir and (target_dir / "bin" / "busybox").is_file()):
            self.log.die(
                f"OpenWrt TARGET_DIR missing/incomplete: {target_dir or '<not found>'} "
                "(run: forge build openwrt)"
            )
        self.log.info(f"rsync OpenWrt TARGET_DIR → {root}")
        self.proc.run(["rsync", "-a", f"{target_dir}/", f"{root}/"])
        self.log.info("next: forge pack (pack-ubifs → rootfs.ubi.img)")

    # ── ubuntu: extract ubuntu-rootfs.tar (build already baked account/etc.) ──
    def _stage_ubuntu(self, root: Path) -> None:
        out_dir = root.parent
        tar = out_dir / "ubuntu-rootfs.tar"
        if not tar.is_file():
            self.log.die(
                f"missing ubuntu rootfs.tar (build it first: forge build ubuntu-rootfs): {tar}"
            )
        self.log.info(f"extracting ubuntu rootfs.tar → {root}")
        # --numeric-owner --same-owner: the tar stores numeric root ownership;
        # under fakeroot this preserves it for pack-emmc's mke2fs.
        self.proc.run(["tar", "--numeric-owner", "--same-owner", "-xf", str(tar),
                       "-C", str(root)])
        self.log.info("next: forge pack (pack-emmc → rootfs.ext4)")

    # ── fakeroot re-exec (ubuntu ownership preservation) ──────────────────────
    def _rerun_under_fakeroot(self, out_dir: Path, profile: str) -> None:
        if not shutil.which("fakeroot"):
            self.log.die("missing host tool: fakeroot (needed to preserve Ubuntu rootfs ownership)")
        state = out_dir / ".rootfs.fakeroot"
        state.unlink(missing_ok=True)
        self.log.info("staging Ubuntu rootfs under fakeroot (persistent ownership metadata)")
        env = dict(os.environ,
                   FAKEROOTDONTTRYCHOWN="1",
                   RK_FORGE_STAGE_FAKEROOT="1")
        cli = Path(__file__).resolve().parent / "cli.py"
        os.execvpe(
            "fakeroot",
            ["fakeroot", "-s", str(state), "--",
             sys.executable, str(cli),
             "--root", str(self.project.root),   # global — must precede the subcommand
             "stage", "--board", self.board.id, "--profile", profile,
             "--out", str(out_dir)],
            env)

    def _find_openwrt_target_dir(self) -> Path | None:
        bd = self.project.src_dir / self.board.id / "openwrt" / "build_dir"
        if not bd.is_dir():
            return None
        for p in bd.rglob("root-rockchip"):
            if p.is_dir():
                return p
        return None


def _tree_size(root: Path) -> str:
    """Human-readable tree size (du -sh analogue)."""
    try:
        return subprocess.run(["du", "-sh", str(root)], capture_output=True,
                              text=True).stdout.split()[0]
    except Exception:
        return "?"
