"""Flasher — write the forge SD-card image (sd.img) to a physical SD card.

Replaces ``scripts/flash-sd.sh``. Pairs with ``forge pack --media sd`` (which
builds sd.img). SD is the SECOND boot media (parallel to SPI-NAND) — a
development/recovery path.

SAFETY: this overwrites the ENTIRE target device, so the guard chain
(architecture §3 — the whole reason ``forge flash`` is a first-class subcommand)
is preserved exactly: requires an explicit ``--device``, refuses partitions,
refuses any mounted device, refuses the system disk, checks the image isn't
larger than the device, and asks for typed confirmation before writing. The
blast radius of a wrong device is total data loss on that disk — these checks
err on the side of refusing.

``dd`` runs under explicit ``sudo`` (§3 — no auto re-exec; sudo is per-invocation).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.proc import Proc


class Flasher:
    """Writes sd.img to a physical SD card (guard chain preserved)."""

    def __init__(self, board: Board, project: Project,
                 proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)

    def flash(self, *, device: str, img: Path | None = None,
              assume_yes: bool = False, out_dir: Path | None = None) -> None:
        for tool in ("lsblk", "dd"):
            if not shutil.which(tool):
                self.log.die(f"{tool} not found")

        img = Path(img) if img else (Path(out_dir) / "sd.img" if out_dir
                                     else self.project.root / self.board.bringup_dir / "out" / "sd.img")

        if not device:
            self.log.warn("--device is required. Candidate devices:")
            self._list_devices()
            self.log.die("re-run with --device /dev/sdX")
        if not img.is_file():
            self.log.die(f"image not found: {img} (run `forge pack --media sd` first)")

        self._guard_block_device(device)
        self._guard_not_partition(device)
        self._guard_not_mounted(device)
        self._guard_not_system_disk(device)
        self._check_size(device, img)
        self._confirm(device, img, assume_yes)

        self.log.info(f"dd → {device} (bs=4M conv=fsync) …")
        self.proc.run(["sudo", "dd", f"if={img}", f"of={device}",
                       "bs=4M", "conv=fsync", "status=progress"])
        self.proc.run(["sync"])
        self.log.ok(f"done — sd.img written to {device}")
        self.log.info("eject/reinsert the card, then boot (see notes/30 for the manual boot sequence)")

    # ── guards (each refuses with a clear reason; §3 dd safety chain) ──────────
    def _list_devices(self) -> None:
        cp = self.proc.run(["lsblk", "-dno", "NAME,SIZE,TYPE,TRAN,MODEL,RM"],
                           check=False, capture=True, quiet=True)
        for line in (cp.stdout or "").splitlines():
            sys.stdout.write(f"    {line}\n")
        sys.stdout.write("  pass one as --device /dev/<NAME>\n")
        sys.stdout.flush()

    def _guard_block_device(self, device: str) -> None:
        if not Path(device).is_block_device():
            self.log.die(f"{device} is not a block device")

    def _guard_not_partition(self, device: str) -> None:
        # refuse a partition node (sdX1, mmcblk0p1): writing a whole-disk image
        # to a partition node corrupts the parent's partition table.
        if device[-1].isdigit() or (device.endswith("p") and len(device) > 1):
            self.log.die(
                f"{device} looks like a PARTITION (trailing digit). Give the "
                "whole-disk node (e.g. /dev/sdc, /dev/mmcblk0)."
            )

    def _guard_not_mounted(self, device: str) -> None:
        cp = self.proc.run(["lsblk", "-no", "MOUNTPOINT", device],
                           check=False, capture=True, quiet=True)
        if any(line.strip() for line in (cp.stdout or "").splitlines()):
            self.log.die(
                f"{device} (or a partition) is mounted — unmount it first:\n"
                f"  sudo umount {device}*"
            )

    def _guard_not_system_disk(self, device: str) -> None:
        # refuse the device whose partition holds / or /boot(/efi). Best-effort
        # heuristic (in WSL2 the root fs is virtio, but a stray /dev/sda that's
        # the host C: pass-through must never be overwritten).
        try:
            mounts = Path("/proc/mounts").read_text()
        except OSError:
            return
        for line in mounts.splitlines():
            fields = line.split()
            if len(fields) < 2 or fields[1] not in ("/", "/boot", "/boot/efi"):
                continue
            sysdev = fields[0]
            cp = self.proc.run(["lsblk", "-no", "PKNAME", sysdev],
                               check=False, capture=True, quiet=True)
            base = (cp.stdout or "").strip().splitlines()[0] if (cp.stdout or "").strip() else ""
            if not base:
                import re
                base = re.sub(r"[0-9]+$", "", re.sub(r"p$", "", Path(sysdev).name))
            if f"/dev/{base}" == device or sysdev.startswith(device):
                self.log.die(
                    f"{device} looks like the SYSTEM disk (holds {sysdev}). Refusing to overwrite."
                )

    def _check_size(self, device: str, img: Path) -> None:
        dev_size = self._lsblk_size(device)
        img_size = img.stat().st_size
        self.log.info(f"image: {img} ({img_size // 1024 // 1024} MiB)")
        model = self._lsblk_field(device, "MODEL")
        tran = self._lsblk_field(device, "TRAN")
        self.log.info(f"target: {device} — {dev_size // 1024 // 1024} MiB {model}{f' [{tran}]' if tran else ''}")
        if dev_size > 0 and img_size > dev_size:
            self.log.die(
                f"image ({img_size} B) is LARGER than {device} ({dev_size} B) — "
                "wrong device or image"
            )

    def _confirm(self, device: str, img: Path, assume_yes: bool) -> None:
        if assume_yes:
            return
        sys.stdout.write(f"  This OVERWRITES {device} entirely. All data on it will be lost.\n")
        sys.stdout.write(f"  Type the device name ({device}) to confirm: ")
        sys.stdout.flush()
        reply = sys.stdin.readline().strip()
        if reply != device:
            self.log.die("confirmation did not match — aborted")

    # ── lsblk helpers ─────────────────────────────────────────────────────────
    def _lsblk_size(self, device: str) -> int:
        cp = self.proc.run(["lsblk", "-bndo", "SIZE", device],
                           check=False, capture=True, quiet=True)
        try:
            return int((cp.stdout or "").strip())
        except ValueError:
            return 0

    def _lsblk_field(self, device: str, field: str) -> str:
        cp = self.proc.run(["lsblk", "-ndo", field, device],
                           check=False, capture=True, quiet=True)
        return (cp.stdout or "").strip()
