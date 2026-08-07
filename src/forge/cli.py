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

import sys
from pathlib import Path

# Path self-fix: when run by path (no package context), add src/ so forge.* imports resolve.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # src/

import argparse

from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.patch import PatchApplier
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
        self._register_pack(sub)
        self._register_assemble(sub)
        return parser

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

    # ── subcommand: pack ─────────────────────────────────────────────────────
    def _register_pack(self, sub) -> None:
        pack = sub.add_parser("pack", help="pack a build stage's output into a flashable artifact")
        pack.add_argument("--board", required=True)
        pack.add_argument("component", choices=["ubifs", "fit", "loader", "sd", "emmc"],
                          help="which packer (more land in later PRs)")
        pack.add_argument("--variant", choices=["nand", "sd"], default="nand", help="fit: nand (default) | sd")
        pack.add_argument("--kernel-dir", default=None,
                          help="fit: kernel artifact dir (default: the board's linux tree)")
        pack.set_defaults(func=self._cmd_pack)

    def _cmd_pack(self, args: argparse.Namespace) -> int:
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
        asm = sub.add_parser("assemble", help="assemble update.img from partition images")
        asm.add_argument("--board", required=True)
        asm.add_argument("--variant", choices=list(_VARIANTS), default="provision",
                         help="provision (default) | nand | rescue | sd | emmc")
        asm.add_argument("--no-verify", action="store_true", help="skip the round-trip self-check")
        asm.set_defaults(func=self._cmd_assemble)

    def _cmd_assemble(self, args: argparse.Namespace) -> int:
        root = args.root or self.root
        board = Board.from_yaml(args.board, root=root)
        Updater(board, Project.from_yaml(root), log=self.log).assemble(
            variant=args.variant, out_dir=self._out_dir(Project.from_yaml(root), board),
            verify=not args.no_verify)
        return 0

    @staticmethod
    def _out_dir(project: Project, board: Board) -> Path:
        """Where this board's build products land today (board-scoped).

        Single point that flips to ``project.out_root / board.id`` at F4 (root
        out/ aggregation); every stage routes through here so the change is local.
        """
        return project.root / board.bringup_dir / "out"


def main(argv: list[str] | None = None) -> int:
    return ForgeCLI().main(argv)


if __name__ == "__main__":
    sys.exit(main())
