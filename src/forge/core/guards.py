"""Guards — structured refusal for dangerous operations (the §4.6 substrate).

pack/flash stages that touch disks or raw-write images route their target
through these before any sgdisk / dd / mke2fs. ``assert_regular_file`` is the
pack-sd addition: the bash pack-sd built a regular file by construction but
never explicitly refused a block device, so a mistaken ``--out /dev/sdX`` would
have partitioned a real disk. The guard turns "never a block device" from a
construction-time assumption into an explicit, tested invariant.

``unreadable_tree_entries`` is the NFS-pollution guard (2026-11-02 rk3588
incident): the staged rootfs doubles as the board's NFS root, so every board
boot litters real-root-owned runtime files (mode 000) into the ext4 source
tree and the next mke2fs -d dies mid-populate with a cryptic per-file error —
after already truncating the target image.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path


def assert_regular_file(path: Path, label: str = "image") -> None:
    """Refuse if ``path`` is a block/char device.

    sgdisk / dd / mke2fs must target a regular file image, never a real disk. A
    not-yet-created target is allowed (the caller is about to create it as a
    regular file).
    """
    p = Path(path)
    try:
        st = p.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISBLK(st.st_mode) or stat.S_ISCHR(st.st_mode):
        raise ValueError(
            f"refuse: {label} target {path} is a block/char device, not a regular file"
        )


def unreadable_tree_entries(root: Path) -> list[Path]:
    """Regular files/dirs under ``root`` that ``mke2fs -d`` cannot copy.

    Symlinks are skipped: mke2fs stores the link text and never reads the
    target, so even dangling board-created symlinks pack fine — only a
    genuinely unreadable file or unsearchable dir breaks the populate step.
    """
    bad: list[Path] = []

    def flag(path: str, need: int) -> None:
        if not os.access(path, need):
            bad.append(Path(path))

    def on_error(err: OSError) -> None:
        bad.append(Path(err.filename or str(root)))

    for dirpath, _dirnames, filenames in os.walk(root, onerror=on_error,
                                                 followlinks=False):
        flag(dirpath, os.R_OK | os.X_OK)
        for name in filenames:
            p = os.path.join(dirpath, name)
            if not os.path.islink(p):
                flag(p, os.R_OK)
    return bad


def unreadable_tree_message(root: Path, bad: list[Path]) -> str:
    """The die() text for unreadable staging entries: name the files, explain
    the NFS no_root_squash origin, hand over the fix one-liner."""
    head = "\n  ".join(str(p) for p in bad[:10])
    if len(bad) > 10:
        head += f"\n  … (+{len(bad) - 10} more)"
    return (
        f"{len(bad)} staged-rootfs entries unreadable — the tree is the board's NFS "
        f"root (/etc/exports no_root_squash), and board boots leave real-root-owned "
        f"runtime files in it that mke2fs -d cannot copy (an aborted run also leaves "
        f"a truncated image behind):\n  {head}\n"
        f"fix: sudo chown -R $(id -un):$(id -gn) {root} — or rm the board-runtime "
        f"files — then re-run pack"
    )
