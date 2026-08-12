"""forge CLI entry — dual-mode.

Invoked either as an installed console script (``forge ...``) or directly by
path (``python3 src/forge/cli.py ...``); the latter needs no ``pip install``
because the path self-fix below puts ``src/`` on ``sys.path``. The env.sh bridge
(PR1) uses the direct-path form.

Subcommands are methods on :class:`ForgeCLI`; the repo root + a shared
:class:`Log` are instance state. New subcommands (setup/build/pack/… land across
PR3–F3) are added as one ``_cmd_*`` method + one ``_register_*`` call each.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Path self-fix: when run by path (no package context), add src/ so forge.* imports resolve.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # src/

import argparse

from forge.build.initramfs import InitramfsBuilder
from forge.build.linux import LinuxBuilder
from forge.build.openwrt import OpenWrtBuilder
from forge.build.rootfs import RootfsBuilder
from forge.build.uboot import UBootBuilder
from forge.build.ubuntu_rootfs import UbuntuRootfsBuilder
from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.dag import Orchestrator
from forge.core.patch import PatchApplier
from forge.core.proc import Proc
from forge.doctor import Doctor
from forge.fetch.deps import DepsFetcher
from forge.fetch.driver import DriverDrop
from forge.flash import Flasher
from forge.stage import StageRootfs
from forge.pack.assemble import Updater, _VARIANTS
from forge.pack.emmc import EmPacker
from forge.pack.fit import FitPacker
from forge.pack.loader import LoaderPacker
from forge.pack.sd import SdPacker
from forge.pack.ubifs import UbiFsPacker

REPO_ROOT = Path(__file__).resolve().parents[2]


class ForgeCLI:
    """The ``forge`` command. Holds shared state (repo root, logger) and
    dispatches subcommands to its own ``_cmd_*`` methods."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else REPO_ROOT
        self.log = Log()

    def main(self, argv: list[str] | None = None) -> int:
        args = self._build_parser().parse_args(argv)
        return args.func(args)

    def _build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="forge", description="rk-forge build orchestrator")
        parser.add_argument("--root", default=None, help="repo root (default: this package's repo root)")
        sub = parser.add_subparsers(dest="cmd", required=True)
        self._register_config(sub)
        self._register_apply(sub)
        self._register_build(sub)
        self._register_pack(sub)
        self._register_assemble(sub)
        self._register_pdf(sub)
        self._register_doctor(sub)
        self._register_fetch(sub)
        self._register_stage(sub)
        self._register_flash(sub)
        self._register_setup(sub)
        self._register_all(sub)
        self._register_clean(sub)
        self._register_status(sub)
        self._register_pack_sd(sub)
        return parser

    # ── orchestration helpers (the DAG — replaces scripts/forge.sh) ───────────
    @staticmethod
    def _orch_flags(p) -> None:
        """Flags shared by the orchestration commands (setup/build/pack/all/…)."""
        p.add_argument("--rootfs", choices=["buildroot", "openwrt", "ubuntu"],
                       default="buildroot", help="rootfs/kernel profile (default: buildroot)")
        p.add_argument("--force", action="store_true",
                       help="re-run stages even if inputs are unchanged")
        p.add_argument("--no-skip", action="store_true",
                       help="run every stage unconditionally (no content-hash skipping)")

    def _orch(self, args: argparse.Namespace) -> Orchestrator:
        root = args.root or self.root
        return Orchestrator(
            Board.from_yaml(args.board, root=root), Project.from_yaml(root), self.log,
            rootfs_profile=args.rootfs, force=args.force, no_skip=args.no_skip)

    # ── subcommand: config ───────────────────────────────────────────────────
    def _register_config(self, sub) -> None:
        cfg = sub.add_parser("config", help="load / emit board config")
        cfg.add_argument("--board", required=True)
        cfg.add_argument("--emit-env", action="store_true", help="emit bash-sourceable board env")
        cfg.set_defaults(func=self._cmd_config)

    def _cmd_config(self, args: argparse.Namespace) -> int:
        if not args.emit_env:
            raise SystemExit("error: `forge config` needs an action (try --emit-env)")
        sys.stdout.write(Board.from_yaml(args.board, root=args.root or self.root).to_bash_env())
        return 0

    # ── subcommand: apply ────────────────────────────────────────────────────
    def _register_apply(self, sub) -> None:
        ap = sub.add_parser("apply", help="apply a quilt-style patch series into a component worktree")
        ap.add_argument("--board", required=True)
        ap.add_argument("--component", required=True, help="linux | uboot | openwrt")
        ap.add_argument("--worktree", required=True, help="the component git worktree dir")
        ap.add_argument("--check", action="store_true", help="dry-run: apply then revert")
        ap.set_defaults(func=self._cmd_apply)

    def _cmd_apply(self, args: argparse.Namespace) -> int:
        root = args.root or self.root
        board = Board.from_yaml(args.board, root=root)
        PatchApplier(board, Project.from_yaml(root), worktree=args.worktree, log=self.log).apply(
            args.component, check=args.check)
        return 0

    # ── subcommand: build ─────────────────────────────────────────────────────
    def _register_build(self, sub) -> None:
        b = sub.add_parser("build",
                           help="build stage (no component = whole DAG) or one builder")
        b.add_argument("--board", required=True)
        b.add_argument("component", nargs="?", default=None,
                       choices=["linux", "uboot", "initramfs", "rootfs", "openwrt", "ubuntu-rootfs"],
                       help="one builder; omit to run the whole build stage")
        self._orch_flags(b)
        b.add_argument("--just-dtb", action="store_true",
                       help="linux: build only rockchip/<dtb>.dtb (fast DT sanity check)")
        b.add_argument("--apply-patches", action="store_true",
                       help="linux: apply the patch series first (clean-tree setup)")
        b.add_argument("--variant", choices=["nand", "sd"], default="nand",
                       help="uboot: nand (default, in-tree) | sd (throwaway worktree)")
        b.add_argument("--clean", action="store_true",
                       help="uboot/initramfs/rootfs: force a clean rebuild")
        b.add_argument("--reconfigure", action="store_true",
                       help="rootfs: regen .config from the forge defconfig before make")
        b.add_argument("--out", default=None,
                       help="initramfs: output cpio.gz path (default: <bringup>/fit/initramfs.cpio.gz)")
        b.add_argument("--version", default="26.04",
                       help="ubuntu-rootfs: ubuntu-base release version (default: 26.04)")
        b.set_defaults(func=self._cmd_build)

    def _cmd_build(self, args: argparse.Namespace) -> int:
        if args.component is None:
            self._orch(args).build()   # the whole build stage (DAG)
            return 0
        root = args.root or self.root
        board = Board.from_yaml(args.board, root=root)
        project = Project.from_yaml(root)
        if args.component == "linux":
            LinuxBuilder(board, project, log=self.log).build(
                just_dtb=args.just_dtb, apply_patches=args.apply_patches)
        elif args.component == "uboot":
            UBootBuilder(board, project, log=self.log).build(
                variant=args.variant, clean=args.clean,
                out_dir=self._out_dir(project, board))
        elif args.component == "initramfs":
            InitramfsBuilder(board, project, log=self.log).build(
                out_dir=self._out_dir(project, board),
                out_cpio=args.out, clean=args.clean)
        elif args.component == "rootfs":
            RootfsBuilder(board, project, log=self.log).build(
                reconfigure=args.reconfigure, clean=args.clean)
        elif args.component == "openwrt":
            OpenWrtBuilder(board, project, log=self.log).build(
                out_dir=self._out_dir(project, board),
                reconfigure=args.reconfigure, clean=args.clean)
        elif args.component == "ubuntu-rootfs":
            UbuntuRootfsBuilder(board, project, log=self.log).build(
                out_dir=self._out_dir(project, board),
                version=args.version, clean=args.clean)
        return 0

    # ── subcommand: pack ─────────────────────────────────────────────────────
    def _register_pack(self, sub) -> None:
        pack = sub.add_parser("pack",
                              help="pack stage (no component = whole DAG) or one packer")
        pack.add_argument("--board", required=True)
        pack.add_argument("component", nargs="?", default=None,
                          choices=["ubifs", "fit", "loader", "sd", "emmc"],
                          help="one packer; omit to run the whole pack stage")
        self._orch_flags(pack)
        pack.add_argument("--variant", choices=["nand", "sd"], default="nand", help="fit: nand (default) | sd")
        pack.add_argument("--kernel-dir", default=None,
                          help="fit: kernel artifact dir (default: the board's linux tree)")
        pack.set_defaults(func=self._cmd_pack)

    def _cmd_pack(self, args: argparse.Namespace) -> int:
        if args.component is None:
            self._orch(args).pack()   # the whole pack stage (DAG)
            return 0
        root = args.root or self.root
        board = Board.from_yaml(args.board, root=root)
        project = Project.from_yaml(root)
        out_dir = self._out_dir(project, board)

        packers = {
            "ubifs": lambda: UbiFsPacker(board, log=self.log).pack(
                rootfs_tree=out_dir / "rootfs", ubifs_out=out_dir / "rootfs.ubifs",
                ubi_out=out_dir / "rootfs.ubi.img"),
            "fit": lambda: FitPacker(board, project, log=self.log).pack(
                variant=args.variant, out_dir=out_dir, kernel_artifact_dir=args.kernel_dir),
            "loader": lambda: LoaderPacker(board, project, log=self.log).pack(out_dir=out_dir),
            "sd": lambda: SdPacker(board, project, log=self.log).pack(out_dir=out_dir),
            "emmc": lambda: EmPacker(board, project, log=self.log).pack(out_dir=out_dir),
        }
        action = packers.get(args.component)
        if action is None:
            raise SystemExit(f"unknown pack component: {args.component}")
        action()
        return 0

    # ── subcommand: assemble ─────────────────────────────────────────────────
    def _register_assemble(self, sub) -> None:
        asm = sub.add_parser("assemble", help="assemble update.img (content-hash skipping)")
        asm.add_argument("--board", required=True)
        self._orch_flags(asm)
        asm.add_argument("--variant", choices=list(_VARIANTS), default="provision",
                         help="provision (default) | nand | rescue | sd | emmc")
        asm.add_argument("--no-verify", action="store_true", help="skip the round-trip self-check")
        asm.set_defaults(func=self._cmd_assemble)

    def _cmd_assemble(self, args: argparse.Namespace) -> int:
        self._orch(args).assemble(args.variant, verify=not args.no_verify)
        return 0

    # ── subcommand: setup / all / clean / status / pack-sd ────────────────────
    def _register_setup(self, sub) -> None:
        s = sub.add_parser("setup", help="init submodule + fetch sources + apply patch series")
        s.add_argument("--board", required=True)
        self._orch_flags(s)
        s.set_defaults(func=lambda a: (self._orch(a).setup(), 0)[1])

    def _register_all(self, sub) -> None:
        al = sub.add_parser("all", help="setup → build → pack → assemble (the whole pipeline)")
        al.add_argument("--board", required=True)
        self._orch_flags(al)
        al.add_argument("--variant", choices=list(_VARIANTS), default="provision",
                        help="assemble variant (default: provision)")
        al.set_defaults(func=lambda a: (self._orch(a).all(a.variant), 0)[1])

    def _register_clean(self, sub) -> None:
        c = sub.add_parser("clean", help="remove out/ (artifacts + fingerprints); --full also mrproper")
        c.add_argument("--board", required=True)
        c.add_argument("--full", action="store_true",
                       help="also mrproper linux/uboot + clean buildroot (full-rebuild basis)")
        c.set_defaults(func=lambda a: (self._orch_full(a), 0)[1])

    def _orch_full(self, args: argparse.Namespace):
        # clean has --full instead of the orch skip flags; build a minimal orch.
        root = args.root or self.root
        return Orchestrator(Board.from_yaml(args.board, root=root), Project.from_yaml(root),
                            self.log).clean(full=args.full)

    def _register_status(self, sub) -> None:
        st = sub.add_parser("status", help="show which stages are recorded (content-hash state)")
        st.add_argument("--board", required=True)
        st.set_defaults(func=lambda a: (self._orch_status(a), 0)[1])

    def _orch_status(self, args: argparse.Namespace):
        root = args.root or self.root
        return Orchestrator(Board.from_yaml(args.board, root=root), Project.from_yaml(root),
                            self.log).status()

    def _register_pack_sd(self, sub) -> None:
        psd = sub.add_parser("pack-sd", help="pack a bootable SD-card image (sd.img)")
        psd.add_argument("--board", required=True)
        self._orch_flags(psd)
        psd.set_defaults(func=lambda a: (self._orch(a).pack_sd(), 0)[1])

    @staticmethod
    def _out_dir(project: Project, board: Board) -> Path:
        """Where this board's build products land: root ``out/<board>/``
        (aggregated — update.img visible at out/'s top level, not buried in a
        board dir). Single point; every stage routes through here."""
        return project.out_root / board.id

    # ── subcommand: doctor ────────────────────────────────────────────────────
    def _register_doctor(self, sub) -> None:
        d = sub.add_parser("doctor", help="check host build deps + cross toolchain")
        d.add_argument("--board", default=None,
                       help="board whose toolchain to check (default: forge.yaml default_board)")
        d.set_defaults(func=self._cmd_doctor)

    def _cmd_doctor(self, args: argparse.Namespace) -> int:
        root = args.root or self.root
        project = Project.from_yaml(root)
        board_id = args.board or project.default_board
        return Doctor(Board.from_yaml(board_id, root=root), log=self.log).run()

    # ── subcommand: fetch ─────────────────────────────────────────────────────
    def _register_fetch(self, sub) -> None:
        f = sub.add_parser("fetch", help="clone pinned source trees / WiFi driver drops")
        f.add_argument("--board", required=True)
        f.add_argument("target",
                       choices=["linux", "uboot", "buildroot", "openwrt", "driver", "all"],
                       default="all", nargs="?",
                       help="what to fetch (all = linux+uboot+buildroot + the board's wifi driver)")
        f.add_argument("--force", action="store_true",
                       help="driver: refetch even if the .forge-fetched marker is present")
        f.set_defaults(func=self._cmd_fetch)

    def _cmd_fetch(self, args: argparse.Namespace) -> int:
        root = args.root or self.root
        board = Board.from_yaml(args.board, root=root)
        project = Project.from_yaml(root)
        if args.target == "driver":
            DriverDrop(board, project, log=self.log).fetch(force=args.force)
        else:
            DepsFetcher(board, project, log=self.log).fetch(args.target)
            if args.target == "all" and board.wifi_driver:
                DriverDrop(board, project, log=self.log).fetch(force=args.force)
        return 0

    # ── subcommand: stage ─────────────────────────────────────────────────────
    def _register_stage(self, sub) -> None:
        st = sub.add_parser("stage",
                            help="materialize out/rootfs/ from the built rootfs source (pure)")
        st.add_argument("--board", required=True)
        st.add_argument("--profile", choices=["buildroot", "openwrt", "ubuntu"],
                        default="buildroot",
                        help="which rootfs source to materialize (default: buildroot)")
        st.add_argument("--out", default=None,
                        help="out dir (default: the board's bringup/out)")
        st.set_defaults(func=self._cmd_stage)

    def _cmd_stage(self, args: argparse.Namespace) -> int:
        root = args.root or self.root
        board = Board.from_yaml(args.board, root=root)
        project = Project.from_yaml(root)
        StageRootfs(board, project, log=self.log).stage(
            out_dir=Path(args.out) if args.out else self._out_dir(project, board),
            profile=args.profile)
        return 0

    # ── subcommand: flash ─────────────────────────────────────────────────────
    def _register_flash(self, sub) -> None:
        fl = sub.add_parser("flash",
                            help="write sd.img to a physical SD card (guard chain; sudo dd)")
        fl.add_argument("--board", required=True)
        fl.add_argument("--device", default=None,
                        help="target block device, e.g. /dev/sdc (REQUIRED; lists candidates if omitted)")
        fl.add_argument("--img", default=None, help="image to write (default: <bringup>/out/sd.img)")
        fl.add_argument("--yes", "-y", action="store_true",
                        help="skip the typed confirmation prompt (CI / confident re-flash)")
        fl.set_defaults(func=self._cmd_flash)

    def _cmd_flash(self, args: argparse.Namespace) -> int:
        root = args.root or self.root
        board = Board.from_yaml(args.board, root=root)
        project = Project.from_yaml(root)
        Flasher(board, project, log=self.log).flash(
            device=args.device or "", img=args.img,
            assume_yes=args.yes, out_dir=self._out_dir(project, board))
        return 0

    # ── subcommand: pdf ──────────────────────────────────────────────────────
    def _register_pdf(self, sub) -> None:
        p = sub.add_parser("pdf",
                           help="build the all-in-one tutorial PDF (pandoc + WeasyPrint)")
        p.set_defaults(func=self._cmd_pdf)

    def _cmd_pdf(self, args: argparse.Namespace) -> int:
        # build_pdf.py is a self-contained doc builder with its OWN heavy deps
        # (pypandoc-binary + weasyprint) that must NOT be imported into the forge
        # package. It runs in an ephemeral uv env, exactly as build-pdf.sh did.
        root = args.root or self.root
        builder = root / "document" / "pdf" / "build_pdf.py"
        if not builder.is_file():
            self.log.die(f"PDF builder missing: {builder}")
        Proc(log=self.log).run(
            ["uv", "run", "--no-project",
             "--with", "pypandoc-binary", "--with", "weasyprint",
             "python3", str(builder)],
            cwd=str(root))
        return 0


def main(argv: list[str] | None = None) -> int:
    # When invoked under sudo, git refuses to operate on the (non-root-owned)
    # repo + source trees ("dubious ownership"). forge handles this internally:
    # inject safe.directory=* so git trusts the dirs for this run. The user runs
    # `sudo forge ...` with no git-config workaround on their side.
    if os.geteuid() == 0 and os.environ.get("SUDO_USER"):
        os.environ["GIT_CONFIG_PARAMETERS"] = "'safe.directory=*'"
    return ForgeCLI().main(argv)


if __name__ == "__main__":
    sys.exit(main())
