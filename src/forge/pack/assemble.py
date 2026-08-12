"""Updater — assemble a flashable RK update.img from partition images via the
pure-Python forge.tools.rkfw_pack encoder. Replaces scripts/assemble-update.sh.

rkfw-pack builds the RKAF container (package-file manifest + partition images)
and wraps it in the RKFW header + loader — replacing vendor afptool +
rkImageMaker. Output is deterministic (fixed build_time) → byte-golden
verifiable. Five variants: provision (default, ubiprog first-boot), nand (direct
mount), rescue (initramfs shell, no rootfs), sd, emmc. boot.img is padded to fill
the boot partition so the loader erases+writes it whole (no factory-garbage gap
on a fresh chip). A round-trip self-check (unpack own output, compare sizes)
makes the pipeline board-independently trustworthy.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from types import SimpleNamespace
from pathlib import Path

from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.proc import Proc
from forge.tools.rkfw_pack import cmd_pack, cmd_unpack

_VARIANTS = ("provision", "nand", "rescue", "sd", "emmc")


class Updater:
    """Assembles update.img for one variant from the pack-stage outputs."""

    def __init__(self, board: Board, project: Project, proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)
        self.bringup = project.root / board.bringup_dir

    def assemble(self, variant: str = "provision", out_dir: Path | None = None, verify: bool = True) -> Path:
        if variant not in _VARIANTS:
            raise ValueError(f"variant must be one of {_VARIANTS}, got {variant!r}")
        out_dir = Path(out_dir) if out_dir else (self.project.root / self.board.bringup_dir / "out")
        boot, uboot, rootfs, parameter, pkgfile, update_out, label = self._resolve(variant, out_dir)

        loader = out_dir / "MiniLoaderAll.bin"
        for f, lbl in ((loader, "MiniLoaderAll.bin"), (uboot, uboot.name), (boot, boot.name),
                       (parameter, parameter.name), (pkgfile, pkgfile.name)):
            self._require(f, lbl)
        if rootfs is not None:
            self._require(rootfs, "rootfs")

        param_text = parameter.read_text()
        if variant in ("sd", "emmc"):
            self._check_rootfs_fits(rootfs, param_text)
        padded_boot = self._padded_boot(boot, param_text)

        try:
            with tempfile.TemporaryDirectory(prefix="rockdev-") as rockdev:
                img = Path(rockdev) / "Image"
                img.mkdir(parents=True)
                shutil.copy(pkgfile, Path(rockdev) / "package-file")
                shutil.copy(loader, img / "MiniLoaderAll.bin")
                shutil.copy(parameter, img / "parameter.txt")
                shutil.copy(uboot, img / uboot.name)        # aes=uboot.img, rk3568=u-boot.itb
                shutil.copy(padded_boot, img / "boot.img")  # boot-nand.img staged AS boot.img (manifest match)
                if rootfs is not None:
                    shutil.copy(rootfs, img / "rootfs.img")

                self.log.info(f"rkfw-pack (RKAF+RKFW, variant={label})…")
                cmd_pack(SimpleNamespace(package_file=str(pkgfile), image_dir=str(img),
                                         loader=str(loader), parameter=str(parameter),
                                         out=str(update_out)))
                if not update_out.is_file():
                    self.log.die(f"rkfw-pack produced no {update_out}")
                self.log.ok(f"{update_out.name} → {update_out} ({update_out.stat().st_size} B, variant={label})")

                if verify:
                    self._round_trip(update_out, uboot, padded_boot, rootfs)
        finally:
            padded_boot.unlink(missing_ok=True)

        return update_out

    # ── variant → paths ──────────────────────────────────────────────────────
    def _resolve(self, variant, out_dir):
        b, br = self.board, self.bringup
        uboot_dir = out_dir / "uboot.img"
        if variant == "emmc":
            return (out_dir / "boot.img", out_dir / "u-boot.itb", out_dir / "rootfs.ext4",
                    br / b.parameter["emmc"], br / b.package["emmc"], out_dir / "update.img", "EMMC")
        if variant == "sd":
            return (out_dir / "boot-sd.img", out_dir / "uboot-sd.img", out_dir / "rootfs.ext4",
                    br / b.parameter["sd"], br / b.package["sd"], out_dir / "update-sd.img", "SD-CARD")
        if variant == "nand":
            return (out_dir / "boot-nand.img", uboot_dir, out_dir / "rootfs.ubi.img",
                    br / b.parameter["nand"], br / b.package["nand"], out_dir / "update-nand.img", "NAND-DIRECT")
        if variant == "rescue":
            return (out_dir / "boot.img", uboot_dir, None,
                    br / b.parameter["nand"], br / b.package["rescue"], out_dir / "update-rescue.img", "RESCUE-SHELL")
        # provision (default)
        return (out_dir / "boot.img", uboot_dir, out_dir / "rootfs.ubi.img",
                br / b.parameter["nand"], br / b.package["nand"], out_dir / "update.img", "PROVISION-UBIPROG")

    # ── parameter parsing + boot padding + rootfs-fit ────────────────────────
    @staticmethod
    def _part_bytes(param_text: str, label: str) -> int:
        """Parse `0x<sectors>@0x<off>(<label>)` → partition size in bytes."""
        m = re.search(rf"0x([0-9a-fA-F]+)@0x[0-9a-fA-F]+\({label}\)", param_text)
        if not m:
            raise ValueError(f"couldn't parse {label} partition size from parameter")
        return int(m.group(1), 16) * 512

    def _check_rootfs_fits(self, rootfs: Path, param_text: str) -> None:
        part = self._part_bytes(param_text, "rootfs")
        size = rootfs.stat().st_size
        if size > part:
            self.log.die(f"rootfs.ext4 ({size} B) > rootfs partition ({part} B). "
                         f"Shrink --rootfs-mib or grow the partition in the parameter file.")
        self.log.info(f"rootfs.ext4 ({size} B) fits rootfs partition ({part} B)")

    def _padded_boot(self, boot: Path, param_text: str) -> Path:
        """Pad boot.img with 0x00 to fill the boot partition (loader erases it whole)."""
        part = self._part_bytes(param_text, "boot")
        size = boot.stat().st_size
        if size > part:
            self.log.die(f"boot.img ({size} B) > boot partition ({part} B); kernel won't fit")
        padded = Path(tempfile.mkstemp(prefix="padded-boot-")[1])
        shutil.copy(boot, padded)
        self.proc.run(["truncate", "-s", str(part), str(padded)], capture=True, quiet=True)
        self.log.info(f"boot.img padded {size} -> {part} B (fills boot partition)")
        return padded

    # ── round-trip self-check ────────────────────────────────────────────────
    def _round_trip(self, update_out: Path, uboot: Path, boot: Path, rootfs: Path | None) -> None:
        self.log.info("round-trip self-check (rkfw-pack unpack own output)…")
        with tempfile.TemporaryDirectory(prefix="rkfwoft-") as vfy:
            cmd_unpack(SimpleNamespace(update_img=str(update_out), out_dir=vfy))
            pairs = [(uboot.name, uboot), ("boot.img", boot)]
            if rootfs is not None:
                pairs.append(("rootfs.img", rootfs))
            for name, src in pairs:
                got = Path(vfy) / name
                if not got.is_file():
                    self.log.die(f"self-check FAIL: {name} missing after unpack")
                if got.stat().st_size != src.stat().st_size:
                    self.log.die(f"self-check FAIL: {name} size {got.stat().st_size} != source {src.stat().st_size}")
            self.log.ok(f"self-check OK: {update_out.name} round-trips "
                        f"(uboot/boot{'+rootfs' if rootfs else ''} sizes match)")

    def _require(self, path: Path, label: str) -> None:
        if not path.exists():
            self.log.die(f"missing: {path} ({label}; run `forge pack` first)")
