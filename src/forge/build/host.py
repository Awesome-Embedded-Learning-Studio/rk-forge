"""Host environment helpers — WSL2 / Windows PATH contamination.

Faithful port of ``lib/host.sh``. WSL2 inherits Windows PATH entries
(``/mnt/c/Program Files/…``) that break some builds — buildroot's
``support/dependencies/dependencies.mk`` rejects any PATH entry containing a
space (or TAB/newline). :func:`clean_path` strips ``/mnt/*`` + whitespace
entries for the builds that need it (buildroot).
"""
from __future__ import annotations

import os
import re

from forge.core.log import Log

_WS = re.compile(r"\s")
_MNT = re.compile(r"^/mnt/")


def is_windows_contaminated(path: str | None = None) -> bool:
    """True if PATH has ``/mnt/*`` entries or whitespace within an entry."""
    path = path if path is not None else os.environ.get("PATH", "")
    for entry in path.split(":"):
        if _MNT.search(entry) or _WS.search(entry):
            return True
    return False


def warn_windows_path(log: Log) -> None:
    """Warn once if the host PATH is Windows-contaminated (buildroot will break)."""
    if is_windows_contaminated():
        log.warn(
            "host PATH has Windows entries (/mnt/... or whitespace) — breaks "
            "buildroot (dependencies.mk); clean_path strips them"
        )


def clean_path(path: str | None = None) -> str:
    """PATH with ``/mnt/*`` and whitespace-containing entries removed (the buildroot fix)."""
    path = path if path is not None else os.environ.get("PATH", "")
    kept = [e for e in path.split(":") if e and not _MNT.search(e) and not _WS.search(e)]
    return ":".join(kept)
