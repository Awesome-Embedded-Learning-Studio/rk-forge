"""Orchestrator — the forge build DAG (replaces scripts/forge.sh).

Composes the leaf builders/packers (in-process — no ``cli.py`` subprocess) in the
right order, each behind :class:`forge.core.stage.Stage` content-hash skipping
(unless ``--force``/``--no-skip``). This is ``forge.sh``'s ``stage_setup /
stage_build / stage_pack / stage_pack_sd / stage_assemble / stage_status /
stage_clean`` + the ``all`` sequence, ported faithfully — same stage order, same
fingerprint inputs (so skip behaviour is byte-identical to the bash ``run_stage``).

Profile-driven (``rootfs_profile``): buildroot (default) / openwrt / ubuntu select
which build + stage + pack chain runs. Storage-driven (``board.storage_kind``):
nand (ubifs + provisioning initramfs + full FIT set) vs emmc/sd (ext4 + single
no-ramdisk boot.img).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from forge.build.initramfs import InitramfsBuilder
from forge.build.linux import LinuxBuilder
from forge.build.rootfs import RootfsBuilder
from forge.build.uboot import UBootBuilder
from forge.build.ubuntu_rootfs import UbuntuRootfsBuilder
from forge.build.host import warn_windows_path
from forge.build.openwrt import OpenWrtBuilder
from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.patch import PatchApplier
from forge.core.proc import Proc
from forge.core.stage import Stage
from forge.fetch.deps import DepsFetcher
from forge.fetch.driver import DriverDrop
from forge.pack.assemble import Updater
from forge.pack.emmc import EmPacker
from forge.pack.fit import FitPacker
from forge.pack.loader import LoaderPacker
from forge.pack.sd import SdPacker
from forge.pack.ubifs import UbiFsPacker
from forge.stage import StageRootfs


class Orchestrator:
    """The forge build/pack/assemble DAG (port of scripts/forge.sh)."""

    def __init__(self, board: Board, project: Project, log: Log | None = None, *,
                 rootfs_profile: str = "buildroot", force: bool = False,
                 no_skip: bool = False):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = Proc(log=self.log)
        self.rootfs_profile = rootfs_profile
        self.force = force
        self.no_skip = no_skip

        b = board
        self.bringup = project.root / b.bringup_dir
        self.out_dir = self.project.out_root / b.id   # aggregated root out/<board>/
        self.state_dir = self.out_dir / ".forge-stage"
        self.linux_dir = project.src_dir / b.id / "linux"
        self.uboot_dir = project.src_dir / b.id / "uboot"
        self.openwrt_dir = project.src_dir / b.id / "openwrt"
        self.buildroot = project.buildroot_dir
        self.rkbin_blobs = project.rkbin_dir / b.rkbin_blob_subdir
        self.board_cfg = project.root / b.board_cfg_dir
        self.stage = Stage(self.state_dir, board, self.log)

    @property
    def kernel_artifact_dir(self) -> Path:
        """Where pack-fit reads zImage+dtb: the OpenWrt build_dir (openwrt) or
        the forge linux tree (buildroot/ubuntu)."""
        if self.rootfs_profile == "openwrt":
            import glob
            hits = glob.glob(str(self.openwrt_dir / "build_dir" / "*" / "linux-rockchip_rk3506*" / "linux-7.*"))
            hits = [h for h in hits if (Path(h) / "arch" / "arm" / "boot" / "zImage").exists()]
            return Path(hits[0]) if hits else self.linux_dir
        return self.linux_dir

    def _run(self, name: str, inputs: list[str], action) -> None:
        self.stage.run(name, [Path(i) for i in inputs], action,
                       force=self.force, no_skip=self.no_skip)

    # ── setup: submodule + fetch + apply ──────────────────────────────────────
    def setup(self) -> None:
        b = self.board
        self.log.info("[setup] init git submodules (third_party/rkbin — boot_merger + blob source)")
        self.proc.run(["git", "-C", str(self.project.root), "submodule", "update", "--init"])

        profile = self.rootfs_profile
        fetcher = DepsFetcher(b, self.project, self.proc, self.log)
        if profile == "openwrt":
            self.log.info("[setup] fetching (openwrt profile: linux + uboot + openwrt)")
            for t in ("linux", "uboot", "openwrt"):
                fetcher.fetch(t)
        elif profile == "ubuntu":
            self.log.info("[setup] fetching (ubuntu profile: linux + uboot; rootfs is ubuntu-base+apt, NO buildroot)")
            for t in ("linux", "uboot"):
                fetcher.fetch(t)
            if b.wifi_driver:
                DriverDrop(b, self.project, self.proc, self.log).fetch(force=self.force)
        else:
            self.log.info("[setup] fetching (buildroot profile: linux + uboot + buildroot + wifi driver)")
            fetcher.fetch("all")
            if b.wifi_driver:
                DriverDrop(b, self.project, self.proc, self.log).fetch(force=self.force)

        # apply the board patch series into each component tree when (and only
        # when) its content changed — see _apply_series for the fingerprint.
        if profile != "openwrt":
            self._apply_series("linux", self.linux_dir)
        self._apply_series("uboot", self.uboot_dir)
        if profile == "openwrt":
            self._apply_series("openwrt", self.openwrt_dir)
        self.log.ok(f"setup complete (profile={profile})")

    def _apply_series(self, component: str, tree: Path) -> None:
        """Apply the board patch series into ``tree`` — but only when it changed.

        The skip guard is a content fingerprint (pinned base + series file +
        every listed patch, via :meth:`PatchApplier.series_digest`) recorded
        after a successful apply, PLUS a sanity check that the tree actually
        moved past the base (covers a tree that was re-fetched clean while the
        fingerprint survived in out/).  The old HEAD==base guard went stale the
        moment the series grew while HEAD stood still — freshly added patches
        were silently skipped (2026-08-15: series 0011→0017, build would have
        shipped without 0013-0017).

        On mismatch the tree is reset to the pinned base and the whole series
        replayed via git am: the tree is derived state, edits belong in the
        patch files (the 9e3de8e1 baud lesson).  ``clean -fdq`` deliberately
        keeps ignored artifacts (.config, build outputs) so the kernel rebuild
        stays incremental after a replay.
        """
        base = self._pin_ref(component)
        if base is None:
            return
        series = self.project.root / "boards" / self.board.id / "patches" / component / "series"
        if not series.is_file():
            self.log.info(f"[setup] {component}: no patch series — nothing to apply")
            return
        base_sha = self._git_peel(tree, base)
        if not base_sha:
            self.log.warn(f"[setup] {component}: cannot resolve base ref {base!r} — skip apply")
            return
        digest = PatchApplier.series_digest(series, base_sha)
        fp_file = self.state_dir / f"apply-{component}.fingerprint"
        if (not self.force and fp_file.is_file()
                and fp_file.read_text().strip() == digest
                and self._git_head(tree) != base_sha):
            self.log.info(f"[setup] {component} series unchanged (fingerprint match) — skip apply")
            return
        if fp_file.is_file():
            self.log.info(f"[setup] {component} series changed since last apply — "
                          f"resetting tree to {base} and replaying series")
        else:
            self.log.info(f"[setup] applying {component} series (no fingerprint yet)")
        self._git_in(tree, "reset", "--hard", base_sha)
        self._git_in(tree, "clean", "-fdq")
        PatchApplier(self.board, self.project, worktree=str(tree), log=self.log).apply(component)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        fp_file.write_text(digest + "\n")

    def _pin_ref(self, component: str) -> str | None:
        from forge import fetch
        pin = fetch.read_source(self.board.sources, self.project.sources, component)
        return pin[1] if pin else None

    def _git_head(self, tree: Path) -> str:
        return self.proc.run(["git", "-C", str(tree), "rev-parse", "HEAD"],
                             capture=True, quiet=True).stdout.strip()

    def _git_in(self, tree: Path, *args: str) -> None:
        """Run git in ``tree``; dies loudly on failure (Proc default check)."""
        self.proc.run(["git", "-C", str(tree), *args], capture=True, quiet=True)

    def _git_peel(self, tree: Path, ref: str) -> str:
        return self.proc.run(["git", "-C", str(tree), "rev-parse", f"{ref}^{{commit}}"],
                             capture=True, quiet=True).stdout.strip()

    # ── build ─────────────────────────────────────────────────────────────────
    def build(self) -> None:
        warn_windows_path(self.log)
        profile = self.rootfs_profile
        if profile == "openwrt":
            self.log.info("[build] OpenWrt kernel+rootfs (OpenWrt builds the kernel)")
            OpenWrtBuilder(self.board, self.project, self.proc, self.log).build(out_dir=self.out_dir)
            self.log.info("[build] U-Boot (rk-forge mainline, reused)")
            UBootBuilder(self.board, self.project, self.proc, self.log).build()
        elif profile == "ubuntu":
            self.log.info("[build] kernel (make is internally incremental)")
            LinuxBuilder(self.board, self.project, self.proc, self.log).build()
            self.log.info("[build] U-Boot (SOURCE_DATE_EPOCH → byte-reproducible)")
            UBootBuilder(self.board, self.project, self.proc, self.log).build()
            self.log.info("[build] rootfs (ubuntu-base + apt via qemu-user-static)")
            UbuntuRootfsBuilder(self.board, self.project, self.proc, self.log).build(out_dir=self.out_dir)
        else:
            self.log.info("[build] kernel (make is internally incremental)")
            LinuxBuilder(self.board, self.project, self.proc, self.log).build()
            self.log.info("[build] U-Boot (SOURCE_DATE_EPOCH → byte-reproducible)")
            UBootBuilder(self.board, self.project, self.proc, self.log).build()
            self.log.info("[build] rootfs (buildroot + WSL clean PATH)")
            RootfsBuilder(self.board, self.project, self.proc, self.log).build()
        self.log.ok(f"build complete (profile={profile})")

    # ── pack ──────────────────────────────────────────────────────────────────
    def pack(self) -> None:
        b = self.board
        self.out_dir.mkdir(parents=True, exist_ok=True)
        kad = self.kernel_artifact_dir
        if self.rootfs_profile == "openwrt":
            self.log.info(f"[pack] kernel artifacts from OpenWrt build_dir: {kad}")

        loader_ini = self.bringup / b.loader_ini
        self._run("pack-loader", [
            str(loader_ini), str(self.rkbin_blobs),
            "src/forge/pack/loader.py", "src/forge/core/rkbin.py",
            f"boards/{b.id}/board.yaml",
        ], lambda: LoaderPacker(b, self.project, proc=self.proc, log=self.log).pack(out_dir=self.out_dir))

        # stage-rootfs inputs are profile-specific.
        stage_inputs = {
            "openwrt": [str(self.out_dir / ".openwrt-built"), "src/forge/stage.py"],
            "ubuntu": [str(self.out_dir / "ubuntu-rootfs.tar"),
                       str(self.out_dir / ".ubuntu-rootfs-built"), "src/forge/stage.py"],
            "buildroot": [str(self.buildroot / "output" / "images" / "rootfs.tar"), "src/forge/stage.py"],
        }[self.rootfs_profile]
        # user/ drop-ins (wifi creds, pubkeys, DNS) bake into the staged tree —
        # they MUST be in the stage-rootfs fingerprint, else a mid-session edit
        # silently reuses the stale tree (board-caught 2026-08-15: ssid baked
        # from a stale guess while wifi.yaml already carried the real one).
        user_d = self.project.root / "user"
        if user_d.is_dir():
            stage_inputs += [str(f) for f in sorted(user_d.glob("*.yaml"))]
        self._run("stage-rootfs", stage_inputs,
                  lambda: StageRootfs(b, self.project, self.proc, self.log).stage(
                      out_dir=self.out_dir, profile=self.rootfs_profile))

        if b.is_emmc:
            self._pack_emmc(kad)
        else:
            self._pack_nand(kad)

    def _pack_emmc(self, kad: Path) -> None:
        b = self.board
        self._run("pack-emmc", [
            str(self.out_dir / "rootfs"), str(self.state_dir / "stage-rootfs.fingerprint"),
            str(self.bringup / "fit" / "boot-emmc.cmd"),
            "src/forge/pack/emmc.py", f"boards/{b.id}/board.yaml",
        ], lambda: EmPacker(b, self.project, proc=self.proc, log=self.log).pack(out_dir=self.out_dir))
        self._run("pack-fit", [
            str(self.bringup / "fit" / f"{b.soc}-kernel.its"),
            str(kad / "arch" / b.arch / "boot" / b.kern_img),
            str(kad / "arch" / b.arch / "boot" / "dts" / "rockchip" / f"{b.dtb_name}.dtb"),
            str(self.uboot_dir / "u-boot.itb"),
            "src/forge/pack/fit.py", "src/forge/tools/fit_pack.py", f"boards/{b.id}/board.yaml",
        ], lambda: FitPacker(b, self.project, proc=self.proc, log=self.log).pack(
            out_dir=self.out_dir, kernel_artifact_dir=kad))

    def _pack_nand(self, kad: Path) -> None:
        b = self.board
        self._run("pack-ubifs", [
            str(self.out_dir / "rootfs"), str(self.buildroot / "output" / "images" / "rootfs.tar"),
            "src/forge/pack/ubifs.py", f"boards/{b.id}/board.yaml",
        ], lambda: UbiFsPacker(b, proc=self.proc, log=self.log).pack(
            rootfs_tree=self.out_dir / "rootfs",
            ubifs_out=self.out_dir / "rootfs.ubifs", ubi_out=self.out_dir / "rootfs.ubi.img"))
        self._run("build-initramfs", [
            str(self.bringup / "initramfs" / "init"), str(self.bringup / "rootfs" / "ubiprog.c"),
            "forge.yaml", str(self.out_dir / "rootfs.ubi.img"),
            "src/forge/build/initramfs.py",
        ], lambda: InitramfsBuilder(b, self.project, self.proc, self.log).build(out_dir=self.out_dir))
        self._run("pack-fit", [
            str(self.bringup / "fit" / f"{b.soc}-mainline.its"),
            str(self.bringup / "fit" / f"{b.soc}-kernel.its"),
            str(self.bringup / "fit" / f"{b.soc}-kernel-nand.its"),
            str(kad / "arch" / b.arch / "boot" / b.kern_img),
            str(kad / "arch" / b.arch / "boot" / "dts" / "rockchip" / f"{b.dtb_name}.dtb"),
            str(self.uboot_dir / "u-boot-nodtb.bin"), str(self.uboot_dir / "u-boot.dtb"),
            str(self.bringup / "fit" / "initramfs.cpio.gz"),
            "src/forge/pack/fit.py", "src/forge/tools/fit_pack.py", f"boards/{b.id}/board.yaml",
        ], lambda: FitPacker(b, self.project, proc=self.proc, log=self.log).pack(
            out_dir=self.out_dir, kernel_artifact_dir=kad))

    # ── pack-sd (second boot media; reuses NAND pack outputs) ─────────────────
    def pack_sd(self) -> None:
        b = self.board
        self.pack()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        sd_defcfg = self.uboot_dir / "configs" / b.uboot_defconfig_sd
        self._run("build-uboot-sd", [str(sd_defcfg), "src/forge/build/uboot.py"],
                  lambda: UBootBuilder(b, self.project, self.proc, self.log).build(variant="sd"))
        self._run("pack-fit-sd", [
            str(self.out_dir / "u-boot-sd-nodtb.bin"), str(self.out_dir / "u-boot-sd.dtb"),
            str(self.bringup / "fit" / f"{b.soc}-mainline.its"),
            "src/forge/pack/fit.py", "src/forge/tools/fit_pack.py", f"boards/{b.id}/board.yaml",
        ], lambda: FitPacker(b, self.project, proc=self.proc, log=self.log).pack(
            variant="sd", out_dir=self.out_dir, kernel_artifact_dir=self.kernel_artifact_dir))
        self._run("pack-sd", [
            str(self.out_dir / "idblock.img"), str(self.out_dir / "uboot.img"),
            str(self.out_dir / "boot.img"), str(self.out_dir / "rootfs"),
            "src/forge/pack/sd.py", f"boards/{b.id}/board.yaml",
        ], lambda: SdPacker(b, self.project, proc=self.proc, log=self.log).pack(out_dir=self.out_dir))

    # ── assemble ──────────────────────────────────────────────────────────────
    def assemble(self, variant: str = "provision", verify: bool = True) -> None:
        b = self.board
        if b.is_emmc:
            self._run("assemble-emmc", [
                str(self.out_dir / "boot.img"), str(self.out_dir / "rootfs.ext4"),
                str(self.out_dir / "u-boot.itb"), str(self.out_dir / "MiniLoaderAll.bin"),
                str(self.bringup / b.parameter.get("emmc", "")),
                "src/forge/pack/assemble.py", "src/forge/tools/rkfw_pack.py", f"boards/{b.id}/board.yaml",
            ], lambda: Updater(b, self.project, proc=self.proc, log=self.log).assemble(
                variant="emmc", out_dir=self.out_dir, verify=verify))
        elif variant == "sd":
            self.pack_sd()
            pkg = self.bringup / b.package.get("sd", "")
            self._run("assemble-sd", [
                str(self.out_dir / "boot-sd.img"), str(self.out_dir / "rootfs.ext4"),
                str(self.out_dir / "uboot-sd.img"), str(self.out_dir / "MiniLoaderAll.bin"),
                str(self.bringup / b.parameter.get("sd", "")), str(pkg),
                "src/forge/pack/assemble.py", "src/forge/tools/rkfw_pack.py", f"boards/{b.id}/board.yaml",
            ], lambda: Updater(b, self.project, proc=self.proc, log=self.log).assemble(
                variant="sd", out_dir=self.out_dir, verify=verify))
        else:
            self._run("assemble", [
                str(self.out_dir / "boot.img"), str(self.out_dir / "rootfs.ubi.img"),
                str(self.out_dir / "uboot.img"), str(self.out_dir / "MiniLoaderAll.bin"),
                str(self.bringup / b.parameter.get("nand", "")),
                "src/forge/pack/assemble.py", "src/forge/tools/rkfw_pack.py", f"boards/{b.id}/board.yaml",
            ], lambda: Updater(b, self.project, proc=self.proc, log=self.log).assemble(
                variant=variant, out_dir=self.out_dir, verify=verify))

    # ── all / status / clean ──────────────────────────────────────────────────
    def all(self, variant: str = "provision") -> None:
        self.setup()
        self.build()
        self.pack()
        self.assemble(variant)
        self.log.ok(f"all done → {self.out_dir}/update.img")

    def status(self) -> None:
        for s in ("build-initramfs", "pack-loader", "pack-fit", "stage-rootfs",
                  "pack-ubifs", "pack-emmc", "build-uboot-sd", "pack-fit-sd",
                  "pack-sd", "assemble", "assemble-emmc", "assemble-sd"):
            fp = self.state_dir / f"{s}.fingerprint"
            if fp.is_file():
                self.log.ok(f"{s}: recorded")
            else:
                self.log.info(f"{s}: not run yet")

    def clean(self, full: bool = False) -> None:
        self.log.info(f"removing {self.out_dir} (pack artifacts + stage fingerprints)")
        shutil.rmtree(self.out_dir, ignore_errors=True)
        if full:
            from forge.build import check_toolchain, make_env
            check_toolchain(self.board, self.log)
            tc_env = make_env(self.board)   # toolchain on PATH so mrproper's CC queries resolve
            self.log.info("[--full] make mrproper linux + uboot + make clean buildroot")
            arch = self.board.uboot_arch_override
            for d, a in ((self.linux_dir, self.board.arch), (self.uboot_dir, arch)):
                self.proc.run(["make", "-C", str(d), f"ARCH={a}",
                               f"CROSS_COMPILE={self.board.toolchain_prefix}", "mrproper"],
                              env_extra=tc_env)
            self.proc.run(["make", "-C", str(self.buildroot), "clean"])
            self.log.ok("source trees cleaned (full-rebuild basis)")
        self.log.ok(f"clean done (--full={int(full)})")
