#!/usr/bin/env python3
"""guards.unreadable_tree_entries — the NFS-pollution scan (2026-11-02 incident).

The staged rootfs doubles as the board's NFS root (/etc/exports no_root_squash),
so board boots leave real-root-owned mode-000 runtime files (crond.reboot, …)
in the ext4 source tree. The next ``mke2fs -d`` then died mid-populate with a
cryptic per-file error — after already truncating rootfs.ext4 into a half
image. The scan must catch unreadable regular files while NOT flagging the
board's dangling symlinks (mke2fs stores the link text, never reads the
target), or every post-boot pack would false-positive on /dev/stdin & co.

Run directly:  python3 tests/test_guards.py
With pytest:   pytest tests/test_guards.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from forge.core.guards import unreadable_tree_entries, unreadable_tree_message  # noqa: E402


def _scan(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in unreadable_tree_entries(root)}


def test_unreadable_entries():
    if os.geteuid() == 0:
        print("skip: running as root — os.access always true")
        return
    with TemporaryDirectory() as td:
        root = Path(td)
        (root / "etc").mkdir()
        (root / "etc" / "hostname").write_text("board\n")          # normal — fine
        (root / "dev").mkdir()
        # dangling board symlink (→ /proc/…): unreadable via os.access, but
        # mke2fs stores the link text — must NOT be flagged
        (root / "dev" / "stdin").symlink_to("../proc/self/fd/0")
        # the actual breaker: unreadable regular file
        locked = root / "crond.reboot"
        locked.write_bytes(b"")
        locked.chmod(0o000)

        bad = _scan(root)
        assert bad == {"crond.reboot"}, f"expected only crond.reboot, got {bad}"

        msg = unreadable_tree_message(root, unreadable_tree_entries(root))
        assert "crond.reboot" in msg and "no_root_squash" in msg and "chown" in msg

        locked.chmod(0o644)  # cleanup (TempDir can't unlink a 000 file's parent path otherwise fine)


if __name__ == "__main__":
    test_unreadable_entries()
    print("test_guards: OK")
