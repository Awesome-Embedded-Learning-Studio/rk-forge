"""FitPacker — all FIT images via the pure-Python forge.tools.fit_pack encoder.

Replaces scripts/pack-fit.sh. Paths come off Board/Project; the tee blob (for the
aes vendor-SPL uboot FIT) routes through Rkbin so the SPL↔tee hash pair stays
single-sourced. fit-pack resolves each image's ``data = /incbin/(...)`` relative
to the ITS file's own dir, so each FIT is staged in a temp workdir (ITS + its
pieces copied together) before packing — exactly as pack-fit.sh did.

Output is deterministic (fit_pack ``timestamp=0``), so boot.img / uboot.img are
byte-reproducible → byte-golden verifiable (unlike the mkfs.ubifs path).
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.proc import Proc
from forge.core.rkbin import Rkbin
from forge.tools.fit_pack import pack as fit_pack_encode

# Mode B external offset (mainline U-Boot bootm: -E -p 0x800 → absolute data-position).
_EXT_OFF_MODE_B = 0x800


class FitPacker:
    """Packs the uboot FIT + the board's boot FIT(s); binman boards just stage."""

    def __init__(self, board: Board, project: Project, proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)
        self.uboot_dir = project.src_dir / board.id / "uboot"
        self.linux_dir = project.src_dir / board.id / "linux"
        self.bringup = project.root / board.bringup_dir
        self.its_dir = self.bringup / "fit"
        self.mkimage = self.uboot_dir / "tools" / "mkimage"

    def pack(self, variant: str = "nand", out_dir: Path | None = None,
             kernel_artifact_dir: Path | None = None) -> None:
        b = self.board
        if variant not in ("nand", "sd"):
            raise ValueError(f"variant must be nand|sd, got {variant!r}")
        out_dir = Path(out_dir) if out_dir else (self.project.root / b.bringup_dir / "out")
        kad = Path(kernel_artifact_dir) if kernel_artifact_dir else self.linux_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        self._require(self.mkimage, "mainline mkimage (build U-Boot first)")

        self._pack_uboot(out_dir)

        if variant == "sd":
            self._pack_one(f"{b.soc}-mainline.its", {
                "uboot-nodtb.bin": out_dir / "u-boot-sd-nodtb.bin",
                "u-boot.dtb": out_dir / "u-boot-sd.dtb",
            }, out_dir / "uboot-sd.img", external_offset=0)
            self.log.info("variant=sd: only uboot-sd.img packed (boot*.img unchanged)")
            return

        self._pack_boot(out_dir, kad)
        self.log.info("all FITs forge-packed (fit-pack encoder; definitive check is board-boot).")

    # ── uboot FIT ────────────────────────────────────────────────────────────
    def _pack_uboot(self, out_dir: Path) -> None:
        b = self.board
        if b.uboot_fit_source == "nodtb":
            blobs = Rkbin(self.project, b, self.log).resolve()
            self._pack_one(f"{b.soc}-mainline.its", {
                "uboot-nodtb.bin": self.uboot_dir / "u-boot-nodtb.bin",
                "u-boot.dtb": self.uboot_dir / "u-boot.dtb",
                "tee.bin": blobs.path(blobs.tee),
            }, out_dir / "uboot.img", external_offset=0)
        else:  # binman (rk3568/rk3588): build-uboot already emitted the final loader+uboot
            for f in ("u-boot.itb", "idbloader.img"):
                src = self.uboot_dir / f
                self._require(src, f"binman {f} (run build-uboot first; ATF boards MUST binman-succeed)")
                shutil.copy(src, out_dir / f)
            self.log.ok(f"u-boot.itb + idbloader.img (binman) → {out_dir}")

    # ── boot FIT(s) ──────────────────────────────────────────────────────────
    def _pack_boot(self, out_dir: Path, kad: Path) -> None:
        b = self.board
        zimage = kad / "arch" / b.arch / "boot" / b.kern_img
        dtb = kad / "arch" / b.arch / "boot" / "dts" / "rockchip" / f"{b.dtb_name}.dtb"
        base = {b.kern_img: zimage, f"{b.dtb_name}.dtb": dtb}

        if b.is_emmc:  # rk3568/rk3588: single boot.img, no ramdisk (eMMC ext4 root)
            self._pack_one(f"{b.soc}-kernel.its", base, out_dir / "boot.img", _EXT_OFF_MODE_B)
        else:  # aes (NAND): boot.img (+provisioning initramfs) + boot-nand.img + boot-sd.img
            pieces = dict(base)
            pieces["initramfs.cpio.gz"] = self.its_dir / "initramfs.cpio.gz"
            self._pack_one(f"{b.soc}-kernel.its", pieces, out_dir / "boot.img", _EXT_OFF_MODE_B)
            self._pack_one(f"{b.soc}-kernel-nand.its", base, out_dir / "boot-nand.img", _EXT_OFF_MODE_B)
            self._pack_one(f"{b.soc}-kernel-sd.its", base, out_dir / "boot-sd.img", _EXT_OFF_MODE_B)

    # ── one FIT: stage ITS + pieces in a temp workdir, pack, parse-check ─────
    def _pack_one(self, its_name: str, pieces: dict, out_path: Path, external_offset: int) -> None:
        its_src = self.its_dir / its_name
        self._require(its_src, f"ITS template {its_name}")
        for name, src in pieces.items():
            self._require(src, f"FIT input {name}")

        mode = "Mode B -E -p 0x800" if external_offset else "Mode A -E"
        self.log.info(f"packing {out_path.name} (fit-pack {mode})…")
        with tempfile.TemporaryDirectory(prefix="fit-") as wd:
            wd = Path(wd)
            shutil.copy(its_src, wd / its_name)
            for name, src in pieces.items():
                shutil.copy(src, wd / name)
            packed = wd / out_path.name
            fit_pack_encode(str(wd / its_name), str(packed),
                            timestamp=0, external_offset=external_offset, verbose=True)
            shutil.copy(packed, out_path)

        self.proc.run([str(self.mkimage), "-l", str(out_path)], capture=True, quiet=True)  # parse check
        self.log.ok(f"{out_path.name} → {out_path} ({out_path.stat().st_size} B)")

    def _require(self, path: Path, label: str) -> None:
        if not path.exists():
            self.log.die(f"missing: {path} ({label})")
