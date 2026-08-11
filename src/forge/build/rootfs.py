"""RootfsBuilder — buildroot UBIFS rootfs (``output/images/rootfs.tar``).

Replaces ``scripts/build-rootfs.sh``. Wraps the canonical buildroot build with
the WSL PATH fix (:func:`forge.build.host.clean_path`) so it runs unattended.
forge's board customization is the ``BR2_EXTERNAL`` tree at
``<bringup>/buildroot-external`` (``rk3506_aes_defconfig`` + overlay + post-build
hook). Output → ``forge stage`` (stage-rootfs).

Reproducibility: buildroot is NOT byte-reproducible by default (package file
timestamps) — unlike U-Boot, where SOURCE_DATE_EPOCH alone suffices. The
rootfs.tar is functionally reproducible (same inputs → same content) but not
byte-identical across builds.

The toolchain path (``BR2_TOOLCHAIN_EXTERNAL_PATH``) is overridden at build time
from the board's ``toolchain_bin_dir`` (the single source of truth) — the
defconfig hardcodes ``/opt/…`` because buildroot's Kconfig needs a concrete path;
this relocates the path only, keeping one owner.
"""
from __future__ import annotations

from pathlib import Path

from forge.build import make_env
from forge.build.host import clean_path, warn_windows_path
from forge.build.progress import run_with_progress
from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.proc import Proc


class RootfsBuilder:
    """Builds the buildroot rootfs.tar (UBIFS rootfs)."""

    def __init__(self, board: Board, project: Project,
                 proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)
        self.buildroot = project.buildroot_dir
        self.br2_external = project.root / board.bringup_dir / "buildroot-external"

    def build(self, *, reconfigure: bool = False, clean: bool = False) -> None:
        b = self.board
        if not self.buildroot.is_dir():
            self.log.die(
                f"buildroot tree not found: {self.buildroot} (run: forge fetch buildroot)"
            )
        warn_windows_path(self.log)

        env = make_env(b)
        env["PATH"] = clean_path(env["PATH"])   # buildroot: strip /mnt + whitespace
        env["BR2_EXTERNAL"] = str(self.br2_external)
        # §5.3: expose the forge kernel tree + board id so buildroot's post-build
        # hook can stage the out-of-tree WiFi .ko (the one customization buildroot's
        # native package/overlay can't express — the .ko is built in forge's kernel
        # tree, not a buildroot package). stage-rootfs no longer touches the tree.
        env["FORGE_LINUX_DIR"] = str(self.project.src_dir / b.id / "linux")
        env["FORGE_BOARD"] = b.id
        self.log.info(f"BR2_EXTERNAL={env['BR2_EXTERNAL']}")

        # Arch guard: buildroot output/ is SHARED across boards. Switching arch
        # (armhf↔aarch64) needs `make clean` + regen — package stamps don't
        # invalidate, so the rootfs would carry the OLD arch's binaries (an armhf
        # busybox inside an aarch64 rootfs → boot death). Detect + refuse UNLESS
        # the user passes the explicit arch-switch pair (--clean --reconfigure).
        cfg = self.buildroot / ".config"
        if cfg.is_file() and not (clean and reconfigure):
            text = cfg.read_text(errors="replace")
            if (b.arch == "arm64" and "BR2_aarch64=y" not in text) or \
               (b.arch == "arm" and "BR2_arm=y" not in text):
                self.log.die(
                    f"buildroot .config arch ≠ board ARCH={b.arch} (board={b.id}): a "
                    "previous board's arch lingers in the shared output/. Switch with: "
                    f"`forge build rootfs --board {b.id} --clean --reconfigure`"
                )

        if clean:
            self.log.info("make clean")
            self.proc.run(["make", "clean"], cwd=str(self.buildroot), env_extra=env, quiet=True)
        if reconfigure or not cfg.is_file():
            self.log.info(f"make {b.buildroot_defconfig} (regen .config from the forge defconfig)")
            self.proc.run(["make", b.buildroot_defconfig], cwd=str(self.buildroot), env_extra=env)

        # Toolchain root (parent of bin/) — overridden at build time from the
        # board's single source of truth (matches build-rootfs.sh).
        tc_root = Path(b.toolchain_bin_dir).resolve().parent
        tc_gcc = tc_root / "bin" / f"{b.toolchain_prefix}gcc"
        if not tc_gcc.exists():
            self.log.die(f"toolchain root invalid: {tc_root} (check board toolchain.bin_dir)")
        self.log.info(f"toolchain (from board config): {tc_root}")

        self.log.info("make (PATH cleaned of /mnt + whitespace, "
                      "BR2_TOOLCHAIN_EXTERNAL_PATH from board config)")
        run_with_progress(
            "buildroot", ["make", f"BR2_TOOLCHAIN_EXTERNAL_PATH={tc_root}"],
            project=self.project, proc=self.proc, log=self.log,
            cwd=str(self.buildroot), env_extra=env,
        )

        rootfs_tar = self.buildroot / "output" / "images" / "rootfs.tar"
        if not rootfs_tar.is_file():
            self.log.die("buildroot produced no rootfs.tar")
        self.log.ok(
            f"rootfs.tar → {rootfs_tar} ({rootfs_tar.stat().st_size} B, "
            f"sha256={_sha256_short(rootfs_tar)})"
        )
        self.log.info("next: forge pack (stage-rootfs picks it up)")


def _sha256_short(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
