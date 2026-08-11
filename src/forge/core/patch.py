"""PatchApplier — quilt-style ordered patch series into a component worktree via
``git am``. Replaces scripts/apply-series.sh.

Real commits (preserves authorship, bisectable), applied in series order with
atomic rollback on failure (``git am --abort`` + ``reset --hard <pre>`` +
``clean -fdq``) — fixes the imx-forge debt where only the last patch applied and
failures silently skipped. ``--check`` does a real apply-then-revert dry-run
(``git apply --check`` on patch N alone can't see N-1's effect).

git runs via Proc with an explicit env (PATH/HOME only) — no FORGE_* / board
fields leak into the git process. Run with ``cwd`` = the component worktree.
"""
from __future__ import annotations

from pathlib import Path

from forge.config.board import Board
from forge.config.project import Project
from forge.core.log import Log
from forge.core.proc import Proc


class PatchApplier:
    """Applies boards/<board>/patches/<component>/series into a component worktree."""

    def __init__(self, board: Board, project: Project, worktree: Path,
                 proc: Proc | None = None, log: Log | None = None):
        self.board = board
        self.project = project
        self.worktree = Path(worktree)
        self.log = log or Log()
        self.proc = proc or Proc(log=self.log)

    def apply(self, component: str, check: bool = False) -> None:
        series = self.project.root / "boards" / self.board.id / "patches" / component / "series"
        if not series.is_file():
            self.log.warn(f"no series at {series} (nothing to apply)")
            return
        self._require_worktree()

        pre_head = self._git("rev-parse", "HEAD")
        patches = self._parse_series(series)
        if not patches:
            self.log.warn("series is empty")
            return

        self.log.info(f"component={component} patches={len(patches)} check={check} base={pre_head[:8]}")

        for i, patch in enumerate(patches, 1):
            if self._git_ok("am", "--3way", "--signoff", str(patch)):
                self.log.ok(f"[{i}/{len(patches)}] {patch.name}")
            else:
                self._git_ok("am", "--abort")
                self._rollback(pre_head)
                self.log.die(f"[{i}/{len(patches)}] FAILED {patch.name} — rolled back to {pre_head[:8]}. "
                             f"Edit the patch or reorder boards/{self.board.id}/patches/{component}/series.")

        if check:
            self._rollback(pre_head)
            self.log.ok(f"dry-run OK: all {len(patches)} patches apply in order (worktree untouched)")
        else:
            new_head = self._git("rev-parse", "HEAD")
            self.log.ok(f"applied {len(patches)} patches: {pre_head[:8]} -> {new_head[:8]}")

    # ── helpers ──────────────────────────────────────────────────────────────
    def _parse_series(self, series: Path) -> list[Path]:
        patches: list[Path] = []
        for line in series.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                patches.append(series.parent / line)
        return patches

    def _require_worktree(self) -> None:
        if not self._git_ok("rev-parse", "--is-inside-work-tree"):
            self.log.die(f"not inside a git worktree: {self.worktree}")

    def _rollback(self, pre_head: str) -> None:
        self._git_ok("reset", "--hard", pre_head)
        self._git_ok("clean", "-fdq")

    def _git(self, *args: str) -> str:
        """Run git, return stdout (stripped). Raises on non-zero."""
        return self.proc.run(["git", *args], cwd=str(self.worktree),
                             capture=True, quiet=True).stdout.strip()

    def _git_ok(self, *args: str) -> bool:
        """Run git, return True on success (no raise)."""
        return self.proc.run(["git", *args], cwd=str(self.worktree),
                             check=False, capture=True, quiet=True).returncode == 0
