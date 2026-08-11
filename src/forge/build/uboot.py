"""UBootBuilder — mainline U-Boot for a Rockchip board.

Replaces ``scripts/build-uboot.sh``. Produces the artifacts pack-fit consumes
(``u-boot-nodtb.bin`` + ``u-boot.dtb`` + ``tools/mkimage``) from the board
defconfig on the patched tree. Two reproducibility / robustness behaviours the
bash script worked hard for are preserved exactly:

* **SOURCE_DATE_EPOCH** pinned to the tree's HEAD commit date — U-Boot embeds a
  build timestamp otherwise, so two builds from the same commit diverge. Pinning
  it → byte-identical binaries (byte-golden verifiable).
* **binman tolerance + real-error gate**: ``make all`` also runs binman for the
  combined image, which fails with "Error 103 / missing external blobs" without
  the rkbin TPL/SPL blobs. We never use that combined image (pack-loader/pack-fit
  build from the separate pieces), so binman's failure is TOLERATED — but a real
  dts/gcc/ld error is FATAL. The full make log is captured and scanned for
  ``error:`` / ``undefined reference`` / dtc ``FATAL`` (excluding the binman
  noise); a match dies hard. (The old version's ``|| true`` + stale-artifact
  check once silently swallowed a dts parse error — see git history.)

ATF boards (RK3568/RK3588, ``rkbin.bl31`` set) let binman self-pack
``idbloader.img`` + ``u-boot.itb`` from the rkbin blobs (``BL31`` +
``ROCKCHIP_TPL`` env); aes/RK3506 has no ATF stage and skips this. TEE is
intentionally NOT passed (rkbin ships bl32 as a raw .bin; binman wants an ELF).

Variants:

* ``nand`` (default) — ``evb-<board>_defconfig``, built **in-tree** in the U-Boot
  dir (pack-fit reads the pieces there).
* ``sd`` — ``evb-<board>_sd_defconfig``, built in a **throwaway git worktree** at
  the same HEAD (has the sd defconfig from its patch) so the SD build never
  touches the NAND artifacts; the separate pieces are copied to ``out_dir``.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

from forge.build import check_toolchain, make_env
from forge.build.progress import run_with_progress
from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.proc import Proc
from forge.core.rkbin import Rkbin

# binman combined-image noise — tolerated (we never use the combined image).
# Matches build-uboot.sh's BINMAN_NOISE exactly.
_BINMAN_NOISE = (
    r"BINMAN |simple-bin|rockchip-tpl|ROCKCHIP_TPL=|binary and build with|"
    r"One possible source|Required binary blob|See the documentation|"
    r"external blob|external TPL|faked external|images are invalid|"
    r"Error 103|binman_stamp|/binman/|rockchip-linux/rkbin|ddr\.bin"
)
# Real build errors — never appear in the binman noise, so a match here is fatal.
_REAL_ERR = re.compile(r"FATAL ERROR|Lexical error|Syntax error|error:|undefined reference")
_NOISE = re.compile(_BINMAN_NOISE)


class UBootBuilder:
    """Builds mainline U-Boot (NAND in-tree, or SD in a throwaway worktree)."""

    def __init__(self, board: Board, project: Project,
                 proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)
        self.uboot_dir = project.src_dir / board.id / "uboot"

    def build(self, *, variant: str = "nand", clean: bool = False,
              out_dir: Path | None = None) -> None:
        b = self.board
        if variant not in ("nand", "sd"):
            raise ValueError(f"variant must be nand|sd, got {variant!r}")
        check_toolchain(b, self.log)
        if not self.uboot_dir.is_dir():
            self.log.die(f"U-Boot tree not found: {self.uboot_dir}")

        defconfig = b.uboot_defconfig_sd if variant == "sd" else b.uboot_defconfig
        mkimage = self.uboot_dir / "tools" / "mkimage"
        if variant == "sd" and not mkimage.exists():
            self.log.die(
                f"NAND tools/mkimage missing at {mkimage} — "
                "run `forge build uboot` (default nand) first"
            )
        self.log.info(f"variant={variant}  defconfig={defconfig}")

        # Reproducibility: pin the build timestamp to the HEAD commit date
        # (same HEAD for both variants — switching defconfig doesn't move HEAD).
        sde = self._head_commit_epoch()
        self.log.info(f"SOURCE_DATE_EPOCH={sde} ({self._head_commit_date()})")

        env = make_env(b, extra={"ARCH": b.uboot_arch_override, "SOURCE_DATE_EPOCH": sde})
        if b.has_atf:   # RK3568/RK3588: binman self-packs from rkbin blobs
            blobs = Rkbin(self.project, b, self.log).resolve()
            env["BL31"] = str(blobs.path(blobs.bl31))
            env["ROCKCHIP_TPL"] = str(blobs.path(blobs.ddr))
            # TEE intentionally omitted: rkbin bl32 is raw .bin, binman wants ELF.
            self.log.info(
                f"binman blobs: BL31={blobs.bl31}  ROCKCHIP_TPL={blobs.ddr}  "
                "(TEE omitted — OP-TEE optional; rkbin bl32 is raw, not ELF)"
            )

        arch_argv = ["make", f"ARCH={b.uboot_arch_override}", f"CROSS_COMPILE={b.toolchain_prefix}"]

        # SD: throwaway git worktree at HEAD → isolated in-tree build that never
        # touches the NAND artifacts. Cleaned up on exit (try/finally).
        build_dir = self.uboot_dir
        wt: str | None = None
        try:
            if variant == "sd":
                wt = tempfile.mkdtemp(prefix="uboot-sd-wt-")
                build_dir = Path(wt)
                self.log.info(f"git worktree (isolated SD in-tree build): {wt}")
                self.proc.run(["git", "-C", str(self.uboot_dir), "worktree",
                               "add", "--detach", wt, "HEAD"])

            if clean:
                if variant == "nand":
                    self.log.info("make mrproper (clean NAND rebuild)")
                    self.proc.run(arch_argv + ["mrproper"], cwd=str(build_dir), env_extra=env)
                else:
                    self.log.info("--clean is a no-op for --variant sd (the worktree is fresh each run)")

            self.log.info(f"make {defconfig} (in {build_dir})")
            self.proc.run(arch_argv + [defconfig], cwd=str(build_dir), env_extra=env)

            self._make_all(build_dir, env)
            self._verify_artifacts(build_dir, mkimage)

            if variant == "sd":
                out = Path(out_dir) if out_dir else (self.project.root / b.bringup_dir / "out")
                out.mkdir(parents=True, exist_ok=True)
                shutil.copy(build_dir / "u-boot-nodtb.bin", out / "u-boot-sd-nodtb.bin")
                shutil.copy(build_dir / "u-boot.dtb", out / "u-boot-sd.dtb")
                self.log.ok(f"U-Boot (SD) built → {out}/u-boot-sd-nodtb.bin + u-boot-sd.dtb")
                self._log_piece(out / "u-boot-sd-nodtb.bin")
                self._log_piece(out / "u-boot-sd.dtb")
                self.log.info("next: forge assemble --sd (pack-fit --variant sd picks these up)")
            else:
                self.log.ok(f"U-Boot built (SOURCE_DATE_EPOCH={sde}):")
                self._log_piece(build_dir / "u-boot-nodtb.bin")
                self._log_piece(build_dir / "u-boot.dtb")
                self._log_piece(mkimage)
                self.log.info("next: forge pack (pack-fit picks these up)")
        finally:
            if wt:
                self.proc.run(["git", "-C", str(self.uboot_dir), "worktree",
                               "remove", wt, "--force"], check=False, quiet=True)
                shutil.rmtree(wt, ignore_errors=True)

    # ── the make-all step: tolerate binman, gate on real errors ──────────────
    def _make_all(self, build_dir: Path, env: dict) -> None:
        """``make -jN`` (binman failure tolerated; real errors fatal).

        The full log is captured to a temp file and scanned for genuine
        dts/compile/link errors (excluding the binman noise). The progress pipe
        (interactive) gets ``--ignore-errors`` so the tolerated binman block
        neither triggers a false error nor clutters the live bar.
        """
        b = self.board
        arch_argv = ["make", f"ARCH={b.uboot_arch_override}", f"CROSS_COMPILE={b.toolchain_prefix}"]
        build_log = Path(tempfile.mktemp(prefix="uboot-build-"))
        self.log.info("make -j%d (binman combined-image failure tolerated; "
                      "real dts/compile/link errors are FATAL)" % (os.cpu_count() or 1))
        rc = run_with_progress(
            "uboot", arch_argv + ["-j", str(os.cpu_count() or 1)],
            project=self.project, proc=self.proc, log=self.log,
            cwd=str(build_dir), env_extra=env, check=False,
            ignore_errors=_BINMAN_NOISE, log_file=build_log,
        )
        _ = rc   # binman's non-zero is tolerated; the gate below is authoritative

        real_errs = [ln for ln in build_log.read_text(errors="replace").splitlines()
                     if _REAL_ERR.search(ln) and not _NOISE.search(ln)]
        if real_errs:
            self.log.error("\n".join(real_errs))
            self.log.die(
                "U-Boot build FAILED (real dts/compile/link error — "
                f"NOT the tolerated binman failure). Full log: {build_log}"
            )
        # build_log left on disk for diagnosis (matches bash's BUILD_LOG retention path).

    def _verify_artifacts(self, build_dir: Path, mkimage: Path) -> None:
        for f in (build_dir / "u-boot-nodtb.bin", build_dir / "u-boot.dtb", mkimage):
            if not f.exists():
                self.log.die(f"expected artifact missing after build: {f}")

    def _log_piece(self, path: Path) -> None:
        size = path.stat().st_size
        self.log.ok(f"  {path.name} → {size} B  sha256={_sha256_short(path)}")

    # ── git HEAD introspection (SOURCE_DATE_EPOCH) ───────────────────────────
    def _head_commit_epoch(self) -> str:
        cp = self.proc.run(["git", "-C", str(self.uboot_dir), "log", "-1",
                            "--format=%ct", "HEAD"], capture=True, quiet=True)
        return cp.stdout.strip()

    def _head_commit_date(self) -> str:
        cp = self.proc.run(["git", "-C", str(self.uboot_dir), "log", "-1",
                            "--format=%ci", "HEAD"], capture=True, quiet=True)
        return cp.stdout.strip()


def _sha256_short(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
