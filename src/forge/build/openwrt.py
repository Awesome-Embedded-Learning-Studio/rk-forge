"""OpenWrtBuilder — OpenWrt kernel (zImage + aes.dtb) + rootfs tree for aes.

Replaces ``scripts/build-openwrt.sh``. OpenWrt is a full firmware builder: it
builds its OWN musl toolchain, the kernel (linux 7.1 + the quilt patches-7.1/
that carry rk-forge's patches 0001-0016 byte-identical), and the rootfs
(busybox+procd+kmod). rk-forge then takes OpenWrt's kernel artifacts
(``KERNEL_ARTIFACT_DIR``) + rootfs tree (``TARGET_DIR`` via ``forge stage``) and
does its own RK-specific packing (fit-pack + rkfw-pack + mainline U-Boot).

Toolchain: OpenWrt builds its OWN (musl-based). The rk-forge external glibc
toolchain is NOT forced — it would break the musl userspace AND the kmod
vermagic. ``LINUX_DIR`` is deliberately NOT passed (Proc's curated env
allow-list excludes it) so OpenWrt extracts ``dl/linux-7.1.tar.gz`` into its OWN
``build_dir/linux-7.1`` and quilts there — otherwise it would quilt-apply
patches-7.1/ onto rk-forge's ALREADY-patched tree → patch rejects. (The bash did
``env -u LINUX_DIR``; the no-leakage invariant makes that automatic.)

Two non-obvious behaviours preserved exactly:

* **dl/linux-7.1.tar.gz regeneration**: czz8888's kernel-headers download URL is
  broken (GitHub archive is ``v7.1.tar.gz``, not ``linux-7.1.tar.gz`` → 404). It
  is regenerated via ``git archive v7.1 | gzip -n`` from the rk-forge linux tree
  — the hash matches czz8888's ``LINUX_KERNEL_HASH`` (both are the deterministic
  git-archive of tag v7.1).
* **Staged build (not ``make world``)**: ``make world -jN`` races
  package/cleanup vs target/linux reading ``tmp/.packageinfo`` → a STABLE
  failure. Each stage builds separately (still ``-jN`` within a stage), following
  the world dependency chain.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path

from forge.build import make_env
from forge.build.host import clean_path, warn_windows_path
from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.proc import Proc

# czz8888's LINUX_KERNEL_HASH for linux-7.1 (deterministic git-archive of v7.1).
_LINUX_TARBALL_SHA = "ad7f8010a17ecd9959c79cba639dfbbc9dccbbfb7323c5f1d04421368939f18f"
# Build stages (NOT `make world` — see class docstring). Order = world dep chain.
_STAGES = [
    ("tools + toolchain", ["tools/install", "toolchain/install"]),
    ("target/linux (kernel)", ["target/linux/compile"]),
    ("package (rootfs)", ["package/compile", "package/install"]),
    # target/linux/install builds the rootfs image FROM TARGET_DIR, so it MUST
    # run AFTER package/install creates that dir.
    ("target install + index", ["target/linux/install", "target/install", "package/index"]),
]


class OpenWrtBuilder:
    """Builds OpenWrt kernel + rootfs (aes / RK3506 openwrt profile)."""

    def __init__(self, board: Board, project: Project,
                 proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)
        self.openwrt = project.src_dir / board.id / "openwrt"
        self.linux_dir = project.src_dir / board.id / "linux"
        self.bringup = project.root / board.bringup_dir
        self.seed = self.bringup / "openwrt" / f"{board.id}-nand.config"

    def build(self, *, out_dir: Path, reconfigure: bool = False, clean: bool = False) -> None:
        if not self.openwrt.is_dir():
            self.log.die(
                f"openwrt tree not found: {self.openwrt} (run: forge setup --rootfs=openwrt)"
            )
        warn_windows_path(self.log)
        if not self.seed.is_file():
            self.log.die(f"missing OpenWrt .config seed: {self.seed}")

        env = make_env(self.board)
        env["PATH"] = clean_path(env["PATH"])

        # 1. feeds (idempotent unless --reconfigure).
        if not (self.openwrt / "feeds" / "packages").is_dir() or reconfigure:
            self.log.info("feeds update -a && install -a (fetches luci/packages/routing/telephony)")
            self.proc.run(["./scripts/feeds", "update", "-a"],
                          cwd=str(self.openwrt), env_extra=env)
            self.proc.run(["./scripts/feeds", "install", "-a"],
                          cwd=str(self.openwrt), env_extra=env)

        # 2. .config seed → make defconfig.
        if reconfigure or not (self.openwrt / ".config").is_file():
            self.log.info(f"seeding .config from {self.seed} (make defconfig expands dependencies)")
            (self.openwrt / ".config").write_bytes(self.seed.read_bytes())
            self.proc.run(["make", "defconfig"], cwd=str(self.openwrt), env_extra=env)

        self._ensure_linux_tarball(env)

        # 3. clean, then build in stages.
        if clean:
            self.log.info("make clean")
            self.proc.run(["make", "clean"], cwd=str(self.openwrt), env_extra=env, quiet=True)
        for name, targets in _STAGES:
            self._build_stage(name, targets, env)

        # 4. verify kernel artifacts + rootfs tree.
        kdir = self._find_build_dir("linux-7.*", "linux-rockchip_rk3506*")
        if not kdir:
            self.log.die("OpenWrt kernel build dir not found (build failed?)")
        zimage = kdir / "arch" / "arm" / "boot" / "zImage"
        aes_dtb = kdir / "arch" / "arm" / "boot" / "dts" / "rockchip" / "rk3506b-aes.dtb"
        for f in (zimage, aes_dtb):
            if not f.is_file():
                self.log.die(f"missing OpenWrt kernel artifact: {f} (was the aes_nand device selected?)")
        target_dir = self._find_build_dir(None, "root-rockchip", is_dir_glob=True)
        if not (target_dir and (target_dir / "bin" / "busybox").is_file()):
            self.log.die(f"OpenWrt TARGET_DIR missing/incomplete: {target_dir or '<not found>'}")

        self.log.ok(f"OpenWrt zImage → {zimage} ({zimage.stat().st_size} B)")
        self.log.ok(f"OpenWrt aes.dtb → {aes_dtb}")
        self.log.ok(f"OpenWrt rootfs tree → {target_dir}")

        # 5. marker for stage-rootfs fingerprint (forge.sh stage_pack watches mtime).
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / ".openwrt-built").touch()
        self.log.info("next: forge pack (pack-fit reads KERNEL_ARTIFACT_DIR; stage-rootfs rsyncs TARGET_DIR)")

    # ── dl/linux-7.1.tar.gz: regenerate via git archive (download URL broken) ─
    def _ensure_linux_tarball(self, env: dict) -> None:
        tarball = self.openwrt / "dl" / "linux-7.1.tar.gz"
        if tarball.is_file() and hashlib.sha256(tarball.read_bytes()).hexdigest() == _LINUX_TARBALL_SHA:
            self.log.info("dl/linux-7.1.tar.gz present (hash OK) — skip regenerate")
            return
        self.log.info("regenerating dl/linux-7.1.tar.gz via git archive v7.1 (czz8888 download URL is broken)")
        if not (self.linux_dir / ".git").is_dir():
            self.log.die(f"linux tree missing at {self.linux_dir} (run: forge setup --rootfs=openwrt)")
        tarball.parent.mkdir(parents=True, exist_ok=True)
        # git archive --format=tar --prefix=linux-7.1/ v7.1 | gzip -n > tarball
        git = subprocess.Popen(
            ["git", "archive", "--format=tar", "--prefix=linux-7.1/", "v7.1"],
            cwd=str(self.linux_dir), stdout=subprocess.PIPE, env=self.proc.env_for(env))
        gz = subprocess.Popen(["gzip", "-n"], stdin=git.stdout,
                              stdout=open(tarball, "wb"), env=self.proc.env_for(env))
        assert git.stdout is not None
        git.stdout.close()
        rc = gz.wait(); git.wait()
        if rc != 0:
            self.log.die("git archive v7.1 failed")
        if hashlib.sha256(tarball.read_bytes()).hexdigest() != _LINUX_TARBALL_SHA:
            self.log.die(f"generated linux-7.1.tar.gz hash mismatch (expected {_LINUX_TARBALL_SHA})")
        self.log.ok(f"dl/linux-7.1.tar.gz regenerated ({tarball.stat().st_size} B)")

    # ── one build stage: V=s -jN → per-stage log, tail-30 on failure ──────────
    def _build_stage(self, name: str, targets: list[str], env: dict) -> None:
        logf = Path(tempfile.mktemp(prefix=f"forge-openwrt-{re.sub(r'[^A-Za-z0-9]', '-', name)}-"))
        self.log.info(f"[build] {name} (-j{os.cpu_count() or 1}, V=s → {logf})")
        # V=s bypasses OpenWrt's cmd() (silent make -s + fd redirect) which
        # false-fails under -jN. Full verbose → per-stage log; tail only on fail.
        cp = self.proc.run(["make", *targets, "V=s", "-j", str(os.cpu_count() or 1)],
                           cwd=str(self.openwrt), env_extra=env, check=False, capture=True, quiet=True)
        logf.write_text((cp.stdout or "") + (cp.stderr or ""))
        if cp.returncode != 0:
            self.log.warn(f"{name} FAILED — last 30 lines:")
            for line in (cp.stdout or "").splitlines()[-30:]:
                self.log.error(line)
            self.log.die(f"full log: {logf}")
        self.log.ok(f"{name} done")

    def _find_build_dir(self, name_pat: str | None, path_pat: str,
                        *, is_dir_glob: bool = False) -> Path | None:
        """Find a dir under openwrt/build_dir matching name/path patterns."""
        bd = self.openwrt / "build_dir"
        if not bd.is_dir():
            return None
        cands = [p for p in bd.rglob(path_pat) if p.is_dir()]
        if name_pat:
            cands = [p for p in cands if re.match(name_pat, p.name)]
        return cands[0] if cands else None
