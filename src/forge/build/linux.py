"""LinuxBuilder — configure + build the mainline Linux kernel + board DT
(+ optional in-tree WiFi module.ko).

Replaces ``scripts/build-linux.sh``. Paths come off ``Board`` / ``Project``; the
kernel tree's own ``scripts/kconfig/merge_config.sh`` merges the board's defconfig
+ config fragments, then ``make`` runs under :class:`Proc` with an explicit
``ARCH``/``CROSS_COMPILE``/``PATH`` env (via :func:`forge.build.make_env`). When
interactive, the long ``zImage``/``dtbs`` make pipes through buildmeter for a
live progress bar (:mod:`forge.build.progress`).
"""
from __future__ import annotations

import os

from forge.build import check_toolchain, make_env
from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.patch import PatchApplier
from forge.core.proc import Proc
from forge.build.progress import run_with_progress


class LinuxBuilder:
    """Builds the kernel (``zImage``/``Image``) + ``rockchip/<dtb>.dtb`` (+ WiFi .ko)."""

    def __init__(self, board: Board, project: Project,
                 proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)
        self.linux_dir = project.src_dir / board.id / "linux"
        self.board_cfg = project.root / board.board_cfg_dir

    def build(self, *, just_dtb: bool = False, apply_patches: bool = False) -> None:
        b = self.board
        check_toolchain(b, self.log)
        if not self.linux_dir.is_dir():
            self.log.die(f"linux tree not found: {self.linux_dir}")

        # Board kernel fragments (KERNEL_FRAGMENTS) — filenames under board_cfg/,
        # merged in order (later overrides). aes carries trim+compress for NAND
        # boot-size; other boards may carry just kernel.config.
        frag_names = list(b.kernel_fragments) or ["kernel.config"]
        fragments = [self.board_cfg / f for f in frag_names]
        for f in fragments:
            if not f.is_file():
                self.log.die(
                    f"kernel config fragment not found: {f} "
                    f"(set kernel.fragments in config/boards/{b.id}.yaml)"
                )

        env = make_env(b)
        cc_argv = ["make", f"ARCH={b.arch}", f"CROSS_COMPILE={b.toolchain_prefix}"]

        if apply_patches:
            self.log.info("applying DT patches (forge apply)…")
            PatchApplier(b, self.project, worktree=str(self.linux_dir), log=self.log).apply("linux")

        self.log.info(f"merge_config: {b.kernel_base_defconfig} + {[f.name for f in fragments]} …")
        self.proc.run(
            ["scripts/kconfig/merge_config.sh", "-m", "-O", ".",
             b.kernel_base_defconfig, *[str(f) for f in fragments]],
            cwd=str(self.linux_dir), env_extra=env,
        )

        self.log.info("olddefconfig …")
        self.proc.run(cc_argv + ["olddefconfig"], cwd=str(self.linux_dir), env_extra=env)
        self._inject_firmware_dir()

        if just_dtb:
            self.log.info(f"building {b.dtb_name}.dtb only …")
            self.proc.run(cc_argv + [f"rockchip/{b.dtb_name}.dtb"],
                          cwd=str(self.linux_dir), env_extra=env)
            self.log.ok(f"dtb → arch/{b.arch}/boot/dts/rockchip/{b.dtb_name}.dtb")
            return

        self.log.info(f"building {b.kern_img} + dtbs …")
        run_with_progress("kernel", cc_argv + ["-j", str(os.cpu_count() or 1), b.kern_img, "dtbs"],
                          project=self.project, proc=self.proc, log=self.log,
                          cwd=str(self.linux_dir), env_extra=env)
        self.proc.run(cc_argv + [f"rockchip/{b.dtb_name}.dtb"],
                      cwd=str(self.linux_dir), env_extra=env)
        self.log.ok(
            f"{b.kern_img} → arch/{b.arch}/boot/{b.kern_img} ; "
            f"dtb → arch/{b.arch}/boot/dts/rockchip/{b.dtb_name}.dtb"
        )

        self._build_wifi_module(cc_argv, env)

    def _inject_firmware_dir(self) -> None:
        """§5.2.3: if the kernel embeds firmware (CONFIG_EXTRA_FIRMWARE set),
        inject CONFIG_EXTRA_FIRMWARE_DIR = <board_dir>/firmware — resolved from
        Board/Project, NOT a ``/home/...`` hardcode baked in the fragment. No-op
        for boards that don't embed firmware (CONFIG_EXTRA_FIRMWARE empty/absent).
        """
        import re
        cfg = self.linux_dir / ".config"
        text = cfg.read_text()
        m = re.search(r'^CONFIG_EXTRA_FIRMWARE="(.+)"', text, re.M)
        if not m or not m.group(1):
            return   # no firmware embedded → nothing to inject
        fw_dir = self.project.root / self.board.bringup_dir / "firmware"
        if not fw_dir.is_dir():
            self.log.die(f"CONFIG_EXTRA_FIRMWARE set but firmware dir missing: {fw_dir}")
        line = f'CONFIG_EXTRA_FIRMWARE_DIR="{fw_dir}"'
        if re.search(r'^CONFIG_EXTRA_FIRMWARE_DIR=', text, re.M):
            text = re.sub(r'^CONFIG_EXTRA_FIRMWARE_DIR=.*$', line, text, flags=re.M)
        else:
            text += line + "\n"
        cfg.write_text(text)
        self.log.info(f"CONFIG_EXTRA_FIRMWARE_DIR → {fw_dir} (§5.2.3 injected)")

    def _build_wifi_module(self, cc_argv: list[str], env: dict) -> None:
        """In-tree WiFi module.ko (CONFIG_<WIFI_DRIVER>=m).

        Uses the in-tree ``module.ko`` target (NOT ``make M=`` — M= hits a
        modfinal-rule error on these in-tree modules). Board-gated via
        ``wifi_driver``: aes=rtl8733bu (USB), rk3568-atk=rtl8852bs (SDIO). The
        module.ko modpost needs ``Module.symvers``; ``make <kern_img>`` only
        yields ``vmlinux.symvers`` (the driver references only vmlinux symbols —
        CFG80211/MAC80211 are =y built-in), so seed it. Built only when missing;
        incremental runs skip.
        """
        driver = self.board.wifi_driver
        if not driver:
            self.log.info(
                f"no wifi_driver for board {self.board.id!r} — skip WiFi module build"
            )
            return

        mod = driver[3:] if driver.startswith("rtl") else driver   # rtl8733bu → 8733bu
        ko_rel = f"drivers/net/wireless/realtek/{driver}/{mod}.ko"
        ko_abs = self.linux_dir / ko_rel
        if ko_abs.is_file():
            self.log.info(f"{mod}.ko present (skip module build)")
            return

        symvers = self.linux_dir / "Module.symvers"
        if not symvers.is_file():
            vmlinux_symvers = self.linux_dir / "vmlinux.symvers"
            if vmlinux_symvers.is_file():
                symvers.write_bytes(vmlinux_symvers.read_bytes())
        self.log.info(f"building {mod}.ko (in-tree module.ko target; missing — full-rebuild case)")
        run_with_progress("kernel", cc_argv + [ko_rel],
                          project=self.project, proc=self.proc, log=self.log,
                          cwd=str(self.linux_dir), env_extra=env)
        self.log.ok(f"{mod}.ko → {ko_rel}")
