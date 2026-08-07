"""SdPacker — bootable SD-card image (sd.img) for the aes board. Replaces
scripts/pack-sd.sh.

Root-free + reproducible-layout: each region is a standalone artifact (ext4 via
``mke2fs -d``, GPT via sgdisk, blobs via dd) written into a regular-file image —
no losetup/mount/sudo. ``assert_regular_file`` guards every raw write so a
mistaken block-device target is refused before any dd/sgdisk. The ext4 superblock
write-time is host-dependent → sd.img is NOT byte-identical across runs (like
buildroot), but structure + content are deterministic (self-check verifies every
blob landed at its offset).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from forge.config.board import Board
from forge.config.project import Project
from forge.core.guards import assert_regular_file
from forge.core.log import Log
from forge.core.proc import Proc

# Layout (sectors of 512 B) — see scripts/pack-sd.sh header for the boot-protocol rationale.
_SECTOR = 512
_IDBLOCK_SECTOR = 64        # BootROM reads idblock at 0x40
_UBOOT_SECTOR = 8192        # 0x2000 — CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR
_BOOTIMG_SECTOR = 16384     # 0x4000 — raw kernel FIT, mmc read by U-Boot
_ROOTFS_SECTOR = 65536      # 0x10000 — GPT p1, 32 MiB alignment
_HEADER_MIB = 32
_TAIL_MIB = 8
# Fixed UUID + hash_seed → structural reproducibility (superblock write-time still varies).
_EXT4_UUID = "11111111-2222-3333-4444-555555555555"
_EXT4_HASH_SEED = "66666666-7777-8888-9999-aaaaaaaaaaaa"


class SdPacker:
    """Packs the aes SD image: GPT + raw idblock/uboot/boot + ext4 rootfs p1."""

    def __init__(self, board: Board, project: Project, proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)

    def pack(self, out_dir: Path | None = None, rootfs_mib: int = 256, size_mib: int = 0) -> None:
        out_dir = Path(out_dir) if out_dir else (self.project.root / self.board.bringup_dir / "out")
        idblock = out_dir / "idblock.img"
        uboot = out_dir / "uboot.img"
        boot = out_dir / "boot.img"
        root = out_dir / "rootfs"
        for f, label in ((idblock, "idblock"), (uboot, "uboot.img"), (boot, "boot.img")):
            self._require(f, f"{label} (run forge pack first — pack-loader + pack-fit)")
        if not root.is_dir():
            self.log.die(f"missing staged rootfs tree: {root} (run forge pack first — stage-rootfs)")

        self._require_tool("mke2fs", "e2fsprogs")
        self._require_tool("sgdisk", "gdisk")
        self._require_tool("dd")
        self._require_tool("truncate")

        out_dir.mkdir(parents=True, exist_ok=True)
        rootfs_ext4 = out_dir / "rootfs.ext4"
        sd_img = out_dir / "sd.img"

        # A: ext4 rootfs from the staged tree
        self.log.info(f"building ext4 rootfs ({rootfs_mib} MiB) from {root} …")
        self.proc.run([
            "mke2fs", "-q", "-F", "-t", "ext4", "-b", "4096", "-L", "rootfs",
            "-U", _EXT4_UUID, "-E", f"hash_seed={_EXT4_HASH_SEED}",
            "-d", str(root), str(rootfs_ext4), f"{rootfs_mib}M",
        ], capture=True, quiet=True)
        self.log.ok(f"rootfs.ext4 → {rootfs_ext4} ({rootfs_ext4.stat().st_size} B)")

        # B: lay out sd.img (GPT + raw blobs + rootfs p1). Guard BEFORE any raw write.
        assert_regular_file(sd_img, "sd.img")
        total_mib = size_mib if size_mib else (_HEADER_MIB + rootfs_mib + _TAIL_MIB)
        self.log.info(f"laying out sd.img ({total_mib} MiB): GPT + raw blobs + rootfs p1 …")
        sd_img.unlink(missing_ok=True)
        self.proc.run(["truncate", "-s", f"{total_mib}M", str(sd_img)], capture=True, quiet=True)
        self.proc.run(["sgdisk", "--zap-all", str(sd_img)], capture=True, quiet=True)
        self.proc.run([
            "sgdisk", f"--new=1:{_ROOTFS_SECTOR}:+{rootfs_mib}M",
            "--change-name=1:rootfs", "--typecode=1:8300", str(sd_img),
        ], capture=True, quiet=True)

        # raw-write boot blobs at fixed sector offsets
        self._dd(idblock, sd_img, _IDBLOCK_SECTOR * _SECTOR, sector_bs=True)
        self._dd(uboot, sd_img, _UBOOT_SECTOR * _SECTOR)
        self._dd(boot, sd_img, _BOOTIMG_SECTOR * _SECTOR)
        self._dd(rootfs_ext4, sd_img, _ROOTFS_SECTOR * _SECTOR)

        # C: self-check — every blob landed at its offset (read back, sha256 compare)
        self.log.info("self-check: blob offsets")
        for f, off, label in (
            (idblock, _IDBLOCK_SECTOR * _SECTOR, "idblock"),
            (uboot, _UBOOT_SECTOR * _SECTOR, "uboot.img"),
            (boot, _BOOTIMG_SECTOR * _SECTOR, "boot.img"),
        ):
            self._verify_offset(f, sd_img, off, label)

        self.log.ok(f"sd.img → {sd_img} ({sd_img.stat().st_size} B = {sd_img.stat().st_size // 1024 // 1024} MiB)")

    # ── helpers ──────────────────────────────────────────────────────────────
    def _dd(self, src: Path, dst: Path, byte_offset: int, sector_bs: bool = False) -> None:
        if sector_bs:
            self.proc.run(["dd", f"if={src}", f"of={dst}", f"bs={_SECTOR}",
                           f"seek={byte_offset // _SECTOR}", "conv=notrunc", "status=none"],
                          capture=True, quiet=True)
        else:
            self.proc.run(["dd", f"if={src}", f"of={dst}", "bs=1M",
                           f"seek={byte_offset // 1024 // 1024}", "conv=notrunc", "status=none"],
                          capture=True, quiet=True)

    def _verify_offset(self, src: Path, img: Path, byte_offset: int, label: str) -> None:
        size = src.stat().st_size
        with open(img, "rb") as f:
            f.seek(byte_offset)
            got = hashlib.sha256(f.read(size)).hexdigest()[:16]
        want = hashlib.sha256(src.read_bytes()).hexdigest()[:16]
        if got != want:
            self.log.die(f"{label} mismatch at byte {byte_offset} (got {got} want {want})")
        self.log.ok(f"{label}: {size} B @ byte {byte_offset} verified")

    def _require(self, path: Path, label: str) -> None:
        if not path.exists():
            self.log.die(f"missing: {path} ({label})")

    def _require_tool(self, tool: str, pkg: str = "") -> None:
        from shutil import which
        if not which(tool):
            self.log.die(f"missing host tool: {tool}" + (f" (apt: {pkg})" if pkg else ""))
