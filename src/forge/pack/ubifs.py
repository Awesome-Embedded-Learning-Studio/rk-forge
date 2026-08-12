"""UbiFsPacker — NAND rootfs tree → flashable UBI image (mkfs.ubifs + ubinize).

Replaces scripts/pack-ubifs.sh. Reads NAND geometry straight off the Board
(no bash env); the only env its subprocesses see is Proc's curated allow-list
(plus PATH) — no project var leakage. NAND-only: a non-NAND board is rejected
here rather than producing a nonsense image.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from textwrap import dedent

from forge.config.board import Board
from forge.core.log import Log
from forge.core.proc import Proc


class UbiFsPacker:
    """Two-step NAND rootfs packaging: mkfs.ubifs (tree → UBIFS volume), then
    ubinize (volume → raw UBI image for one-shot partition programming)."""

    def __init__(self, board: Board, proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)

    def pack(self, rootfs_tree: Path, ubifs_out: Path, ubi_out: Path) -> None:
        b = self.board
        if not b.is_nand:
            raise ValueError(
                f"UbiFsPacker is NAND-only; board {b.id!r} is storage.kind={b.storage_kind!r}"
            )
        self._require_tool("mkfs.ubifs", "mtd-utils")
        self._require_tool("ubinize", "mtd-utils")
        if not (rootfs_tree.is_dir() and (rootfs_tree / "bin" / "busybox").is_file()):
            self.log.die(f"rootfs tree missing or incomplete: {rootfs_tree} (run stage-rootfs first)")

        self.log.info(
            f"mkfs.ubifs  (min_io={b.nand_min_io} leb={b.nand_leb} max_leb={b.nand_max_leb})…"
        )
        self.proc.run([
            "mkfs.ubifs", "-x", "none",
            "-m", str(b.nand_min_io),
            "-e", str(b.nand_leb),
            "-c", str(b.nand_max_leb),
            "-r", str(rootfs_tree),
            str(ubifs_out),
        ])

        cfg = self._write_ubinize_cfg(ubifs_out)
        try:
            self.log.info(f"ubinize  (peb={b.nand_peb} → {ubi_out.name})…")
            self.proc.run([
                "ubinize",
                "-m", str(b.nand_min_io),
                "-p", str(b.nand_peb),
                str(cfg),
                "-o", str(ubi_out),
            ])
        finally:
            cfg.unlink(missing_ok=True)

        if not ubi_out.is_file():
            self.log.die(f"ubinize produced no image: {ubi_out}")
        self.log.ok(f"rootfs.ubi.img → {ubi_out} ({ubi_out.stat().st_size} bytes)")

    # ── helpers ──────────────────────────────────────────────────────────────
    def _require_tool(self, tool: str, pkg: str) -> None:
        from shutil import which
        if not which(tool):
            self.log.die(f"{tool} missing (apt install {pkg})")

    @staticmethod
    def _write_ubinize_cfg(image: Path) -> Path:
        """Write the single-volume ubinize descriptor to a temp .cfg."""
        with tempfile.NamedTemporaryFile(
            "w", prefix="ubinize-", suffix=".cfg", delete=False
        ) as f:
            f.write(dedent(f"""\
                [rootfs_vol]
                mode=ubi
                vol_id=0
                vol_type=dynamic
                vol_name=rootfs
                vol_alignment=1
                vol_flags=autoresize
                image={image}
            """))
            return Path(f.name)
