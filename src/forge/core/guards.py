"""Guards — structured refusal for dangerous operations (the §4.6 substrate).

pack/flash stages that touch disks or raw-write images route their target
through these before any sgdisk / dd / mke2fs. ``assert_regular_file`` is the
pack-sd addition: the bash pack-sd built a regular file by construction but
never explicitly refused a block device, so a mistaken ``--out /dev/sdX`` would
have partitioned a real disk. The guard turns "never a block device" from a
construction-time assumption into an explicit, tested invariant.
"""
from __future__ import annotations

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
