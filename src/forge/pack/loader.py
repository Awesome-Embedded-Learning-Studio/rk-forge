"""LoaderPacker — reproduce the RK loader (MiniLoaderAll.bin + idblock.img) from
rkbin blobs via Rockchip's boot_merger. Replaces scripts/pack-loader.sh.

The loader = DDR init + usbplug + SPL blobs wrapped in RK idblock format by
boot_merger. Blobs come through Rkbin (single source → SPL↔tee hash pair stays
consistent with pack-fit). SPL_SOURCE=mainline (rk3588) swaps the rkbin vendor
SPL for build-uboot's u-boot-spl.bin (same-gen as BL31 v1.54); otherwise the
rkbin vendor SPL is used (aes/rk3568). boot_merger embeds a build timestamp, so
the output is structurally-valid but NOT byte-reproducible (like mkfs.ubifs) —
verified by size + presence, not byte-golden.
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


class LoaderPacker:
    """Packs the loader (RK idblock + download tail) for the vendor-SPL boot flow."""

    def __init__(self, board: Board, project: Project, proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)
        self.uboot_dir = project.src_dir / board.id / "uboot"
        self.bringup = project.root / board.bringup_dir
        # boot_merger is version-tolerant → always the public rkbin submodule's.
        self.boot_merger = project.rkbin_dir / "tools" / "boot_merger"
        self.ini_tpl = self.bringup / board.loader_ini

    def pack(self, out_dir: Path | None = None) -> None:
        b = self.board
        out_dir = Path(out_dir) if out_dir else (self.project.root / b.bringup_dir / "out")
        self._require(self.boot_merger, "boot_merger (init third_party/rkbin submodule)")
        self._require(self.ini_tpl, f"loader ini template {b.loader_ini}")

        blobs = Rkbin(self.project, b, self.log).resolve()
        spl_name, spl_src = self._resolve_spl(blobs)

        with tempfile.TemporaryDirectory(prefix="loader-") as wd:
            wd = Path(wd)
            blob_wd = wd / b.rkbin_blob_subdir
            blob_wd.mkdir(parents=True)
            # stage blobs into <workdir>/<blob_subdir>/ so boot_merger's ini refs resolve
            shutil.copy(blobs.path(blobs.ddr), blob_wd / blobs.ddr)
            shutil.copy(blobs.path(blobs.usbplug), blob_wd / blobs.usbplug)
            shutil.copy(spl_src, blob_wd / spl_name)
            (wd / "RKBOOT.ini").write_text(self._substitute_ini(spl_name, blobs))

            self.log.info(f"boot_merger  (ddr={blobs.ddr} usbplug={blobs.usbplug} spl={spl_name})…")
            self.proc.run([str(self.boot_merger), "RKBOOT.ini"], cwd=str(wd), capture=True, quiet=True)

            loader = wd / "loader.bin"
            if not loader.is_file():
                self.log.die("boot_merger produced no loader.bin")
            out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(loader, out_dir / "MiniLoaderAll.bin")
            self.log.ok(f"MiniLoaderAll.bin → {out_dir/'MiniLoaderAll.bin'} ({loader.stat().st_size} B)")

            idb = wd / "idblock.img"
            if idb.is_file():
                shutil.copy(idb, out_dir / "idblock.img")
                self.log.ok(f"idblock.img → {out_dir/'idblock.img'} ({idb.stat().st_size} B, for SD/eMMC raw write)")
            else:
                self.log.warn("no standalone idblock.img (pack-sd will carve it from MiniLoaderAll.bin)")

        self.log.warn("NOT byte-identical to ATK-shipped loader (boot_merger timestamp + idblock layout).")

    # ── helpers ──────────────────────────────────────────────────────────────
    def _resolve_spl(self, blobs) -> tuple[str, Path]:
        """SPL_SOURCE=mainline → build-uboot's u-boot-spl.bin; else rkbin vendor SPL."""
        b = self.board
        if b.rkbin_spl_source == "mainline":
            src = self.uboot_dir / "spl" / "u-boot-spl.bin"
            self._require(src, "mainline SPL (run build-uboot; SPL_SOURCE=mainline)")
            return "u-boot-spl.bin", src
        return blobs.spl, blobs.path(blobs.spl)

    def _substitute_ini(self, spl_name: str, blobs) -> str:
        """Vendor mk-fitimage.sh convention: @TOKEN@ → blob basenames / output names."""
        b = self.board
        text = self.ini_tpl.read_text()
        for token, value in {
            "@DDR_BIN@": blobs.ddr,
            "@USBPLUG_BIN@": blobs.usbplug,
            "@SPL_BIN@": spl_name,
            "@BL31_BIN@": blobs.bl31 or "",   # no ATF stage (RK3506) → empty / token absent
            "@LOADER_OUT@": "loader.bin",
            "@IDB_OUT@": "idblock.img",
        }.items():
            text = text.replace(token, value)
        return text

    def _require(self, path: Path, label: str) -> None:
        if not path.exists():
            self.log.die(f"missing: {path} ({label})")
