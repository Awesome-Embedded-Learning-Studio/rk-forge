"""EmPacker — ext4 rootfs image (rootfs.ext4) for eMMC boards. Replaces
scripts/pack-emmc.sh.

eMMC rootfs = ext4 (not UBIFS, not a provisioning initramfs); the kernel mounts
it directly (root=/dev/mmcblk1pN). Takes the staged rootfs tree and packs a
fixed-size ext4 via ``mke2fs -d`` (root-free, no losetup/mount/sudo), plus a
u-boot boot.scr (the eMMC boot partition is raw FIT, so bootflow's SCRIPT
bootmeth finds boot.scr on this ext4 partition and raw-`mmc read`s the boot
partition). Fixed UUID + hash_seed → structural reproducibility (superblock
write-time still varies → NOT byte-identical, like pack-sd).

Ubuntu rootfs ownership: stage-rootfs records archive ownership in a fakeroot
database (``.rootfs.fakeroot``); when that exists and we're not already under
fakeroot, re-exec under fakeroot so mke2fs -d sees root-owned system files. This
mirrors the bash auto-re-exec exactly (no behaviour change); the §4.7 "explicit
fakeroot, no auto re-exec" refinement lands at F3.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.proc import Proc

_EXT4_UUID = "11111111-2222-3333-4444-555555555555"
_EXT4_HASH_SEED = "66666666-7777-8888-9999-aaaaaaaaaaaa"


class EmPacker:
    """Packs the staged rootfs tree into a fixed-size ext4 (+ boot.scr)."""

    def __init__(self, board: Board, project: Project, proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)
        self.bringup = project.root / board.bringup_dir
        self.uboot_dir = project.src_dir / board.id / "uboot"
        self.boot_cmd = self.bringup / "fit" / "boot-emmc.cmd"

    def pack(self, out_dir: Path | None = None, rootfs_mib: int | None = None) -> None:
        b = self.board
        out_dir = Path(out_dir) if out_dir else (self.project.root / b.bringup_dir / "out")
        rootfs_mib = rootfs_mib or b.rootfs_mib or 1024

        # Ubuntu fakeroot: re-exec under the saved ownership db if needed (preserves bash behaviour).
        state = out_dir / ".rootfs.fakeroot"
        if state.is_file() and os.environ.get("RK_FORGE_ROOTFS_FAKEROOT") != "1":
            self._reexec_fakeroot(state)
            return  # os.execv replaces the process; not reached on success

        root = out_dir / "rootfs"
        if not root.is_dir():
            self.log.die(f"missing staged rootfs tree: {root} (run forge pack first — stage-rootfs)")
        self._require_tool("mke2fs", "e2fsprogs")

        self._gen_boot_scr(root)
        rootfs_ext4 = out_dir / "rootfs.ext4"
        self.log.info(f"building ext4 rootfs ({rootfs_mib} MiB) from {root} …")
        self.proc.run([
            "mke2fs", "-q", "-F", "-t", "ext4", "-b", "4096", "-L", "rootfs",
            "-U", _EXT4_UUID, "-E", f"hash_seed={_EXT4_HASH_SEED}",
            "-d", str(root), str(rootfs_ext4), f"{rootfs_mib}M",
        ], capture=True, quiet=True)
        self.log.ok(f"rootfs.ext4 → {rootfs_ext4} ({rootfs_ext4.stat().st_size} B)")

    # ── boot.scr (eMMC boot partition is raw FIT → bootflow SCRIPT bootmeth) ─
    def _gen_boot_scr(self, root: Path) -> None:
        if not self.boot_cmd.is_file():
            return
        mkimage = self._find_mkimage()
        (root / "boot").mkdir(parents=True, exist_ok=True)
        self.proc.run([
            mkimage, "-A", self.board.arch, "-O", "linux", "-T", "script", "-C", "none",
            "-n", f"{self.board.id} eMMC boot", "-d", str(self.boot_cmd), str(root / "boot" / "boot.scr"),
        ], capture=True, quiet=True)
        shutil.copy(root / "boot" / "boot.scr", root / "boot.scr")  # SCRIPT_FNAME2 (partition root)
        self.log.info("boot.scr → rootfs /boot/boot.scr + /boot.scr (bootflow entry)")

    def _find_mkimage(self) -> str:
        from shutil import which
        for cand in (which("mkimage"),
                     str(self.project.root / "third_party/buildroot/output/host/bin/mkimage"),
                     str(self.uboot_dir / "tools" / "mkimage")):
            if cand and Path(cand).is_file():
                return cand
        self.log.die("mkimage not found (build build-uboot or install u-boot-tools)")

    # ── fakeroot re-exec (Ubuntu ownership preservation; transition — F3 makes it explicit) ─
    def _reexec_fakeroot(self, state: Path) -> None:
        from shutil import which
        if not which("fakeroot"):
            self.log.die("missing host tool: fakeroot (needed to preserve Ubuntu rootfs ownership)")
        self.log.info("packing Ubuntu ext4 under saved fakeroot ownership metadata")
        os.environ["RK_FORGE_ROOTFS_FAKEROOT"] = "1"   # marker: child skips re-exec
        os.environ["FAKEROOTDONTTRYCHOWN"] = "1"
        cli = self.project.root / "src" / "forge" / "cli.py"
        os.execvp("fakeroot", [
            "fakeroot", "-i", str(state), "-s", str(state), "--",
            sys.executable, str(cli), "pack", "--board", self.board.id, "emmc",
        ])

    def _require_tool(self, tool: str, pkg: str = "") -> None:
        from shutil import which
        if not which(tool):
            self.log.die(f"missing host tool: {tool}" + (f" (apt: {pkg})" if pkg else ""))
